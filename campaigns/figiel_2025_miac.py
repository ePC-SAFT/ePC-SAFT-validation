"""Black-box Figiel 2025 aqueous MIAC campaign over an installed provider wheel."""

from __future__ import annotations

import argparse
import csv
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
from typing import Any

import epcsaft


TEMPERATURE_K = 298.15
PRESSURE_BAR = 1.0
DATA_PATH = Path(__file__).parents[1] / "data" / "hamer-wu-1972-aqueous-alkali-halides.csv"
SALT_COMPONENTS = {
    "LiCl": ("lithium-cation", "chloride-anion"),
    "NaCl": ("sodium-cation", "chloride-anion"),
    "KCl": ("potassium-cation", "chloride-anion"),
    "LiBr": ("lithium-cation", "bromide-anion"),
    "NaBr": ("sodium-cation", "bromide-anion"),
    "KBr": ("potassium-cation", "bromide-anion"),
}
PER_SALT_RMSE_MAX = 0.35
PER_SALT_MAX_ABS_MAX = 1.25
POOLED_RMSE_MAX = 0.17
FIRST_PREDICTION_MAX = 0.98


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_data(path: Path) -> list[dict[str, float | str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = [
            {
                "salt": row["salt"],
                "molality_mol_kg": float(row["molality_mol_kg"]),
                "gamma_pm_m": float(row["gamma_pm_m"]),
            }
            for row in csv.DictReader(stream)
        ]
    if len(rows) != 164 or {row["salt"] for row in rows} != set(SALT_COMPONENTS):
        raise AssertionError("unexpected Hamer--Wu campaign data shape")
    return rows


def metrics(errors: list[float]) -> dict[str, float]:
    return {
        "rmse": math.sqrt(math.fsum(error * error for error in errors) / len(errors)),
        "mae": math.fsum(abs(error) for error in errors) / len(errors),
        "bias": math.fsum(errors) / len(errors),
        "max_abs": max(abs(error) for error in errors),
    }


def run(artifact: Path, data_path: Path = DATA_PATH) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if artifact.suffix != ".whl" or not artifact.is_file():
        raise ValueError("--artifact must name the installed provider wheel")
    module_path = Path(epcsaft.__file__).resolve()
    if not {"site-packages", "dist-packages"}.intersection(module_path.parts):
        raise AssertionError(f"epcsaft is not installed: {module_path}")

    units = epcsaft.unit_registry
    source_rows = read_data(data_path)
    predictions: list[dict[str, Any]] = []
    fingerprints: dict[str, str] = {}
    reference_diagnostics: dict[str, dict[str, float]] = {}

    bundle = epcsaft.ParameterBundle.from_catalog(
        "figiel-2025-reference-electrolytes", version=1
    )
    for salt, (cation, anion) in SALT_COMPONENTS.items():
        parameters = bundle.select(("water", cation, anion))
        fingerprints[salt] = parameters.fingerprint
        eos = epcsaft.EPCSAFT(parameters)
        reference = eos.reference_state(
            temperature=TEMPERATURE_K * units.kelvin,
            pressure=PRESSURE_BAR * units.bar,
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
            observed = float(row["gamma_pm_m"])
            predicted = reference.at_molality(
                molality * units.mole / units.kilogram
            ).mean_ionic_activity_coefficient_molality
            error = predicted - observed
            predictions.append(
                {
                    "salt": salt,
                    "molality_mol_kg": molality,
                    "gamma_pm_m_literature": observed,
                    "gamma_pm_m_model": predicted,
                    "error": error,
                    "abs_error": abs(error),
                    "parameter_fingerprint": parameters.fingerprint,
                }
            )

    failures: list[str] = []
    per_salt: dict[str, dict[str, float | int]] = {}
    all_errors: list[float] = []
    for salt in SALT_COMPONENTS:
        selected = [row for row in predictions if row["salt"] == salt]
        errors = [float(row["error"]) for row in selected]
        all_errors.extend(errors)
        result = metrics(errors)
        per_salt[salt] = {"points": len(selected), **result}
        if result["rmse"] > PER_SALT_RMSE_MAX:
            failures.append(f"{salt} RMSE {result['rmse']:.8g} exceeds {PER_SALT_RMSE_MAX}")
        if result["max_abs"] > PER_SALT_MAX_ABS_MAX:
            failures.append(
                f"{salt} max abs error {result['max_abs']:.8g} exceeds {PER_SALT_MAX_ABS_MAX}"
            )
        if float(selected[0]["gamma_pm_m_model"]) >= FIRST_PREDICTION_MAX:
            failures.append(f"{salt} does not reproduce the initial MIAC decrease")

    invalid = [
        row
        for row in predictions
        if not math.isfinite(float(row["gamma_pm_m_model"]))
        or float(row["gamma_pm_m_model"]) <= 0.0
    ]
    if invalid:
        failures.append(f"{len(invalid)} predictions are nonfinite or nonpositive")
    pooled = metrics(all_errors)
    if pooled["rmse"] > POOLED_RMSE_MAX:
        failures.append(f"pooled RMSE {pooled['rmse']:.8g} exceeds {POOLED_RMSE_MAX}")

    distribution = metadata.distribution("epcsaft")
    receipt = {
        "schema_version": 1,
        "status": "passed" if not failures else "failed",
        "claim": "Figiel 2025 Figure 5 aqueous alkali-halide MIAC behavior through 6 mol/kg",
        "artifact": {
            "filename": artifact.name,
            "sha256": sha256(artifact),
            "distribution": distribution.metadata["Name"],
            "version": distribution.version,
            "module_path_class": "installed-site-packages",
        },
        "source_data": {
            "filename": data_path.name,
            "sha256": sha256(data_path),
            "rows": len(source_rows),
            "doi": "10.1063/1.3253108",
            "tables": {"LiCl": 9, "LiBr": 10, "NaCl": 16, "NaBr": 17, "KCl": 28, "KBr": 29},
        },
        "conditions": {
            "temperature_K": TEMPERATURE_K,
            "pressure_bar": PRESSURE_BAR,
            "solvent": "water",
            "molality_range_mol_kg": [0.001, 6.0],
        },
        "parameter_set_fingerprints": fingerprints,
        "reference_diagnostics": reference_diagnostics,
        "metrics": {"per_salt": per_salt, "pooled": {"points": len(all_errors), **pooled}},
        "tolerances": {
            "per_salt_rmse_max": PER_SALT_RMSE_MAX,
            "per_salt_max_abs_max": PER_SALT_MAX_ABS_MAX,
            "pooled_rmse_max": POOLED_RMSE_MAX,
            "first_prediction_max": FIRST_PREDICTION_MAX,
        },
        "failures": failures,
        "limits": [
            "The Figiel ion--water and ion--ion interaction parameters were fitted "
            "to aqueous MIAC data; this campaign is physical reproduction evidence, "
            "not an independent prediction set.",
            "NaBr also informed the fitted water solvation factor in Figiel 2025.",
            "Only Hamer--Wu points overlapping the Figiel Figure 5 model range "
            "through 6 mol/kg are retained.",
            "A passed campaign does not establish behavior for other salts, solvents, "
            "temperatures, pressures, equilibria, or regressions.",
            "A passed campaign does not transfer runtime authority.",
        ],
    }
    return receipt, predictions


def write_predictions(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    arguments = parser.parse_args()
    receipt, predictions = run(arguments.artifact.resolve())
    arguments.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_predictions(arguments.predictions, predictions)
    if receipt["status"] != "passed":
        raise SystemExit("MIAC campaign failed; inspect the retained receipt")


if __name__ == "__main__":
    main()
