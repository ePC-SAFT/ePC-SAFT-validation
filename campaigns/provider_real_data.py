"""Two small real-data campaigns over one installed provider wheel."""

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


ROOT = Path(__file__).parents[1]
ACTIVITY_DATA = ROOT / "data" / "esteso-1989-water-ethanol-nacl.csv"
DENSITY_DATA = ROOT / "data" / "held-2012-ethanol-salt-density.csv"
PURE_ETHANOL_DATA = ROOT / "data" / "held-2012-pure-ethanol-density.csv"
TEMPERATURE_K = 298.15
PRESSURE_BAR = 1.0
WATER_MOLAR_MASS_KG_MOL = 0.0180153
ETHANOL_MOLAR_MASS_KG_MOL = 0.046069
ACTIVITY_POOLED_RMSE_MAX = 0.05
ACTIVITY_SERIES_RMSE_MAX = 0.10
ACTIVITY_MAX_ABS_MAX = 0.12
DENSITY_POOLED_RMSE_MAX_KG_M3 = 12.0
DENSITY_MAX_ABS_MAX_KG_M3 = 20.0
DENSITY_MAX_RELATIVE_MAX = 0.025
DENSITY_PRESSURE_RESIDUAL_MAX_PA = 1.0e-3
PURE_ETHANOL_RELATIVE_ERROR_MAX = 0.02
SALT_COMPONENTS = {
    "LiCl": ("lithium-cation", "chloride-anion"),
    "LiBr": ("lithium-cation", "bromide-anion"),
    "NaBr": ("sodium-cation", "bromide-anion"),
}
COMPONENT_MOLAR_MASSES_KG_MOL = {
    "ethanol": ETHANOL_MOLAR_MASS_KG_MOL,
    "lithium-cation": 0.00694,
    "sodium-cation": 0.02298,
    "chloride-anion": 0.03545,
    "bromide-anion": 0.0799,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def metrics(errors: list[float]) -> dict[str, float]:
    return {
        "rmse": math.sqrt(math.fsum(error * error for error in errors) / len(errors)),
        "mae": math.fsum(abs(error) for error in errors) / len(errors),
        "bias": math.fsum(errors) / len(errors),
        "max_abs": max(abs(error) for error in errors),
    }


def artifact_record(artifact: Path) -> dict[str, str]:
    if artifact.suffix != ".whl" or not artifact.is_file():
        raise ValueError("--artifact must name the installed provider wheel")
    module_path = Path(epcsaft.__file__).resolve()
    if not {"site-packages", "dist-packages"}.intersection(module_path.parts):
        raise AssertionError(f"epcsaft is not installed: {module_path}")
    distribution = metadata.distribution("epcsaft")
    return {
        "filename": artifact.name,
        "sha256": sha256(artifact),
        "distribution": distribution.metadata["Name"],
        "version": distribution.version,
        "module_path_class": "installed-site-packages",
    }


def read_activity_data(path: Path) -> list[dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = [
            {
                "ethanol_mass_percent": float(row["ethanol_mass_percent"]),
                "molality_mol_kg": float(row["molality_mol_kg"]),
                "gamma_pm_m": float(row["gamma_pm_m"]),
            }
            for row in csv.DictReader(stream)
        ]
    if len(rows) != 92 or {row["ethanol_mass_percent"] for row in rows} != {
        20.0,
        40.0,
        60.0,
        80.0,
    }:
        raise AssertionError("unexpected Esteso Table I campaign data shape")
    return rows


def run_activity(
    artifact: dict[str, str], data_path: Path = ACTIVITY_DATA
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    units = epcsaft.unit_registry
    source_rows = read_activity_data(data_path)
    parameters = epcsaft.ParameterBundle.from_catalog(
        "figiel-2025-reference-electrolytes", version=1
    ).select(("water", "ethanol", "sodium-cation", "chloride-anion"))
    eos = epcsaft.EPCSAFT(parameters)
    predictions: list[dict[str, Any]] = []
    reference_diagnostics: dict[str, dict[str, float]] = {}

    for ethanol_mass_percent in (20.0, 40.0, 60.0, 80.0):
        ethanol_mass_fraction = ethanol_mass_percent / 100.0
        water_moles = (1.0 - ethanol_mass_fraction) / WATER_MOLAR_MASS_KG_MOL
        ethanol_moles = ethanol_mass_fraction / ETHANOL_MOLAR_MASS_KG_MOL
        solvent_moles = water_moles + ethanol_moles
        water_mole_fraction = water_moles / solvent_moles
        ethanol_mole_fraction = ethanol_moles / solvent_moles
        reference = eos.reference_state(
            temperature=TEMPERATURE_K * units.kelvin,
            pressure=PRESSURE_BAR * units.bar,
            solvent_mole_fractions=(
                water_mole_fraction,
                ethanol_mole_fraction,
                0.0,
                0.0,
            ),
            phase="liquid",
        )
        reference_diagnostics[str(int(ethanol_mass_percent))] = {
            "water_mole_fraction": water_mole_fraction,
            "ethanol_mole_fraction": ethanol_mole_fraction,
            "reference_molality_mol_kg": reference.reference_molality.to(
                "mole / kilogram"
            ).magnitude,
            "log_fugacity_convergence_error": reference.convergence_error,
        }
        for row in source_rows:
            if row["ethanol_mass_percent"] != ethanol_mass_percent:
                continue
            predicted = reference.at_molality(
                row["molality_mol_kg"] * units.mole / units.kilogram
            ).mean_ionic_activity_coefficient_molality
            error = predicted - row["gamma_pm_m"]
            predictions.append(
                {
                    "ethanol_mass_percent": int(ethanol_mass_percent),
                    "molality_mol_kg": row["molality_mol_kg"],
                    "gamma_pm_m_literature": row["gamma_pm_m"],
                    "gamma_pm_m_model": predicted,
                    "error": error,
                    "abs_error": abs(error),
                    "parameter_fingerprint": parameters.fingerprint,
                }
            )

    failures: list[str] = []
    all_errors = [float(row["error"]) for row in predictions]
    per_series: dict[str, dict[str, float | int]] = {}
    for ethanol_mass_percent in (20, 40, 60, 80):
        selected = [
            row
            for row in predictions
            if row["ethanol_mass_percent"] == ethanol_mass_percent
        ]
        result = metrics([float(row["error"]) for row in selected])
        per_series[str(ethanol_mass_percent)] = {"points": len(selected), **result}
        if result["rmse"] > ACTIVITY_SERIES_RMSE_MAX:
            failures.append(
                f"{ethanol_mass_percent} wt% ethanol RMSE {result['rmse']:.8g} "
                f"exceeds {ACTIVITY_SERIES_RMSE_MAX}"
            )
    pooled = metrics(all_errors)
    if pooled["rmse"] > ACTIVITY_POOLED_RMSE_MAX:
        failures.append(
            f"pooled RMSE {pooled['rmse']:.8g} exceeds {ACTIVITY_POOLED_RMSE_MAX}"
        )
    if pooled["max_abs"] > ACTIVITY_MAX_ABS_MAX:
        failures.append(
            f"max abs error {pooled['max_abs']:.8g} exceeds {ACTIVITY_MAX_ABS_MAX}"
        )
    if any(
        not math.isfinite(float(row["gamma_pm_m_model"]))
        or float(row["gamma_pm_m_model"]) <= 0.0
        for row in predictions
    ):
        failures.append("one or more activity predictions are nonfinite or nonpositive")

    receipt = {
        "schema_version": 1,
        "status": "passed" if not failures else "failed",
        "claim": "NaCl MIAC in water-ethanol mixtures at 298.15 K",
        "artifact": artifact,
        "source_data": {
            "filename": data_path.name,
            "sha256": sha256(data_path),
            "rows": len(source_rows),
            "citation": "Esteso et al., Journal of Solution Chemistry 18 (1989) 277-288",
            "table": "I",
        },
        "conditions": {
            "temperature_K": TEMPERATURE_K,
            "pressure_bar": PRESSURE_BAR,
            "ethanol_mass_percent": [20, 40, 60, 80],
        },
        "parameter_set_fingerprint": parameters.fingerprint,
        "reference_diagnostics": reference_diagnostics,
        "metrics": {
            "per_ethanol_mass_percent": per_series,
            "pooled": {"points": len(all_errors), **pooled},
        },
        "tolerances": {
            "per_series_rmse_max": ACTIVITY_SERIES_RMSE_MAX,
            "pooled_rmse_max": ACTIVITY_POOLED_RMSE_MAX,
            "max_abs_max": ACTIVITY_MAX_ABS_MAX,
        },
        "failures": failures,
        "limits": [
            "The retained values are direct Table I experiments, not digitized figure points.",
            "The one-bar model condition approximates the experimental ambient pressure.",
            "The tolerance is a model-accuracy gate, not experimental uncertainty.",
            "Passing does not establish other salts, solvent compositions, temperatures, "
            "pressures, equilibria, or regressions.",
        ],
    }
    return receipt, predictions


def read_density_data(path: Path) -> list[dict[str, float | str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = [
            {
                "salt": row["salt"],
                "molality_mol_kg": float(row["molality_mol_kg"]),
                "density_kg_m3": float(row["density_kg_m3"]),
            }
            for row in csv.DictReader(stream)
        ]
    if len(rows) != 7 or {row["salt"] for row in rows} != set(SALT_COMPONENTS):
        raise AssertionError("unexpected Held Table 1 campaign data shape")
    return rows


def run_density(
    artifact: dict[str, str], data_path: Path = DENSITY_DATA
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    units = epcsaft.unit_registry
    source_rows = read_density_data(data_path)
    bundle = epcsaft.ParameterBundle.from_catalog(
        "figiel-2025-reference-electrolytes", version=1
    )
    predictions: list[dict[str, Any]] = []
    fingerprints: dict[str, str] = {}
    failures: list[str] = []

    for salt, (cation, anion) in SALT_COMPONENTS.items():
        components = ("ethanol", cation, anion)
        parameters = bundle.select(components)
        fingerprints[salt] = parameters.fingerprint
        eos = epcsaft.EPCSAFT(parameters)
        for row in source_rows:
            if row["salt"] != salt:
                continue
            molality = float(row["molality_mol_kg"])
            ethanol_moles = 1.0 / ETHANOL_MOLAR_MASS_KG_MOL
            total_moles = ethanol_moles + 2.0 * molality
            mole_fractions = (
                ethanol_moles / total_moles,
                molality / total_moles,
                molality / total_moles,
            )
            result = eos.evaluate(
                temperature=TEMPERATURE_K * units.kelvin,
                pressure=PRESSURE_BAR * units.bar,
                mole_fractions=mole_fractions,
                phase="liquid",
            )
            diagnostics = result.density_diagnostics
            if diagnostics is None:
                raise AssertionError(
                    "specified-pressure state returned no density diagnostics"
                )
            average_molar_mass = math.fsum(
                fraction * COMPONENT_MOLAR_MASSES_KG_MOL[component]
                for fraction, component in zip(mole_fractions, components, strict=True)
            )
            predicted = (
                result.molar_density.to("mole / meter ** 3").magnitude
                * average_molar_mass
            )
            observed = float(row["density_kg_m3"])
            error = predicted - observed
            pressure_residual = abs(
                diagnostics.pressure_residual.to("pascal").magnitude
            )
            if not diagnostics.stable:
                failures.append(
                    f"{salt} at {molality} mol/kg returned an unstable root"
                )
            if pressure_residual > DENSITY_PRESSURE_RESIDUAL_MAX_PA:
                failures.append(
                    f"{salt} at {molality} mol/kg pressure residual {pressure_residual:.8g} Pa "
                    f"exceeds {DENSITY_PRESSURE_RESIDUAL_MAX_PA} Pa"
                )
            predictions.append(
                {
                    "salt": salt,
                    "molality_mol_kg": molality,
                    "density_kg_m3_literature": observed,
                    "density_kg_m3_model": predicted,
                    "error_kg_m3": error,
                    "abs_error_kg_m3": abs(error),
                    "relative_error": error / observed,
                    "root_branch": diagnostics.branch,
                    "root_stable": diagnostics.stable,
                    "pressure_residual_pa": pressure_residual,
                    "pressure_density_derivative_pa_m3_mol": diagnostics.pressure_density_derivative.to(
                        "pascal * meter ** 3 / mole"
                    ).magnitude,
                    "parameter_fingerprint": parameters.fingerprint,
                }
            )

    all_errors = [float(row["error_kg_m3"]) for row in predictions]
    pooled = metrics(all_errors)
    per_salt: dict[str, dict[str, float | int]] = {}
    for salt in SALT_COMPONENTS:
        selected = [row for row in predictions if row["salt"] == salt]
        result = metrics([float(row["error_kg_m3"]) for row in selected])
        per_salt[salt] = {"points": len(selected), **result}
        if result["max_abs"] > DENSITY_MAX_ABS_MAX_KG_M3:
            failures.append(
                f"{salt} max abs error {result['max_abs']:.8g} kg/m3 "
                f"exceeds {DENSITY_MAX_ABS_MAX_KG_M3} kg/m3"
            )
    if pooled["rmse"] > DENSITY_POOLED_RMSE_MAX_KG_M3:
        failures.append(
            f"pooled RMSE {pooled['rmse']:.8g} kg/m3 exceeds "
            f"{DENSITY_POOLED_RMSE_MAX_KG_M3} kg/m3"
        )
    max_relative = max(abs(float(row["relative_error"])) for row in predictions)
    if max_relative > DENSITY_MAX_RELATIVE_MAX:
        failures.append(
            f"max relative error {max_relative:.8g} exceeds {DENSITY_MAX_RELATIVE_MAX}"
        )

    receipt = {
        "schema_version": 1,
        "status": "passed" if not failures else "failed",
        "claim": "LiCl, LiBr, and NaBr solution densities in ethanol at 298.15 K",
        "artifact": artifact,
        "source_data": {
            "filename": data_path.name,
            "sha256": sha256(data_path),
            "rows": len(source_rows),
            "doi": "10.1016/j.ces.2011.09.040",
            "table": "1",
        },
        "conditions": {
            "temperature_K": TEMPERATURE_K,
            "experimental_pressure": "ambient",
            "model_pressure_bar": PRESSURE_BAR,
            "solvent": "ethanol",
        },
        "parameter_set_fingerprints": fingerprints,
        "metrics": {
            "per_salt": per_salt,
            "pooled": {"points": len(all_errors), **pooled},
            "max_relative_error": max_relative,
        },
        "tolerances": {
            "pooled_rmse_max_kg_m3": DENSITY_POOLED_RMSE_MAX_KG_M3,
            "per_salt_max_abs_max_kg_m3": DENSITY_MAX_ABS_MAX_KG_M3,
            "max_relative_error": DENSITY_MAX_RELATIVE_MAX,
            "pressure_residual_max_pa": DENSITY_PRESSURE_RESIDUAL_MAX_PA,
        },
        "failures": failures,
        "limits": [
            "The retained values are direct Table 1 experiments, not digitized figure points.",
            "One bar approximates the reported ambient pressure.",
            "The density tolerances measure model accuracy and are intentionally much wider "
            "than the reported 0.0015 kg/m3 maximum instrument uncertainty.",
            "Passing does not establish other salts, concentrations, solvents, temperatures, "
            "pressures, equilibria, or regressions.",
        ],
    }
    return receipt, predictions


def run_pure_ethanol_density(
    artifact: dict[str, str], data_path: Path = PURE_ETHANOL_DATA
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with data_path.open(newline="", encoding="utf-8") as stream:
        source_rows = list(csv.DictReader(stream))
    if len(source_rows) != 1:
        raise AssertionError("unexpected Held pure-ethanol campaign data shape")

    units = epcsaft.unit_registry
    parameters = epcsaft.ParameterBundle.from_catalog(
        "figiel-2025-reference-electrolytes", version=1
    ).select(("ethanol",))
    result = epcsaft.EPCSAFT(parameters).evaluate(
        temperature=float(source_rows[0]["temperature_K"]) * units.kelvin,
        pressure=PRESSURE_BAR * units.bar,
        mole_fractions=(1.0,),
        phase="liquid",
    )
    diagnostics = result.density_diagnostics
    if diagnostics is None:
        raise AssertionError("specified-pressure state returned no density diagnostics")
    observed = float(source_rows[0]["density_kg_m3"])
    predicted = (
        result.molar_density.to("mole / meter ** 3").magnitude
        * ETHANOL_MOLAR_MASS_KG_MOL
    )
    error = predicted - observed
    relative_error = error / observed
    pressure_residual = abs(diagnostics.pressure_residual.to("pascal").magnitude)
    failures: list[str] = []
    if result.association >= 0.0:
        failures.append("neutral ethanol state did not activate association")
    if result.debye_huckel != 0.0 or result.born_ssm_ds != 0.0:
        failures.append("neutral ethanol state activated an ionic contribution")
    if not diagnostics.stable or diagnostics.branch != "liquid":
        failures.append("pure ethanol did not return a certified liquid root")
    if pressure_residual > DENSITY_PRESSURE_RESIDUAL_MAX_PA:
        failures.append(
            f"pressure residual {pressure_residual:.8g} Pa exceeds "
            f"{DENSITY_PRESSURE_RESIDUAL_MAX_PA} Pa"
        )
    if abs(relative_error) > PURE_ETHANOL_RELATIVE_ERROR_MAX:
        failures.append(
            f"relative density error {relative_error:.8g} exceeds "
            f"{PURE_ETHANOL_RELATIVE_ERROR_MAX}"
        )

    predictions = [
        {
            "temperature_K": float(source_rows[0]["temperature_K"]),
            "density_kg_m3_literature": observed,
            "density_kg_m3_model": predicted,
            "error_kg_m3": error,
            "relative_error": relative_error,
            "association_helmholtz": result.association,
            "root_branch": diagnostics.branch,
            "root_stable": diagnostics.stable,
            "pressure_residual_pa": pressure_residual,
            "parameter_fingerprint": parameters.fingerprint,
        }
    ]
    receipt = {
        "schema_version": 1,
        "status": "passed" if not failures else "failed",
        "claim": "pure ethanol liquid density from the neutral-associating EOS path",
        "artifact": artifact,
        "source_data": {
            "filename": data_path.name,
            "sha256": sha256(data_path),
            "rows": 1,
            "doi": "10.1016/j.ces.2011.09.040",
            "section": "2.2 Solution densities",
        },
        "conditions": {
            "temperature_K": float(source_rows[0]["temperature_K"]),
            "experimental_pressure": "ambient",
            "model_pressure_bar": PRESSURE_BAR,
        },
        "parameter_set_fingerprint": parameters.fingerprint,
        "metrics": predictions[0],
        "tolerances": {
            "relative_error_max": PURE_ETHANOL_RELATIVE_ERROR_MAX,
            "pressure_residual_max_pa": DENSITY_PRESSURE_RESIDUAL_MAX_PA,
        },
        "failures": failures,
        "limits": [
            "The retained value is the authors' direct mean measurement, not a digitized point or evaluated database value.",
            "The two-percent gate is a model-accuracy tolerance; the source reports a much smaller instrument uncertainty.",
            "Passing establishes one neutral-associating density state, not saturation or phase-equilibrium capability.",
        ],
    }
    return receipt, predictions


def write_predictions(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    artifact = artifact_record(arguments.artifact.resolve())
    output_dir = arguments.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    activity_receipt, activity_predictions = run_activity(artifact)
    density_receipt, density_predictions = run_density(artifact)
    pure_ethanol_receipt, pure_ethanol_predictions = run_pure_ethanol_density(artifact)
    write_predictions(
        output_dir / "esteso-1989-water-ethanol-nacl.csv", activity_predictions
    )
    write_receipt(output_dir / "esteso-1989-water-ethanol-nacl.json", activity_receipt)
    write_predictions(
        output_dir / "held-2012-ethanol-salt-density.csv", density_predictions
    )
    write_receipt(output_dir / "held-2012-ethanol-salt-density.json", density_receipt)
    write_predictions(
        output_dir / "held-2012-pure-ethanol-density.csv", pure_ethanol_predictions
    )
    write_receipt(
        output_dir / "held-2012-pure-ethanol-density.json", pure_ethanol_receipt
    )
    if any(
        receipt["status"] != "passed"
        for receipt in (activity_receipt, density_receipt, pure_ethanol_receipt)
    ):
        raise SystemExit("real-data campaign failed; inspect the retained receipts")


if __name__ == "__main__":
    main()
