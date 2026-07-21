"""Installed-artifact Haslam 2020 Table-8 cross-EOS campaign."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
import platform
import sys
from urllib.parse import unquote, urlparse
import zipfile
from typing import Any


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "data" / "hamer-wu-1972-haslam-table8.csv"
TARGETS = ROOT / "data" / "haslam-2020-table8-targets.csv"
SOURCE_LEDGER = ROOT / "data" / "haslam-2020-table8-source-ledger.yaml"
EXPECTED_ARTIFACT_SHA256 = (
    "961156a641435e33746a65d07d97e07a40243e0cfdf870932bd79961783afa96"
)
TEMPERATURE_K = 298.15
PRESSURE_MPA = 0.101
SUPPORTED = {
    "LiCl": ("figiel-2025-reference-electrolytes", "lithium-cation", "chloride-anion"),
    "LiBr": ("figiel-2025-reference-electrolytes", "lithium-cation", "bromide-anion"),
    "NaCl": ("figiel-2025-reference-electrolytes", "sodium-cation", "chloride-anion"),
    "NaBr": ("figiel-2025-reference-electrolytes", "sodium-cation", "bromide-anion"),
    "KCl": ("figiel-2025-reference-electrolytes", "potassium-cation", "chloride-anion"),
    "KBr": ("figiel-2025-reference-electrolytes", "potassium-cation", "bromide-anion"),
    "NaI": ("figiel-2025-aqueous-iodides", "sodium-cation", "iodide-anion"),
    "KI": ("figiel-2025-aqueous-iodides", "potassium-cation", "iodide-anion"),
}
SALTS = ("LiCl", "LiBr", "LiI", "NaCl", "NaBr", "NaI", "KCl", "KBr", "KI")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def percent_aad(observed: list[float], predicted: list[float]) -> float:
    """Conventional relative %AAD; Haslam's pointwise equation was not located."""
    return (
        100.0
        * math.fsum(
            abs((calc - exp) / exp)
            for exp, calc in zip(observed, predicted, strict=True)
        )
        / len(observed)
    )


def verify_installed_wheel(artifact: Path) -> dict[str, Any]:
    """Prove imported distribution files came from the named wheel."""
    distribution = metadata.distribution("epcsaft")
    direct_url_text = distribution.read_text("direct_url.json")
    if direct_url_text is None:
        raise AssertionError("installed distribution has no direct_url.json")
    direct_url = json.loads(direct_url_text)
    installed_from = Path(unquote(urlparse(direct_url["url"]).path)).resolve()
    if installed_from != artifact:
        raise AssertionError(
            f"installed epcsaft origin {installed_from} is not artifact {artifact}"
        )
    verified: list[str] = []
    with zipfile.ZipFile(artifact) as wheel:
        record_name = next(
            name for name in wheel.namelist() if name.endswith(".dist-info/RECORD")
        )
        wheel_rows = csv.reader(wheel.read(record_name).decode("utf-8").splitlines())
        for relative, encoded_hash, _size in wheel_rows:
            if not encoded_hash:
                continue
            algorithm, expected = encoded_hash.split("=", 1)
            if algorithm != "sha256":
                raise AssertionError(f"unexpected wheel RECORD algorithm: {algorithm}")
            installed = Path(str(distribution.locate_file(relative)))
            actual = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(installed.read_bytes()).digest()
                )
                .decode()
                .rstrip("=")
            )
            if actual != expected:
                raise AssertionError(f"installed file differs from wheel: {relative}")
            verified.append(relative)
    return {
        "direct_url": direct_url["url"],
        "wheel_record_verified_files": len(verified),
        "wheel_record_verification": "PASS",
    }


def public_record(record: Any) -> dict[str, str]:
    return {
        name: str(getattr(record, name))
        for name in (
            "record_id",
            "component_id_a",
            "component_id_b",
            "family",
            "value",
            "source_id",
            "locator",
            "domain_id",
        )
        if hasattr(record, name)
    }


