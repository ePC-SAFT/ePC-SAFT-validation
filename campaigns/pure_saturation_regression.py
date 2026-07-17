#!/usr/bin/env python3
"""Validate exact installed pure-saturation regression artifacts."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib
import importlib.metadata
import json
import math
import platform
import statistics
import sys
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path
from typing import Any


CAMPAIGN_ID = "consumer-slice-2-pure-saturation-regression-v1"
PROVIDER_SHA256 = "f92f79c8d6f614660e5c201b7061c9b02b5cd1a25a4ed8c8fee0b59adaabf2bf"
REGRESSION_SHA256 = "e4bf7ec673a9e6f5b70ce1ef39d9f28a73c709cf38974019c09790cc4f9bfa49"
REGRESSION_IMPLEMENTATION_COMMIT = "50a488b91686388432fd50a0d6bfc5b15825e4f1"
REGRESSION_EVIDENCE_COMMIT = "1c0c8bdbabbed20795cb2d093a7d15ee03accedb"
ETHANE_RECEIPT_SHA256 = "e4729aa0d089973c1041e68b8b0abd028a440a04a0b4a47da2b7ccdbcb6cf529"
ETHANE_RECEIPT_SUBJECT_SHA256 = "a324cc2ba665b06c84660e6d815c7d39d1f898640a3b3fcc5833c10dc84b1f4f"
METHANE_ACCEPTED_RECEIPT = "promotion-0020-regression-methane-saturation-v1"

EXPECTED_DATASETS = {
    "methane": {
        "dataset_id": "nist-webbook-methane-saturation-100-180-k-v1",
        "source_sha256": "a5e16df3bf8ec78483fc340782cddc89ab8b284a9f6dfaecd6cda3ffde579227",
        "packaged_sha256": "dec64d5a6cac414a4a92393a0d728fa27c02135c6a159d0d1881d7b6dde6d26c",
        "training": (110.0, 130.0, 150.0, 170.0),
        "held_out": (100.0, 120.0, 140.0, 160.0, 180.0),
        "stress": (),
    },
    "ethane": {
        "dataset_id": "nist-webbook-ethane-saturation-100-280-k-v1",
        "source_sha256": "ed09b8781acfb7025ca505878b884f6353ddd9f3f4bd7aae2e6df88bbe847a67",
        "packaged_sha256": "b01333e827933c0a7148672c8ae3eef78393320c0d18f2c4d5a0fc40d9bef6b2",
        "training": (140.0, 180.0, 220.0, 260.0),
        "held_out": (120.0, 160.0, 200.0, 240.0),
        "stress": (100.0, 280.0),
    },
}

METHANE_PARITY = {
    "parameters": (0.9932081279826167, 3.717121437945618, 150.4888402511307),
    "initial_cost": 14340.021563034428,
    "final_cost": 4.798586497669576e-6,
    "predictions": (
        (100.0, 34626.07915160773, 436.84483289550474),
        (110.0, 88224.60866583801, 423.3969791365449),
        (120.0, 191083.41254773695, 409.3407614313209),
        (130.0, 366384.5067925305, 394.34823157350235),
        (140.0, 639981.9267634666, 377.95195367291694),
        (150.0, 1039603.4624909018, 359.43578939218077),
        (160.0, 1594405.452356535, 337.5806133970321),
        (170.0, 2334648.4404434026, 309.96652881184707),
        (180.0, 3290375.174877589, 270.4239126820564),
    ),
}

ROW_FIELDS = (
    "component_id",
    "row_id",
    "partition",
    "temperature_k",
    "observed_pressure_pa",
    "start_predicted_pressure_pa",
    "fitted_predicted_pressure_pa",
    "start_pressure_relative_error",
    "fitted_pressure_relative_error",
    "observed_liquid_density_kg_m3",
    "start_predicted_liquid_density_kg_m3",
    "fitted_predicted_liquid_density_kg_m3",
    "start_liquid_density_relative_error",
    "fitted_liquid_density_relative_error",
    "reporting_solver_status",
    "reporting_physical_status",
    "provider_parameter_fingerprint",
    "fitted_parameter_sha256",
    "provider_wheel_sha256",
    "regression_wheel_sha256",
)

PARAMETER_FIELDS = (
    "component_id",
    "name",
    "unit",
    "start",
    "fitted",
    "movement",
    "lower_bound",
    "upper_bound",
    "active_bound",
    "fitted_parameter_sha256",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require_wheel(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path.suffix != ".whl" or not path.is_file():
        raise ValueError(f"wheel path is not an existing .whl file: {path}")
    return path


def _wheel_metadata(wheel: Path) -> tuple[str, str, list[tuple[str, str]]]:
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        message = BytesParser().parsebytes(archive.read(metadata_name))
        record_name = metadata_name.removesuffix("METADATA") + "RECORD"
        record_rows = list(csv.reader(archive.read(record_name).decode("utf-8").splitlines()))
    return str(message["Name"]), str(message["Version"]), [(row[0], row[1]) for row in record_rows]


def verify_installed_wheel(wheel: Path, expected_distribution: str, expected_sha256: str) -> dict[str, Any]:
    observed_sha256 = sha256_file(wheel)
    if observed_sha256 != expected_sha256:
        raise ValueError(
            f"{expected_distribution} wheel SHA-256 mismatch: {observed_sha256} != {expected_sha256}"
        )
    wheel_name, wheel_version, record_rows = _wheel_metadata(wheel)
    if wheel_name != expected_distribution:
        raise ValueError(f"wheel distribution is {wheel_name!r}, expected {expected_distribution!r}")
    distribution = importlib.metadata.distribution(expected_distribution)
    if distribution.version != wheel_version:
        raise ValueError("installed distribution version does not match supplied wheel")
    checked = 0
    for member, encoded_hash in record_rows:
        if not encoded_hash:
            continue
        algorithm, expected = encoded_hash.split("=", 1)
        if algorithm != "sha256":
            raise ValueError(f"unsupported RECORD hash algorithm: {algorithm}")
        installed = Path(distribution.locate_file(member)).resolve()
        if not installed.is_file():
            raise ValueError(f"installed wheel member is missing: {member}")
        observed = base64.urlsafe_b64encode(hashlib.sha256(installed.read_bytes()).digest()).rstrip(b"=").decode()
        if observed != expected:
            raise ValueError(f"installed wheel member hash mismatch: {member}")
        checked += 1
    if checked == 0:
        raise ValueError("wheel RECORD contained no verifiable members")
    return {
        "path": str(wheel),
        "sha256": observed_sha256,
        "distribution": wheel_name,
        "version": wheel_version,
        "installed_root": str(Path(distribution.locate_file("")).resolve()),
        "record_members_verified": checked,
    }


def _verify_module_origin(module: Any, installed_root: str) -> str:
    origin = Path(module.__file__).resolve()
    if not origin.is_relative_to(Path(installed_root)):
        raise RuntimeError(f"module import did not originate in the verified installed artifact: {origin}")
    return str(origin)


def _environment(origins: dict[str, str]) -> dict[str, Any]:
    distributions = sorted(
        {
            (str(item.metadata["Name"]), item.version)
            for item in importlib.metadata.distributions()
            if item.metadata["Name"]
        }
    )
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "python_executable_sha256": sha256_file(Path(sys.executable).resolve()),
        "python_isolated": bool(sys.flags.isolated),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "implementation": platform.python_implementation(),
        "installed_distributions": [
            {"name": name, "version": version} for name, version in distributions
        ],
        "imports": origins,
    }


def _partition_contract(dataset: Any, expected: dict[str, Any]) -> None:
    observed = {
        "dataset_id": dataset.dataset_id,
        "source_sha256": dataset.source.data_sha256,
        "packaged_sha256": dataset.source.packaged_data_sha256,
        "training": tuple(dataset.training_temperatures_k),
        "held_out": tuple(dataset.held_out_temperatures_k),
        "stress": tuple(dataset.stress_temperatures_k),
    }
    if observed != expected:
        raise RuntimeError(f"source partition contract changed: {observed!r}")


def _parity_status(result: Any) -> tuple[str, list[str]]:
    failures: list[str] = []
    for observed, expected in zip(
        (item.final for item in result.parameters), METHANE_PARITY["parameters"], strict=True
    ):
        if not math.isclose(observed, expected, rel_tol=2.0e-11, abs_tol=2.0e-11):
            failures.append(f"parameter parity failed: {observed} != {expected}")
    if not math.isclose(result.initial_cost, METHANE_PARITY["initial_cost"], rel_tol=2.0e-12):
        failures.append("initial-cost parity failed")
    if not math.isclose(result.final_cost, METHANE_PARITY["final_cost"], rel_tol=2.0e-9):
        failures.append("final-cost parity failed")
    for observed, expected in zip(result.reporting_rows, METHANE_PARITY["predictions"], strict=True):
        values = (observed.temperature_k, observed.predicted_pressure_pa, observed.predicted_liquid_density_kg_m3)
        if any(
            not math.isclose(a, b, rel_tol=2.0e-9, abs_tol=2.0e-9)
            for a, b in zip(values, expected, strict=True)
        ):
            failures.append(f"reporting parity failed for {observed.row_id}")
    return ("PASS" if not failures else "FAIL"), failures


def _metrics(rows: list[dict[str, Any]], partition: str) -> dict[str, float | int]:
    selected = [row for row in rows if row["partition"] == partition]
    pressure = [float(row["fitted_pressure_relative_error"]) for row in selected]
    density = [float(row["fitted_liquid_density_relative_error"]) for row in selected]
    return {
        "rows": len(selected),
        "pressure_relative_error_rms": math.sqrt(statistics.fmean(value * value for value in pressure)),
        "pressure_relative_error_max_abs": max(map(abs, pressure)),
        "liquid_density_relative_error_rms": math.sqrt(statistics.fmean(value * value for value in density)),
        "liquid_density_relative_error_max_abs": max(map(abs, density)),
    }


def validate_result_contract(receipt: dict[str, Any], rows: list[dict[str, Any]], parameters: list[dict[str, Any]]) -> None:
    required = {"solver_status", "numerical_status", "local_physical_status", "predictive_status", "artifact_admission"}
    for component in receipt.get("components", []):
        missing = required.difference(component)
        if missing:
            raise ValueError(f"component status is missing {sorted(missing)[0]}")
    if len(receipt.get("components", [])) != 2:
        raise ValueError("receipt must contain methane and ethane component statuses")
    if len(rows) != 19 or len(parameters) != 6:
        raise ValueError("result row counts do not match the frozen methane/ethane datasets")
    if any(not math.isfinite(float(row["fitted_predicted_pressure_pa"])) for row in rows):
        raise ValueError("nonfinite fitted pressure prediction")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-wheel", required=True, type=require_wheel)
    parser.add_argument("--regression-wheel", required=True, type=require_wheel)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not sys.flags.isolated:
        raise RuntimeError("campaign must run with Python isolated mode (-I)")
    provider = verify_installed_wheel(args.provider_wheel, "epcsaft", PROVIDER_SHA256)
    regression = verify_installed_wheel(args.regression_wheel, "epcsaft-regression", REGRESSION_SHA256)
    epcsaft = importlib.import_module("epcsaft")
    epcsaft_regression = importlib.import_module("epcsaft_regression")
    origins = {
        "epcsaft": _verify_module_origin(epcsaft, provider["installed_root"]),
        "epcsaft_regression": _verify_module_origin(epcsaft_regression, regression["installed_root"]),
    }

    rows: list[dict[str, Any]] = []
    parameter_rows: list[dict[str, Any]] = []
    component_receipts: list[dict[str, Any]] = []
    specs = {
        "methane": epcsaft_regression.METHANE_SATURATION_FIT_V1,
        "ethane": epcsaft_regression.ETHANE_SATURATION_FIT_V1,
    }
    for component, specification in specs.items():
        dataset = epcsaft_regression.load_pure_saturation_dataset(component)
        _partition_contract(dataset, EXPECTED_DATASETS[component])
        model = epcsaft.EPCSAFT(
            epcsaft.ParameterBundle.from_catalog("gross-2001-methane-ethane", version=1).select((component,))
        )
        result = epcsaft_regression.fit_pure_saturation(
            model=model, dataset=dataset, specification=specification
        )
        fitted_values = [asdict(item) for item in result.parameters]
        fitted_parameter_sha256 = sha256_json(fitted_values)
        for item in fitted_values:
            parameter_rows.append(
                {
                    "component_id": component,
                    "name": item["name"],
                    "unit": item["unit"],
                    "start": item["start"],
                    "fitted": item["final"],
                    "movement": item["movement"],
                    "lower_bound": item["lower_bound"],
                    "upper_bound": item["upper_bound"],
                    "active_bound": item["active_bound"] or "",
                    "fitted_parameter_sha256": fitted_parameter_sha256,
                }
            )
        for item in result.reporting_rows:
            rows.append(
                {
                    "component_id": component,
                    "row_id": item.row_id,
                    "partition": item.partition,
                    "temperature_k": item.temperature_k,
                    "observed_pressure_pa": item.observed_pressure_pa,
                    "start_predicted_pressure_pa": "",
                    "fitted_predicted_pressure_pa": item.predicted_pressure_pa,
                    "start_pressure_relative_error": "",
                    "fitted_pressure_relative_error": item.pressure_relative_error,
                    "observed_liquid_density_kg_m3": item.observed_liquid_density_kg_m3,
                    "start_predicted_liquid_density_kg_m3": "",
                    "fitted_predicted_liquid_density_kg_m3": item.predicted_liquid_density_kg_m3,
                    "start_liquid_density_relative_error": "",
                    "fitted_liquid_density_relative_error": item.liquid_density_relative_error,
                    "reporting_solver_status": "PASS" if item.solution_usable else "FAIL",
                    "reporting_physical_status": "PASS" if item.physically_valid else "FAIL",
                    "provider_parameter_fingerprint": result.provider_fingerprint,
                    "fitted_parameter_sha256": fitted_parameter_sha256,
                    "provider_wheel_sha256": PROVIDER_SHA256,
                    "regression_wheel_sha256": REGRESSION_SHA256,
                }
            )
        component_rows = [row for row in rows if row["component_id"] == component]
        parity_status, parity_failures = (
            _parity_status(result) if component == "methane" else ("NOT_APPLICABLE", [])
        )
        stress_rows = [item for item in result.reporting_rows if item.partition == "stress"]
        local_pass = (
            result.solver_converged
            and result.numerically_converged
            and result.physically_valid
            and (parity_status in {"PASS", "NOT_APPLICABLE"})
        )
        component_receipts.append(
            {
                "component_id": component,
                "dataset_id": result.dataset_id,
                "specification_id": result.specification_id,
                "source": asdict(dataset.source),
                "solver_status": "PASS" if result.solver_converged else "FAIL",
                "numerical_status": "PASS" if result.numerically_converged else "FAIL",
                "local_physical_status": "PASS" if result.physically_valid else "FAIL",
                "predictive_status": "DESCRIPTIVE_ONLY_NO_APPROVED_CUTOFF",
                "stress_status": (
                    "EXCLUDED_FAILURE"
                    if any(not item.physically_valid for item in stress_rows)
                    else "EXCLUDED_PASS"
                ),
                "methane_parity_status": parity_status,
                "methane_parity_failures": parity_failures,
                "artifact_admission": "PASS" if local_pass else "NON_ADMISSION",
                "termination": result.termination,
                "solution_usable": result.solution_usable,
                "initial_cost": result.initial_cost,
                "final_cost": result.final_cost,
                "iterations": result.iterations,
                "parameters": fitted_values,
                "fitted_parameter_sha256": fitted_parameter_sha256,
                "jacobian": asdict(result.jacobian),
                "confirmation": {
                    "termination": result.confirmation_termination,
                    "solution_usable": result.confirmation_solution_usable,
                    "parameter_scaled_max_delta": result.confirmation_parameter_scaled_max_delta,
                    "cost_relative_delta": result.confirmation_cost_relative_delta,
                },
                "metrics": {
                    partition: _metrics(component_rows, partition)
                    for partition in ("training", "held_out", "stress")
                    if any(row["partition"] == partition for row in component_rows)
                },
                "failure_reasons": list(result.failure_reasons),
            }
        )

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "environment": _environment(origins),
        "artifacts": {
            "provider": provider,
            "regression": regression,
            "regression_implementation_commit": REGRESSION_IMPLEMENTATION_COMMIT,
            "regression_evidence_commit": REGRESSION_EVIDENCE_COMMIT,
            "ethane_candidate_receipt_sha256": ETHANE_RECEIPT_SHA256,
            "ethane_candidate_receipt_subject_sha256": ETHANE_RECEIPT_SUBJECT_SHA256,
            "methane_accepted_receipt": METHANE_ACCEPTED_RECEIPT,
        },
        "components": component_receipts,
        "admission": {
            "artifact_status": (
                "PASS"
                if all(item["artifact_admission"] == "PASS" for item in component_receipts)
                else "NON_ADMISSION"
            ),
            "predictive_status": "NOT_ADJUDICATED_NO_APPROVED_HELD_OUT_CUTOFF",
            "stress_policy": "Stress rows are descriptive and excluded from artifact admission; ethane 100 K remains an excluded failure.",
        },
        "limitations": [
            "The public regression result does not expose start-model saturation predictions. Start/fitted parameters and initial/final objective values are retained; start-prediction CSV cells remain empty rather than being reconstructed downstream.",
            "Held-out errors are descriptive because no predictive accuracy cutoff is approved.",
            "The ethane 100 K reporting solve is a retained excluded stress failure and is not an accepted prediction.",
            "Local rank and condition diagnostics do not establish global identifiability or parameter uncertainty.",
            "This validation transfers no runtime, release, or publication authority.",
        ],
    }
    validate_result_contract(receipt, rows, parameter_rows)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "pure-saturation-regression.csv"
    parameter_path = output_dir / "pure-saturation-regression-parameters.csv"
    receipt_path = output_dir / "pure-saturation-regression.json"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ROW_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with parameter_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PARAMETER_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(parameter_rows)
    receipt["outputs"] = {
        "prediction_csv": {"path": str(csv_path), "sha256": sha256_file(csv_path), "rows": len(rows)},
        "parameter_csv": {"path": str(parameter_path), "sha256": sha256_file(parameter_path), "rows": len(parameter_rows)},
    }
    receipt["environment"]["contract_sha256"] = sha256_json(receipt["environment"])
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_path), "admission": receipt["admission"]}, indent=2))
    return receipt


def main() -> int:
    args = build_parser().parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
