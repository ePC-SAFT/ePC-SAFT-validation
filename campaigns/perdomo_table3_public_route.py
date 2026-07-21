#!/usr/bin/env python3
"""Audit the exact D-025 Perdomo Table-3 case through installed public APIs."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib
import importlib.metadata
import inspect
import json
import math
import platform
import sys
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path
from typing import Any


CAMPAIGN_ID = "perdomo-2025-table3-public-route-installed-v1"
STATUS = "PUBLIC_ROUTE_PASS_SOURCE_TOPOLOGY_DISAGREEMENT"
MIGRATION_COMMIT = "8d916b9b7d76c3adc3ffce17c35b9a27224e4763"
MIGRATION_TREE = "a9c198f9a8e4019280faa3b96d9d559e7924e0a9"
EQUILIBRIUM_COMMIT = "ef6fe362dc0bd84521e7499728ed977ce62c17f1"
EQUILIBRIUM_TREE = "f196c86cf5eacbaadbc62f8d900fd02bd99413b3"
SOURCE_COMMIT = "5620f030b1e4bf12cde2f97d739cb931653eb960"
SOURCE_TREE = "6d40521d15b823ab4243dd772e3069d82bd342ba"
PROVIDER_SHA256 = "9e4da0d7ba7896bcd2ec096400553d935e0516c61f1bd9f41f2370ab68ab36ea"
EQUILIBRIUM_SHA256 = "da37682dc06d278cc0c7e9333d61604c81209727cc99b1b91c9682d2aa82e5c7"
SOURCE_METADATA_SHA256 = (
    "2cce8ab35505b67622c4096604d4051122516b374bd36aea0ea12848eab8b436"
)
SOURCE_CASES_SHA256 = "654e4098f53abfa75bf8d4b5b8093fd56b89d352164be2a18c7804cc5a3a1282"
SOURCE_SAMPLES_SHA256 = (
    "92338efdb800f8a4546a0ed9bbd0944021586735c181963057c86e3e9b4f7c1f"
)
PARAMETER_FINGERPRINT = (
    "sha256:7c637771bc9f717b8f47b44bb2a61044c3fe83084dca7c3c16102fba0989912d"
)
COMPONENT_IDS = ("water", "sodium-cation", "chloride-anion")
FEED_Z = (0.8321050353538131, 0.08394748232309347, 0.08394748232309347)
TEMPERATURE_K = 298.15
PRESSURE_PA = 2508.0
WATER_MOLAR_MASS_KG_PER_MOL = 0.0180153
DECLARED_STARTS = 30
STAGE_I_SEED = 2025
EXPECTED_OUTCOME = "one_phase"
EXPECTED_SEARCH_STATUS = "complete_no_negative_found"
EXPECTED_BEST_TPD = -1.6139519381498581e-12
EXPECTED_SEARCH_PROFILE = "perdomo-held2-stage-i-installed-v1"
EXPECTED_RESULT_PAYLOAD_SHA256 = (
    "45380b1d572b1f13b884041cb813ae3290f02647de55ba4f629da1b20de9d924"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def required_file(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"required file is absent: {path}")
    return path


def required_wheel(value: str | Path) -> Path:
    path = required_file(value)
    if path.suffix != ".whl":
        raise ValueError(f"artifact is not a wheel: {path}")
    return path


def _wheel_contract(wheel: Path) -> tuple[str, str, list[list[str]]]:
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        record_name = metadata_name.removesuffix("METADATA") + "RECORD"
        records = list(csv.reader(archive.read(record_name).decode().splitlines()))
    return str(metadata["Name"]), str(metadata["Version"]), records


def verify_installed_wheel(
    wheel: Path, distribution_name: str, expected_sha256: str
) -> dict[str, Any]:
    observed_sha256 = sha256_file(wheel)
    if observed_sha256 != expected_sha256:
        raise ValueError(f"{distribution_name} wheel SHA-256 mismatch")
    wheel_name, wheel_version, record_rows = _wheel_contract(wheel)
    if wheel_name != distribution_name:
        raise ValueError(
            f"wheel distribution is {wheel_name!r}, not {distribution_name!r}"
        )
    distribution = importlib.metadata.distribution(distribution_name)
    if distribution.version != wheel_version:
        raise ValueError(f"installed {distribution_name} version differs from wheel")
    installed_root = Path(distribution.locate_file("")).resolve()
    if "site-packages" not in installed_root.parts:
        raise ValueError(f"{distribution_name} is not installed in site-packages")
    verified_members = 0
    for member, encoded_hash, *_ in record_rows:
        if not encoded_hash:
            continue
        algorithm, expected = encoded_hash.split("=", 1)
        if algorithm != "sha256":
            raise ValueError(f"unsupported RECORD algorithm: {algorithm}")
        installed = Path(distribution.locate_file(member)).resolve()
        if not installed.is_file():
            raise ValueError(f"installed RECORD member is absent: {member}")
        actual = (
            base64.urlsafe_b64encode(hashlib.sha256(installed.read_bytes()).digest())
            .rstrip(b"=")
            .decode()
        )
        if actual != expected:
            raise ValueError(f"installed RECORD member mismatch: {member}")
        verified_members += 1
    if not verified_members:
        raise ValueError(f"{distribution_name} RECORD has no hashed members")
    record_path = Path(
        distribution.locate_file(
            f"{distribution_name.replace('-', '_')}-{wheel_version}.dist-info/RECORD"
        )
    ).resolve()
    package_name = distribution_name.replace("-", "_")
    native_members = sorted((installed_root / package_name).glob("_*.so"))
    return {
        "path": str(wheel),
        "sha256": observed_sha256,
        "distribution": wheel_name,
        "version": wheel_version,
        "installed_root": str(installed_root),
        "record_path": str(record_path),
        "record_sha256": sha256_file(record_path),
        "record_members_verified": verified_members,
        "native_members": [
            {"path": str(path), "sha256": sha256_file(path)} for path in native_members
        ],
    }


def reject_sibling_source_paths(validation_root: Path) -> None:
    project_root = validation_root.parent
    forbidden = (project_root / "ePC-SAFT", project_root / "ePC-SAFT-equilibrium")
    for entry in sys.path:
        if not entry:
            continue
        resolved = Path(entry).resolve()
        if any(resolved == root or resolved.is_relative_to(root) for root in forbidden):
            raise RuntimeError(f"sibling source checkout is on sys.path: {resolved}")


def load_source_contract(
    metadata_path: Path, cases_path: Path, samples_path: Path
) -> dict[str, Any]:
    observed = {
        "metadata": sha256_file(metadata_path),
        "cases": sha256_file(cases_path),
        "samples": sha256_file(samples_path),
    }
    expected = {
        "metadata": SOURCE_METADATA_SHA256,
        "cases": SOURCE_CASES_SHA256,
        "samples": SOURCE_SAMPLES_SHA256,
    }
    if observed != expected:
        raise ValueError(f"Perdomo source contract hash mismatch: {observed}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata["dataset_id"] != "perdomo-2025-held2-case-study-ledger-v1":
        raise ValueError("unexpected Perdomo source-ledger identity")
    with samples_path.open(newline="", encoding="utf-8") as stream:
        sample = next(
            row
            for row in csv.DictReader(stream)
            if row["sample_id"] == "table3-nacl-5.6molal"
        )
    if (
        float(sample["temperature_K"]) != TEMPERATURE_K
        or float(sample["pressure_kPa"]) * 1000.0 != PRESSURE_PA
        or int(sample["reported_phase_count"]) != 2
    ):
        raise ValueError("Perdomo Table-3 scalar contract changed")
    molality = float(sample["input_1_value"])
    amounts = (1.0 / WATER_MOLAR_MASS_KG_PER_MOL, molality, molality)
    derived_feed = tuple(value / sum(amounts) for value in amounts)
    if any(abs(left - right) > 5e-16 for left, right in zip(derived_feed, FEED_Z)):
        raise ValueError(
            "formula-unit molality no longer derives the frozen explicit feed"
        )
    source_order = tuple(sample["species_order"].split("|"))
    vapor = tuple(float(value) for value in sample["phase_1_x"].split("|"))
    liquid = tuple(float(value) for value in sample["phase_2_x"].split("|"))
    index = {name: offset for offset, name in enumerate(source_order)}
    public_order = {"water": "water", "sodium-cation": "Na+", "chloride-anion": "Cl-"}
    return {
        "authority_commit": SOURCE_COMMIT,
        "authority_tree": SOURCE_TREE,
        "metadata": {"path": str(metadata_path), "sha256": observed["metadata"]},
        "cases": {"path": str(cases_path), "sha256": observed["cases"]},
        "samples": {"path": str(samples_path), "sha256": observed["samples"]},
        "sample_id": sample["sample_id"],
        "doi": metadata["citation"]["doi"],
        "locator": "Perdomo et al. 2025 Table 3, retained Markdown lines 849-860",
        "reported_phase_count": 2,
        "reported_endpoints_in_public_order": {
            "vapor": [vapor[index[public_order[name]]] for name in COMPONENT_IDS],
            "liquid": [liquid[index[public_order[name]]] for name in COMPONENT_IDS],
        },
        "feed_derivation": {
            "salt_formula_unit_molality_mol_per_kg": molality,
            "salt_free_water_basis_kg": 1.0,
            "water_molar_mass_kg_per_mol": WATER_MOLAR_MASS_KG_PER_MOL,
            "explicit_amounts_mol": list(amounts),
            "normalized_feed": list(derived_feed),
        },
    }


def decisions() -> dict[str, str]:
    return {
        "artifact_input": "PASS",
        "public_route": "PASS",
        "solver": "PASS",
        "numerical": "PASS",
        "physical": "PASS",
        "source_topology_comparison": "DISAGREEMENT_CROSS_EOS",
        "predictive_endpoint_comparison": "NOT_EVALUATED",
        "search_completeness": "PASS_DECLARED_30_OF_30",
        "globality": "NOT_GUARANTEED",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    provider_wheel = required_wheel(args.provider_wheel)
    equilibrium_wheel = required_wheel(args.equilibrium_wheel)
    provider = verify_installed_wheel(provider_wheel, "epcsaft", PROVIDER_SHA256)
    equilibrium = verify_installed_wheel(
        equilibrium_wheel, "epcsaft-equilibrium", EQUILIBRIUM_SHA256
    )
    validation_root = Path(__file__).resolve().parents[1]
    reject_sibling_source_paths(validation_root)
    source = load_source_contract(
        required_file(args.source_metadata),
        required_file(args.source_cases),
        required_file(args.source_samples),
    )

    epcsaft = importlib.import_module("epcsaft")
    equilibrium_api = importlib.import_module("epcsaft_equilibrium")
    for module, artifact in ((epcsaft, provider), (equilibrium_api, equilibrium)):
        origin = Path(module.__file__).resolve()
        if not origin.is_relative_to(Path(artifact["installed_root"])):
            raise RuntimeError(
                f"module import did not originate in verified artifact: {origin}"
            )
    if "tp_flash" not in equilibrium_api.__all__:
        raise RuntimeError("tp_flash is not a public epcsaft_equilibrium export")

    parameters = epcsaft.ParameterBundle.from_catalog(
        "figiel-2025-reference-electrolytes", version=1
    ).select(COMPONENT_IDS)
    if parameters.fingerprint != PARAMETER_FINGERPRINT:
        raise ValueError("public Provider parameter fingerprint changed")
    model = epcsaft.EPCSAFT(parameters)
    if args.captured_result is None:
        result = equilibrium_api.tp_flash(
            model,
            TEMPERATURE_K * epcsaft.unit_registry.kelvin,
            PRESSURE_PA * epcsaft.unit_registry.pascal,
            FEED_Z,
        )
        result_payload = asdict(result)
        result_type = f"{type(result).__module__}.{type(result).__qualname__}"
        payload_source = "live_public_call"
    else:
        captured = json.loads(required_file(args.captured_result).read_text())
        if "public_route_audit" in captured:
            captured = captured["public_route_audit"]
        result_payload = captured["result"]
        result_type = captured["result_type"]
        payload_source = "retained_active_session_public_call"
    diagnostics = result_payload["diagnostics"]
    if sha256_json(result_payload) != EXPECTED_RESULT_PAYLOAD_SHA256:
        raise RuntimeError("retained public result payload SHA-256 mismatch")
    if (
        diagnostics["outcome"] != EXPECTED_OUTCOME
        or diagnostics["search_status"] != EXPECTED_SEARCH_STATUS
        or diagnostics["attempts"] != DECLARED_STARTS
        or diagnostics["best_tpd"] != EXPECTED_BEST_TPD
        or tuple(diagnostics["search_profiles"]) != (EXPECTED_SEARCH_PROFILE,)
        or diagnostics["solver_status"] != "passed"
        or diagnostics["numerical_status"] != "passed"
        or diagnostics["physical_status"] != "passed"
        or diagnostics["globality_certificate"] != "not_guaranteed"
    ):
        raise RuntimeError(f"corrected public-route contract mismatch: {diagnostics}")
    phases = result_payload["phases"]
    if (
        result_payload["temperature_k"] != TEMPERATURE_K
        or result_payload["pressure_pa"] != PRESSURE_PA
        or tuple(result_payload["overall_mole_fractions"]) != FEED_Z
        or result_payload["parameter_fingerprint"] != PARAMETER_FINGERPRINT
        or tuple(result_payload["phase_fractions"]) != (1.0,)
        or len(phases) != 1
        or tuple(phases[0]["mole_fractions"]) != FEED_Z
    ):
        raise RuntimeError("public result changed the frozen input or one-phase state")
    if not all(
        math.isfinite(value)
        for value in (
            result_payload["total_free_energy_over_rt"],
            phases[0]["molar_density_mol_m3"],
            phases[0]["pressure_pa"],
            phases[0]["volume_m3"],
            *phases[0]["chemical_potential_over_rt"],
        )
    ):
        raise RuntimeError("public result contains a non-finite physical value")

    mole_fraction_sum_residual = abs(sum(phases[0]["mole_fractions"]) - 1.0)
    charge_residual = abs(
        sum(
            charge * mole_fraction
            for charge, mole_fraction in zip(
                (0, 1, -1), phases[0]["mole_fractions"], strict=True
            )
        )
    )

    record = {
        "schema": "perdomo-table3-public-route-validation-v1",
        "campaign_id": CAMPAIGN_ID,
        "status": STATUS,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "authority_effect": "none",
        "production_status": "non-production-validation-evidence",
        "migration_binding": {"commit": MIGRATION_COMMIT, "tree": MIGRATION_TREE},
        "equilibrium_subject": {
            "commit": EQUILIBRIUM_COMMIT,
            "tree": EQUILIBRIUM_TREE,
        },
        "artifacts": {
            "provider": provider,
            "equilibrium": equilibrium,
        },
        "source": source,
        "input": {
            "temperature_K": TEMPERATURE_K,
            "pressure_Pa": PRESSURE_PA,
            "component_ids": list(COMPONENT_IDS),
            "charges": [0, 1, -1],
            "feed_explicit_species_mole_fractions": list(FEED_Z),
            "parameter_bundle": "figiel-2025-reference-electrolytes@1",
            "parameter_fingerprint": parameters.fingerprint,
        },
        "frozen_search_contract": {
            "declared_starts": DECLARED_STARTS,
            "seed": STAGE_I_SEED,
            "observed_attempts": diagnostics["attempts"],
            "search_profile": diagnostics["search_profiles"][0],
            "search_status": diagnostics["search_status"],
            "private_adapter_called": False,
        },
        "public_route_audit": {
            "symbol": "epcsaft_equilibrium.tp_flash",
            "publicly_exported": True,
            "signature": str(inspect.signature(equilibrium_api.tp_flash)),
            "call_attempted": True,
            "call_completed": True,
            "result_type": result_type,
            "payload_source": payload_source,
            "result_payload_sha256": sha256_json(result_payload),
            "result": result_payload,
        },
        "execution_accounting": {
            "public_solver_executions": 3,
            "canonical_payload_execution": "exploratory_public_audit",
            "evidence_assembly_solver_execution": False,
            "attempts": [
                {
                    "id": "exploratory_public_audit",
                    "scientific_status": "completed",
                    "evidence_status": "raw_payload_retained_in_active_session",
                },
                {
                    "id": "campaign_capture_1",
                    "scientific_status": (
                        "completed_expected_diagnostics_before_postcondition_failure"
                    ),
                    "evidence_status": (
                        "not_retained_search_profiles_tuple_list_postcondition_failure"
                    ),
                },
                {
                    "id": "campaign_corrective_capture_2",
                    "scientific_status": (
                        "completed_expected_diagnostics_before_postcondition_failure"
                    ),
                    "evidence_status": (
                        "not_retained_phase_fractions_tuple_list_postcondition_failure"
                    ),
                },
            ],
            "identity_continuity_claimed": False,
        },
        "independent_checks": {
            "returned_phase_count": len(phases),
            "phase_fraction_sum_residual": abs(
                sum(result_payload["phase_fractions"]) - 1.0
            ),
            "phase_mole_fraction_sum_residual": mole_fraction_sum_residual,
            "phase_charge_residual": charge_residual,
            "phase_pressure_residual_Pa": abs(phases[0]["pressure_pa"] - PRESSURE_PA),
            "all_retained_physical_values_finite": True,
        },
        "source_comparison": {
            "published_phase_count": 2,
            "returned_phase_count": 1,
            "topology_status": "disagreement_cross_eos",
            "endpoint_status": "not_evaluated_phase_count_disagreement",
            "topology_disagreement": True,
            "interpretation": (
                "The installed ePC-SAFT public result is one phase while the "
                "SAFT-gamma-Mie source reports two; this is a cross-EOS source "
                "topology disagreement, not a same-EOS reproduction test."
            ),
        },
        "decisions": decisions(),
        "globality_certificate": "not_guaranteed",
        "environment": {
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "imports_from_isolated_site_packages": True,
            "provider_import_origin": str(Path(epcsaft.__file__).resolve()),
            "equilibrium_import_origin": str(Path(equilibrium_api.__file__).resolve()),
            "sys_path": list(sys.path),
            "dependency_versions": {
                name: importlib.metadata.version(name)
                for name in ("pint", "flexcache", "flexparser", "platformdirs")
            },
        },
        "commands": {
            "environment": (
                "env -u PYTHONPATH uv run --isolated --no-project --offline "
                "--python 3.13"
            ),
            "install": (
                "--with $PROVIDER_WHEEL --with $EQUILIBRIUM_WHEEL; uv creates "
                "an isolated site-packages environment from the exact wheels"
            ),
            "run": (
                "env -u PYTHONPATH uv run --isolated --no-project --offline "
                "--python 3.13 --with $PROVIDER_WHEEL --with $EQUILIBRIUM_WHEEL "
                "python -I "
                "$VALIDATION_ROOT/campaigns/perdomo_table3_public_route.py run "
                "--provider-wheel $PROVIDER_WHEEL --equilibrium-wheel "
                "$EQUILIBRIUM_WHEEL "
                "--source-metadata $VALIDATION_ROOT/data/perdomo-2025-held2-source-ledger.yaml "
                "--source-cases $VALIDATION_ROOT/data/perdomo-2025-held2-case-ledger.csv "
                "--source-samples $VALIDATION_ROOT/data/perdomo-2025-held2-published-samples.csv "
                "--output $VALIDATION_ROOT/results/perdomo-table3-public-route-validation.json"
            ),
            "evidence_assembly": (
                "the same command with --captured-result $CAPTURED_RESULT; "
                "this serializes the retained raw payload without executing tp_flash"
            ),
        },
        "negative_space": [
            "No private _held2 adapter or native private symbol was imported or called.",
            "No package-retained runner, result payload, or expected numerical output was copied.",
            "No phase was forced and no endpoint comparison was evaluated after the phase-count disagreement.",
            "No tolerance change, package edit, receipt, promotion, same-EOS reproduction claim, or authority action occurred.",
        ],
    }
    check_record(record)
    output = Path(args.output).resolve()
    output.write_text(
        json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return record


def check_record(record: dict[str, Any]) -> dict[str, Any]:
    if record["schema"] != "perdomo-table3-public-route-validation-v1":
        raise ValueError("unexpected result schema")
    if record["campaign_id"] != CAMPAIGN_ID or record["status"] != STATUS:
        raise ValueError("public-route terminal status changed")
    if record["migration_binding"] != {
        "commit": MIGRATION_COMMIT,
        "tree": MIGRATION_TREE,
    }:
        raise ValueError("Migration binding changed")
    artifacts = record["artifacts"]
    if artifacts["provider"]["sha256"] != PROVIDER_SHA256:
        raise ValueError("Provider artifact changed")
    if artifacts["equilibrium"]["sha256"] != EQUILIBRIUM_SHA256:
        raise ValueError("Equilibrium artifact changed")
    source = record["source"]
    if (
        source["metadata"]["sha256"] != SOURCE_METADATA_SHA256
        or source["cases"]["sha256"] != SOURCE_CASES_SHA256
        or source["samples"]["sha256"] != SOURCE_SAMPLES_SHA256
    ):
        raise ValueError("source authority changed")
    inputs = record["input"]
    if (
        inputs["temperature_K"] != TEMPERATURE_K
        or inputs["pressure_Pa"] != PRESSURE_PA
        or tuple(inputs["component_ids"]) != COMPONENT_IDS
        or tuple(inputs["feed_explicit_species_mole_fractions"]) != FEED_Z
        or inputs["parameter_fingerprint"] != PARAMETER_FINGERPRINT
    ):
        raise ValueError("frozen Table-3 input changed")
    audit = record["public_route_audit"]
    result = audit["result"]
    diagnostics = result["diagnostics"]
    if (
        not audit["publicly_exported"]
        or not audit["call_completed"]
        or audit["result_payload_sha256"] != EXPECTED_RESULT_PAYLOAD_SHA256
        or sha256_json(result) != EXPECTED_RESULT_PAYLOAD_SHA256
        or diagnostics["outcome"] != EXPECTED_OUTCOME
        or diagnostics["search_status"] != EXPECTED_SEARCH_STATUS
        or diagnostics["attempts"] != DECLARED_STARTS
        or diagnostics["best_tpd"] != EXPECTED_BEST_TPD
        or diagnostics["solver_status"] != "passed"
        or diagnostics["numerical_status"] != "passed"
        or diagnostics["physical_status"] != "passed"
        or len(result["phases"]) != 1
        or tuple(result["overall_mole_fractions"]) != FEED_Z
        or tuple(result["phase_fractions"]) != (1.0,)
        or tuple(result["phases"][0]["mole_fractions"]) != FEED_Z
    ):
        raise ValueError("public route result changed")
    accounting = record["execution_accounting"]
    if (
        accounting["public_solver_executions"] != 3
        or accounting["canonical_payload_execution"] != "exploratory_public_audit"
        or accounting["evidence_assembly_solver_execution"]
        or accounting["identity_continuity_claimed"]
        or [attempt["scientific_status"] for attempt in accounting["attempts"]]
        != [
            "completed",
            "completed_expected_diagnostics_before_postcondition_failure",
            "completed_expected_diagnostics_before_postcondition_failure",
        ]
    ):
        raise ValueError("public solver execution accounting changed")
    if record["decisions"] != decisions():
        raise ValueError("decision axes changed")
    if record["source_comparison"] != {
        "published_phase_count": 2,
        "returned_phase_count": 1,
        "topology_status": "disagreement_cross_eos",
        "endpoint_status": "not_evaluated_phase_count_disagreement",
        "topology_disagreement": True,
        "interpretation": (
            "The installed ePC-SAFT public result is one phase while the "
            "SAFT-gamma-Mie source reports two; this is a cross-EOS source "
            "topology disagreement, not a same-EOS reproduction test."
        ),
    }:
        raise ValueError("source comparison classification changed")
    if record["globality_certificate"] != "not_guaranteed":
        raise ValueError("globality boundary changed")
    if record["frozen_search_contract"] != {
        "declared_starts": DECLARED_STARTS,
        "seed": STAGE_I_SEED,
        "observed_attempts": DECLARED_STARTS,
        "search_profile": EXPECTED_SEARCH_PROFILE,
        "search_status": EXPECTED_SEARCH_STATUS,
        "private_adapter_called": False,
    }:
        raise ValueError("declared search contract changed")
    return {
        "status": STATUS,
        "artifact_input": "PASS",
        "public_route": "PASS",
        "solver": "PASS",
        "source_topology_comparison": "DISAGREEMENT_CROSS_EOS",
        "predictive_endpoint_comparison": "NOT_EVALUATED",
        "globality_certificate": "not_guaranteed",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    execute = subparsers.add_parser("run")
    execute.add_argument("--provider-wheel", required=True, type=required_wheel)
    execute.add_argument("--equilibrium-wheel", required=True, type=required_wheel)
    execute.add_argument("--source-metadata", required=True, type=required_file)
    execute.add_argument("--source-cases", required=True, type=required_file)
    execute.add_argument("--source-samples", required=True, type=required_file)
    execute.add_argument("--captured-result", type=required_file)
    execute.add_argument("--output", required=True, type=Path)
    check = subparsers.add_parser("check")
    check.add_argument("record", type=required_file)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "run":
        summary = check_record(run(args))
    else:
        summary = check_record(json.loads(args.record.read_text(encoding="utf-8")))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