def run(
    artifact: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    import epcsaft

    if sys.flags.isolated != 1:
        raise RuntimeError("campaign must run with Python isolated mode (-I)")
    if artifact.suffix != ".whl" or not artifact.is_file():
        raise ValueError("--artifact must name an installed provider wheel")
    artifact_hash = sha256(artifact)
    if artifact_hash != EXPECTED_ARTIFACT_SHA256:
        raise ValueError(f"unexpected provider artifact SHA-256: {artifact_hash}")
    module_path = Path(epcsaft.__file__).resolve()
    if "site-packages" not in module_path.parts:
        raise AssertionError(f"epcsaft is not installed: {module_path}")
    installed_wheel_verification = verify_installed_wheel(artifact)

    source_rows = read_csv(SOURCE)
    targets = {(row["salt"], row["observable"]): row for row in read_csv(TARGETS)}
    units = epcsaft.unit_registry
    bundles = {
        name: epcsaft.ParameterBundle.from_catalog(name, version=1)
        for name in {spec[0] for spec in SUPPORTED.values()}
    }
    component_ids = {
        name: tuple(component.component_id for component in bundle.components)
        for name, bundle in bundles.items()
    }
    derived_supported = {
        salt: spec
        for salt, spec in SUPPORTED.items()
        if "water" in component_ids[spec[0]]
        and all(component in component_ids[spec[0]] for component in spec[1:])
    }
    if derived_supported != SUPPORTED:
        raise AssertionError("public component catalogs do not cover expected salts")
    public_pair_records = [
        {"bundle": name, **public_record(record)}
        for name, bundle in bundles.items()
        for record in bundle.records
        if getattr(record, "family", None) == "k_ij"
    ]
    output_rows: list[dict[str, Any]] = []
    fingerprints: dict[str, str] = {}
    reference_diagnostics: dict[str, dict[str, float]] = {}
    predictions: dict[tuple[str, float, str], float] = {}
    molality_state_capabilities: dict[str, dict[str, bool]] = {}

    for salt, (bundle_name, cation, anion) in SUPPORTED.items():
        bundle = bundles[bundle_name]
        parameters = bundle.select(("water", cation, anion))
        fingerprints[salt] = parameters.fingerprint
        reference = epcsaft.EPCSAFT(parameters).reference_state(
            temperature=TEMPERATURE_K * units.kelvin,
            pressure=PRESSURE_MPA * units.megapascal,
            solvent_mole_fractions=(1.0, 0.0, 0.0),
            phase="liquid",
        )
        reference_diagnostics[salt] = {
            "reference_molality_mol_kg": reference.reference_molality.to(
                "mole / kilogram"
            ).magnitude,
            "log_fugacity_convergence_error": reference.convergence_error,
        }
        for row in source_rows:
            if row["salt"] != salt:
                continue
            molality = float(row["molality_mol_kg"])
            molality_state = reference.at_molality(
                molality * units.mole / units.kilogram
            )
            if bundle_name not in molality_state_capabilities:
                molality_state_capabilities[bundle_name] = {
                    "mean_ionic_activity_coefficient_molality": hasattr(
                        molality_state,
                        "mean_ionic_activity_coefficient_molality",
                    ),
                    "practical_osmotic_coefficient_molality": hasattr(
                        molality_state,
                        "practical_osmotic_coefficient_molality",
                    ),
                }
            predictions[(salt, molality, "gamma_pm_m")] = (
                molality_state.mean_ionic_activity_coefficient_molality
            )
            phi = molality_state.practical_osmotic_coefficient_molality
            if phi is None:
                raise AssertionError(
                    f"public osmotic coefficient unavailable for {salt}"
                )
            predictions[(salt, molality, "osmotic_coefficient")] = phi

    for row in source_rows:
        salt = row["salt"]
        molality = float(row["molality_mol_kg"])
        for observable, column in (
            ("osmotic_coefficient", "osmotic_coefficient"),
            ("gamma_pm_m", "gamma_pm_m"),
        ):
            target = targets[(salt, observable)]
            source_exact = target["subset_status"] == "EXACT_HAMER_WU_SUBSET"
            if salt not in SUPPORTED:
                prediction = None
                artifact_status = "NOT_EVALUATED"
                blocker = "installed Provider has iodide species but no source-backed Li+/I- interaction"
            else:
                prediction = predictions[(salt, molality, observable)]
                artifact_status = "EVALUATED"
                blocker = ""
            observed = float(row[column])
            residual = None if prediction is None else prediction - observed
            relative_error = (
                None if residual is None else 100.0 * abs(residual / observed)
            )
            output_rows.append(
                {
                    "salt": salt,
                    "observable": observable,
                    "molality_mol_kg": molality,
                    "literature_value": observed,
                    "model_value": prediction,
                    "residual": residual,
                    "relative_abs_error_percent": relative_error,
                    "source_subset_status": target["subset_status"],
                    "exact_table8_row": str(source_exact).lower(),
                    "artifact_status": artifact_status,
                    "solver_status": "NOT_ADJUDICATED_PUBLIC_API_EXPOSES_NO_POINT_SOLVER_DIAGNOSTIC"
                    if prediction is not None
                    else "NOT_EVALUATED",
                    "numerical_status": "FINITE_OUTPUT_ONLY_NO_CONVERGENCE_CERTIFICATE"
                    if prediction is not None and math.isfinite(prediction)
                    else "NOT_EVALUATED",
                    "physical_status": "PASS_WITH_REPORTED_DOMAIN_PRESSURE_EXTRAPOLATION"
                    if prediction is not None
                    else "NOT_EVALUATED",
                    "blocker": blocker,
                    "parameter_fingerprint": fingerprints.get(salt, ""),
                }
            )

    comparison: list[dict[str, Any]] = []
    exact_evaluated_aads: list[float] = []
    for salt in SALTS:
        for observable in ("osmotic_coefficient", "gamma_pm_m"):
            target = targets[(salt, observable)]
            selected = [
                row
                for row in output_rows
                if row["salt"] == salt and row["observable"] == observable
            ]
            evaluated = [
                row for row in selected if row["artifact_status"] == "EVALUATED"
            ]
            current_aad = None
            if evaluated:
                current_aad = percent_aad(
                    [float(row["literature_value"]) for row in evaluated],
                    [float(row["model_value"]) for row in evaluated],
                )
                if target["subset_status"] == "EXACT_HAMER_WU_SUBSET":
                    exact_evaluated_aads.append(current_aad)
            comparison.append(
                {
                    "salt": salt,
                    "observable": observable,
                    "haslam_saft_gamma_mie_points": int(target["haslam_points"]),
                    "haslam_saft_gamma_mie_aad_percent": float(
                        target["haslam_aad_percent"]
                    ),
                    "current_epcsaft_points": len(evaluated),
                    "current_epcsaft_aad_percent": current_aad,
                    "comparison_status": "CROSS_EOS_EXACT_SOURCE_SUBSET"
                    if current_aad is not None
                    and target["subset_status"] == "EXACT_HAMER_WU_SUBSET"
                    else (
                        "CROSS_EOS_PARTIAL_SOURCE_GRID"
                        if current_aad is not None
                        else "NOT_EVALUATED"
                    ),
                    "source_subset_status": target["subset_status"],
                    "aad_method": "conventional_relative_percent_aad_method_assumption",
                }
            )

    invalid = [
        row
        for row in output_rows
        if row["artifact_status"] == "EVALUATED"
        and (
            not math.isfinite(float(row["model_value"]))
            or float(row["model_value"]) <= 0.0
        )
    ]
    receipt = {
        "schema_version": 1,
        "campaign_id": "haslam-2020-table8-cross-eos",
        "decision": "HASLAM_TABLE8_PARTIAL_SOURCE_COVERAGE",
        "campaign_decisions": {
            "EXACT_TABLE8_REPRODUCTION": {
                "status": "PARTIAL_138_SOURCE_ESTABLISHED_GAMMA_ROWS_EVALUATED",
                "scope": "only observable-specific Hamer-Wu subsets whose 23-row selection exactly matches Haslam Table 8",
                "phi": "NO_EXACT_HASLAM_SELECTED_ROWS_SOURCE_ESTABLISHED",
                "limitation": "not a same-model reproduction; current ePC-SAFT is compared cross-EOS with Haslam SAFT-gamma-Mie",
            },
            "PARTIAL_HAMER_WU_CROSS_EOS": {
                "status": "COMPLETE_FOR_368_PROVIDER_SUPPORTED_ROWS",
                "scope": "Phi and gamma on all 23 Hamer-Wu rows for eight source-complete installed salts",
                "phi": "EVALUATED_184_PARTIAL_SOURCE_GRID_ROWS",
                "iodides": "NAI_AND_KI_EVALUATED_LII_NOT_EVALUATED_MISSING_LI_I_INTERACTION",
            },
        },
        "artifact": {
            "filename": artifact.name,
            "sha256": artifact_hash,
            "provider_commit": "53b0b74bf5de86d459c49eb2cc7e75b7cfd4ce3e",
            "provider_tree": "1750d04a84f3733e62eb32fb859d323243dddce9",
            "distribution": metadata.distribution("epcsaft").metadata["Name"],
            "version": metadata.version("epcsaft"),
            "import_origin": str(module_path),
            **installed_wheel_verification,
        },
        "source_data": {
            "filename": SOURCE.name,
            "sha256": sha256(SOURCE),
            "rows": len(source_rows),
            "target_ledger_sha256": sha256(TARGETS),
            "source_ledger_sha256": sha256(SOURCE_LEDGER),
            "canonical_provider_source_binding": {
                "validation_commit": "8d34f64f42201a564f2fa958f3d8552650abc4da",
                "validation_tree": "bb4b2e60a966792a8d6bdf159055be625170cb98",
                "ledger_path": "data/haslam-2020-osmotic-provider-source-ledger.yaml",
                "ledger_sha256": "b12d592b7886e5b8701103c3a41f5b211b3b46b1f5b617f345bc5e3f793c3741",
                "source_row_path": "data/haslam-2020-osmotic-provider-source-row.csv",
                "source_row_sha256": "fa2e68e8bc1224f2c6d5b80ad79e6643a08b5944276274067084c40aee2b4f45",
                "role": "referenced canonical property-definition packet; not copied into this campaign",
            },
        },
        "conditions": {
            "temperature_K": TEMPERATURE_K,
            "pressure_MPa": PRESSURE_MPA,
            "molality_range_mol_kg": [0.001, 3.0],
            "basis": "formula-unit molality in water",
        },
        "bundle_fingerprints": {
            name: bundle.fingerprint for name, bundle in bundles.items()
        },
        "public_capability_evidence": {
            "component_ids": component_ids,
            "iodide_component_present": any(
                "iodide-anion" in ids for ids in component_ids.values()
            ),
            "derived_supported_salts": tuple(derived_supported),
            "queried_molality_state_attributes": molality_state_capabilities,
            "selected_k_ij_records": public_pair_records,
            "record_families": {
                name: sorted(
                    {
                        str(getattr(record, "family", "NO_FAMILY_ATTRIBUTE"))
                        for record in bundle.records
                    }
                )
                for name, bundle in bundles.items()
            },
        },
        "parameter_set_fingerprints": fingerprints,
        "reference_diagnostics": reference_diagnostics,
        "coverage": {
            "evaluated_rows": sum(
                row["artifact_status"] == "EVALUATED" for row in output_rows
            ),
            "not_evaluated_rows": sum(
                row["artifact_status"] == "NOT_EVALUATED" for row in output_rows
            ),
            "exact_table8_gamma_rows_evaluated": sum(
                row["artifact_status"] == "EVALUATED"
                and row["observable"] == "gamma_pm_m"
                and row["exact_table8_row"] == "true"
                for row in output_rows
            ),
            "exact_table8_phi_rows_evaluated": 0,
            "current_exact_source_subset_mean_aad_percent": math.fsum(
                exact_evaluated_aads
            )
            / len(exact_evaluated_aads),
        },
        "coverage_by_salt": {
            salt: {
                "gamma_pm_m": "EVALUATED"
                if salt in SUPPORTED
                else "NOT_EVALUATED_MISSING_LI_I_INTERACTION",
                "osmotic_coefficient": "EVALUATED"
                if salt in SUPPORTED
                else "NOT_EVALUATED_MISSING_LI_I_INTERACTION",
            }
            for salt in SALTS
        },
        "interaction_semantics": {
            "k_ij": "retained from queried public PairParameterRecord objects, including explicit published zeros",
            "l_ij": "ABSENT_FROM_PUBLIC_BUNDLE_RECORDS_NO_DEFAULT_INFERRED",
            "k_ij_hb": "ABSENT_FROM_PUBLIC_BUNDLE_RECORDS_NO_DEFAULT_INFERRED",
        },
        "decisions": {
            "artifact": "PASS",
            "source": "PARTIAL_SOURCE_COVERAGE",
            "solver": "NOT_ADJUDICATED_PUBLIC_API_EXPOSES_NO_POINT_SOLVER_DIAGNOSTIC",
            "numerical": "FINITE_OUTPUT_ONLY_NO_CONVERGENCE_CERTIFICATE"
            if not invalid
            else "FAIL_NONFINITE_OR_NONPOSITIVE_OUTPUT",
            "physical": "DESCRIPTIVE_PRESSURE_EXTRAPOLATION_1P01_BAR_VS_REPORTED_1_BAR_DOMAIN",
            "predictive": "DESCRIPTIVE_CROSS_EOS_NO_ACCEPTANCE_CUTOFF",
            "exact_table8_reproduction": "NOT_EVALUATED_FULL_TABLE",
        },
        "aad_method": {
            "formula": "100/n * sum(abs((model-experiment)/experiment))",
            "status": "method_assumption",
            "reason": "Haslam pointwise AAD equation was not located in the paper text or available source packet",
        },
        "execution": {
            "argv": sys.argv,
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "isolated_mode": bool(sys.flags.isolated),
            "cwd": str(Path.cwd()),
            "environment_recipe": "uv venv --python 3.13 <temp>/venv; uv pip install --python <temp>/venv/bin/python <exact-wheel>; <temp>/venv/bin/python -I campaigns/haslam_2020_table8.py ...",
        },
        "blockers": [
            "LiI lacks a published Li+/I- interaction and remains not evaluated",
            "exact NaCl and KBr gamma row selections unavailable",
            "exact Haslam Phi row-selection manifest unavailable",
        ],
    }
    return receipt, output_rows, comparison


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    args = parser.parse_args()
    receipt, rows, comparison = run(args.artifact.resolve())
    write_csv(args.rows, rows)
    write_csv(args.comparison, comparison)
    receipt["retained_outputs"] = {
        "rows_csv": {"path": str(args.rows), "sha256": sha256(args.rows)},
        "comparison_csv": {
            "path": str(args.comparison),
            "sha256": sha256(args.comparison),
        },
    }
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
