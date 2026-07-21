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
import platform
import sys
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path
from typing import Any


CAMPAIGN_ID = "perdomo-2025-table3-public-route-installed-v1"
STATUS = "NOT_EVALUATED_PUBLIC_ROUTE_ABSENT"
MIGRATION_COMMIT = "8d916b9b7d76c3adc3ffce17c35b9a27224e4763"
MIGRATION_TREE = "a9c198f9a8e4019280faa3b96d9d559e7924e0a9"
EQUILIBRIUM_COMMIT = "2d4cfcbec537e3ff3d2272a5a6ad10959a00a09e"
EQUILIBRIUM_TREE = "3acbae48db7dfe5ad1b9857c6907ba1384e7c91a"
SOURCE_COMMIT = "5620f030b1e4bf12cde2f97d739cb931653eb960"
SOURCE_TREE = "6d40521d15b823ab4243dd772e3069d82bd342ba"
PROVIDER_SHA256 = "9e4da0d7ba7896bcd2ec096400553d935e0516c61f1bd9f41f2370ab68ab36ea"
EQUILIBRIUM_SHA256 = "ff34db9643b79dad9df0095c190d55f98e02f4fc268e073ec83594669b277831"
TRACE_SHA256 = "0ff032a747992a6add25dc6228da0628fcf901dc176f7f408a61c7a9c82903df"
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
PUBLIC_ROUTE_FAILURE = "tp_flash requires exactly two components"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
        "public_route": "ABSENT_FOR_ELECTROLYTE_INPUT",
        "solver": "NOT_EVALUATED",
        "numerical": "NOT_EVALUATED",
        "physical": "NOT_EVALUATED",
        "source_topology_comparison": "NOT_EVALUATED",
        "predictive_endpoint_comparison": "NOT_EVALUATED",
        "search_completeness": "NOT_EVALUATED",
        "globality": "NOT_GUARANTEED",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    provider_wheel = required_wheel(args.provider_wheel)
    equilibrium_wheel = required_wheel(args.equilibrium_wheel)
    trace = required_file(args.retained_trace)
    if sha256_file(trace) != TRACE_SHA256:
        raise ValueError("retained package trace SHA-256 mismatch")
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
    try:
        equilibrium_api.tp_flash(
            model,
            TEMPERATURE_K * epcsaft.unit_registry.kelvin,
            PRESSURE_PA * epcsaft.unit_registry.pascal,
            FEED_Z,
        )
    except equilibrium_api.FlashError as error:
        diagnostics = asdict(error.diagnostics)
        if (
            diagnostics["outcome"] != "invalid_input"
            or diagnostics["search_status"] != "input_rejected"
            or diagnostics["failure_reason"] != PUBLIC_ROUTE_FAILURE
        ):
            raise RuntimeError(
                f"unexpected public tp_flash failure: {diagnostics}"
            ) from error
    else:
        raise RuntimeError(
            "exact artifact unexpectedly accepted public electrolyte tp_flash"
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
            "retained_package_trace_context_only": {
                "path": str(trace),
                "sha256": TRACE_SHA256,
                "role": "hash-bound package context only; no result or private runner was consumed",
            },
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
            "status": "not_started_public_route_absent",
            "private_adapter_called": False,
        },
        "public_route_audit": {
            "symbol": "epcsaft_equilibrium.tp_flash",
            "publicly_exported": True,
            "signature": str(inspect.signature(equilibrium_api.tp_flash)),
            "call_attempted": True,
            "exception_type": "FlashError",
            "exception_diagnostics": diagnostics,
            "surface_gap": (
                "The installed public generic tp_flash route admits exactly two "
                "components and has no public dispatch for the three-component "
                "water/Na+/Cl- electrolyte model."
            ),
        },
        "source_comparison": {
            "published_phase_count": 2,
            "returned_phase_count": None,
            "topology_status": "not_evaluated_public_route_absent",
            "endpoint_status": "not_evaluated_no_public_result",
            "topology_disagreement": None,
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
            "environment": "uv venv $D025_ENV --python 3.13",
            "install": (
                "uv pip install --python $D025_ENV/bin/python --offline "
                "$PROVIDER_WHEEL $EQUILIBRIUM_WHEEL"
            ),
            "run": (
                "cd $D025_ENV && env -u PYTHONPATH $D025_ENV/bin/python -I "
                "$VALIDATION_ROOT/campaigns/perdomo_table3_public_route.py run "
                "--provider-wheel $PROVIDER_WHEEL --equilibrium-wheel "
                "$EQUILIBRIUM_WHEEL --retained-trace $RETAINED_TRACE "
                "--source-metadata $VALIDATION_ROOT/data/perdomo-2025-held2-source-ledger.yaml "
                "--source-cases $VALIDATION_ROOT/data/perdomo-2025-held2-case-ledger.csv "
                "--source-samples $VALIDATION_ROOT/data/perdomo-2025-held2-published-samples.csv "
                "--output $VALIDATION_ROOT/results/perdomo-table3-public-route-validation.json"
            ),
        },
        "negative_space": [
            "No private _held2 adapter or native private symbol was imported or called.",
            "No package-retained runner, result payload, or expected numerical output was copied.",
            "No solver search, forced phase split, endpoint comparison, tolerance change, package edit, receipt, promotion, or authority action occurred.",
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
    if artifacts["retained_package_trace_context_only"]["sha256"] != TRACE_SHA256:
        raise ValueError("retained trace identity changed")
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
    diagnostics = audit["exception_diagnostics"]
    if (
        not audit["publicly_exported"]
        or diagnostics["outcome"] != "invalid_input"
        or diagnostics["failure_reason"] != PUBLIC_ROUTE_FAILURE
    ):
        raise ValueError("public route gap changed")
    if record["decisions"] != decisions():
        raise ValueError("decision axes changed")
    if record["source_comparison"] != {
        "published_phase_count": 2,
        "returned_phase_count": None,
        "topology_status": "not_evaluated_public_route_absent",
        "endpoint_status": "not_evaluated_no_public_result",
        "topology_disagreement": None,
    }:
        raise ValueError("source comparison was evaluated without a public result")
    if record["globality_certificate"] != "not_guaranteed":
        raise ValueError("globality boundary changed")
    if record["frozen_search_contract"] != {
        "declared_starts": DECLARED_STARTS,
        "seed": STAGE_I_SEED,
        "status": "not_started_public_route_absent",
        "private_adapter_called": False,
    }:
        raise ValueError("search was entered despite the missing public route")
    return {
        "status": STATUS,
        "artifact_input": "PASS",
        "public_route": "ABSENT_FOR_ELECTROLYTE_INPUT",
        "solver": "NOT_EVALUATED",
        "source_topology_comparison": "NOT_EVALUATED",
        "predictive_endpoint_comparison": "NOT_EVALUATED",
        "globality_certificate": "not_guaranteed",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    execute = subparsers.add_parser("run")
    execute.add_argument("--provider-wheel", required=True, type=required_wheel)
    execute.add_argument("--equilibrium-wheel", required=True, type=required_wheel)
    execute.add_argument("--retained-trace", required=True, type=required_file)
    execute.add_argument("--source-metadata", required=True, type=required_file)
    execute.add_argument("--source-cases", required=True, type=required_file)
    execute.add_argument("--source-samples", required=True, type=required_file)
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
