#!/usr/bin/env python3
"""Run the frozen 17-row May 2015 methane/ethane flash admission."""

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
import sys
import zipfile
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path
from typing import Any


CAMPAIGN_ID = "consumer-slice-2-may-2015-methane-ethane-flash-v1"
SOURCE_SHA256 = "5cd1e74925a3c6504f5106dcf911f2cae2d6e99a5133fccc20454d8991bdbc7f"
SOURCE_METADATA_SHA256 = "d43433e93b354e01f96d330c760818a24b775026461ce795e45774cfb11ac94e"
TOLERANCE_SHA256 = "ad744526678355be6ca47cf27ab9ff7ae66b7661c27e36ffe259c5b6295f1016"
SOURCE_CONTRACT_COMMIT = "73a37f5935e919a34d1e4fa3af285951d6fac8e7"
PROVIDER_SHA256 = "17c6735ee117469b13b76b6a669d0b4430071c8eaebdf1e405baefc9adcb838b"
EQUILIBRIUM_SHA256 = "9f3adbc6f5539ae14cbff15b14a9eccf289ce238b316f78a81a25c1b91b3cc49"
EQUILIBRIUM_COMMIT = "e16f1e0fff62892615ef11e4012cd1e63a329e39"
EQUILIBRIUM_TREE = "6fc131c03e392acd5ab6678ff6e17e59a4afce02"

OFFICIAL_SOURCE_HASHES = {
    "publisher_article_pdf": "53fd1bdd55dc6807ec76cf88626438d8dfceb3ec09149d4405ea36cfbe6b842a",
    "nist_thermoml_json": "77630e90db70bb6aabfdfa520f61f14cee5076ece0265754140a25f771659662",
    "nist_thermoml_xml": "311e35b53e27bc050e17c4146a466e087c24c7a15624c29ababc4b7897d7871a",
}

ROW_FIELDS = (
    "row_id",
    "pathway",
    "T_K",
    "P_Pa",
    "input_beta",
    "feed_z_methane",
    "source_x_methane",
    "source_y_methane",
    "uc_x_methane",
    "uc_y_methane",
    "x_comparison_allowance",
    "y_comparison_allowance",
    "model_x_methane",
    "model_y_methane",
    "returned_liquid_fraction",
    "returned_vapor_fraction",
    "x_signed_error",
    "y_signed_error",
    "x_normalized_error",
    "y_normalized_error",
    "solver_status",
    "numerical_status",
    "local_physical_status",
    "composition_agreement_status",
    "row_admission",
    "solver_message",
    "iterations",
    "material_balance_max_abs",
    "recomputed_material_balance_max_abs",
    "pressure_stationarity_max_relative",
    "chemical_potential_max_abs",
    "kkt_stationarity_max_abs",
    "phase_density_distance",
    "liquid_pressure_pa",
    "vapor_pressure_pa",
    "liquid_molar_density_mol_m3",
    "vapor_molar_density_mol_m3",
    "total_free_energy_over_rt",
    "parameter_fingerprint",
    "exact_derivatives",
    "globality_certificate",
    "failure_reason",
    "provider_wheel_sha256",
    "equilibrium_wheel_sha256",
    "source_csv_sha256",
    "tolerance_sha256",
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


def load_source(path: Path) -> list[dict[str, str]]:
    source = Path(path).expanduser().resolve()
    if sha256_file(source) != SOURCE_SHA256:
        raise ValueError("source CSV SHA-256 does not match the frozen contract")
    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected_ids = [f"may2015-ch4-c2h6-{index:03d}" for index in range(1, 18)]
    if [row["row_id"] for row in rows] != expected_ids:
        raise ValueError("source must contain the 17 frozen rows in source order")
    for row in rows:
        if not math.isclose(
            float(row["x_comparison_allowance"]), 3.0 * float(row["uc_x_methane"]), abs_tol=1e-12
        ):
            raise ValueError(f"liquid tolerance changed for {row['row_id']}")
        if not math.isclose(
            float(row["y_comparison_allowance"]), 3.0 * float(row["uc_y_methane"]), abs_tol=1e-12
        ):
            raise ValueError(f"vapor tolerance changed for {row['row_id']}")
    return rows


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _blank_result(source: dict[str, str], z_methane: float) -> dict[str, Any]:
    row = {field: "" for field in ROW_FIELDS}
    row.update(
        {
            "row_id": source["row_id"],
            "pathway": source["pathway"],
            "T_K": source["T_K"],
            "P_Pa": source["P_Pa"],
            "input_beta": 0.5,
            "feed_z_methane": z_methane,
            "source_x_methane": source["x_methane"],
            "source_y_methane": source["y_methane"],
            "uc_x_methane": source["uc_x_methane"],
            "uc_y_methane": source["uc_y_methane"],
            "x_comparison_allowance": source["x_comparison_allowance"],
            "y_comparison_allowance": source["y_comparison_allowance"],
            "provider_wheel_sha256": PROVIDER_SHA256,
            "equilibrium_wheel_sha256": EQUILIBRIUM_SHA256,
            "source_csv_sha256": SOURCE_SHA256,
            "tolerance_sha256": TOLERANCE_SHA256,
            "globality_certificate": False,
        }
    )
    return row


def _status(value: bool) -> str:
    return "PASS" if value else "FAIL"


def validate_result_contract(receipt: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    if receipt.get("globality_certificate") is not False:
        raise ValueError("campaign must explicitly disclaim globality")
    if len(rows) != 17:
        raise ValueError("result must retain all 17 rows")
    if any(row.get("globality_certificate") is not False for row in rows):
        raise ValueError("no row may claim a globality certificate")
    if any(row.get("row_admission") == "PASS" and row.get("local_physical_status") != "PASS" for row in rows):
        raise ValueError("a locally rejected or collapsed phase result cannot be admitted")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-wheel", required=True, type=require_wheel)
    parser.add_argument("--equilibrium-wheel", required=True, type=require_wheel)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not sys.flags.isolated:
        raise RuntimeError("campaign must run with Python isolated mode (-I)")
    source_rows = load_source(args.source)
    metadata_path = args.source.resolve().with_suffix(".yaml")
    if sha256_file(metadata_path) != SOURCE_METADATA_SHA256:
        raise ValueError("source metadata SHA-256 does not match the frozen contract")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata["tolerance_contract"]["sha256"] != TOLERANCE_SHA256:
        raise ValueError("tolerance contract hash changed")
    observed_source_hashes = {
        name: item["sha256"] for name, item in metadata["sources"].items()
    }
    if observed_source_hashes != OFFICIAL_SOURCE_HASHES:
        raise ValueError("official source download hashes changed")

    provider = verify_installed_wheel(args.provider_wheel, "epcsaft", PROVIDER_SHA256)
    equilibrium = verify_installed_wheel(
        args.equilibrium_wheel, "epcsaft-equilibrium", EQUILIBRIUM_SHA256
    )
    epcsaft = importlib.import_module("epcsaft")
    epcsaft_equilibrium = importlib.import_module("epcsaft_equilibrium")
    origins = {
        "epcsaft": _verify_module_origin(epcsaft, provider["installed_root"]),
        "epcsaft_equilibrium": _verify_module_origin(
            epcsaft_equilibrium, equilibrium["installed_root"]
        ),
    }
    model = epcsaft.EPCSAFT(
        epcsaft.ParameterBundle.from_catalog("gross-2001-methane-ethane", version=1).select(
            ("methane", "ethane")
        )
    )

    rows: list[dict[str, Any]] = []
    diagnostics_by_row: dict[str, Any] = {}
    for source in source_rows:
        source_x = float(source["x_methane"])
        source_y = float(source["y_methane"])
        z_methane = 0.5 * source_x + 0.5 * source_y
        row = _blank_result(source, z_methane)
        try:
            result = epcsaft_equilibrium.two_phase_flash(
                model,
                float(source["T_K"]) * epcsaft.unit_registry.kelvin,
                float(source["P_Pa"]) * epcsaft.unit_registry.pascal,
                (z_methane, 1.0 - z_methane),
            )
            diagnostics = asdict(result.diagnostics)
            diagnostics_by_row[source["row_id"]] = diagnostics
            if diagnostics["globality_certificate"] is not False:
                raise RuntimeError("equilibrium result made a forbidden globality claim")
            model_x = float(result.liquid.mole_fractions[0])
            model_y = float(result.vapor.mole_fractions[0])
            x_error = model_x - source_x
            y_error = model_y - source_y
            x_allowance = float(source["x_comparison_allowance"])
            y_allowance = float(source["y_comparison_allowance"])
            composition_pass = abs(x_error) <= x_allowance and abs(y_error) <= y_allowance
            recomputed_balance = abs(
                result.liquid_phase_fraction * model_x
                + result.vapor_phase_fraction * model_y
                - z_methane
            )
            local_pass = (
                diagnostics["solver_converged"]
                and diagnostics["numerical_converged"]
                and diagnostics["physical_accepted"]
            )
            row.update(
                {
                    "model_x_methane": model_x,
                    "model_y_methane": model_y,
                    "returned_liquid_fraction": result.liquid_phase_fraction,
                    "returned_vapor_fraction": result.vapor_phase_fraction,
                    "x_signed_error": x_error,
                    "y_signed_error": y_error,
                    "x_normalized_error": x_error / x_allowance,
                    "y_normalized_error": y_error / y_allowance,
                    "solver_status": _status(diagnostics["solver_converged"]),
                    "numerical_status": _status(diagnostics["numerical_converged"]),
                    "local_physical_status": _status(diagnostics["physical_accepted"]),
                    "composition_agreement_status": _status(composition_pass),
                    "row_admission": _status(local_pass and composition_pass),
                    "solver_message": diagnostics["solver_status"],
                    "iterations": diagnostics["iterations"],
                    "material_balance_max_abs": diagnostics["material_balance_max_abs"],
                    "recomputed_material_balance_max_abs": recomputed_balance,
                    "pressure_stationarity_max_relative": diagnostics[
                        "pressure_stationarity_max_relative"
                    ],
                    "chemical_potential_max_abs": diagnostics["chemical_potential_max_abs"],
                    "kkt_stationarity_max_abs": diagnostics["kkt_stationarity_max_abs"],
                    "phase_density_distance": diagnostics["phase_density_distance"],
                    "liquid_pressure_pa": result.liquid.pressure_pa,
                    "vapor_pressure_pa": result.vapor.pressure_pa,
                    "liquid_molar_density_mol_m3": result.liquid.molar_density_mol_m3,
                    "vapor_molar_density_mol_m3": result.vapor.molar_density_mol_m3,
                    "total_free_energy_over_rt": result.total_free_energy_over_rt,
                    "parameter_fingerprint": result.parameter_fingerprint,
                    "exact_derivatives": diagnostics["exact_derivatives"],
                    "globality_certificate": diagnostics["globality_certificate"],
                    "failure_reason": diagnostics["failure_reason"],
                }
            )
        except epcsaft_equilibrium.FlashError as error:
            diagnostics = _json_safe(error.diagnostics)
            diagnostics_by_row[source["row_id"]] = diagnostics
            if diagnostics.get("globality_certificate") is not False:
                raise RuntimeError("rejected equilibrium result made a forbidden globality claim")
            row.update(
                {
                    "solver_status": _status(bool(diagnostics.get("solver_converged"))),
                    "numerical_status": _status(bool(diagnostics.get("numerical_converged"))),
                    "local_physical_status": _status(bool(diagnostics.get("physical_accepted"))),
                    "composition_agreement_status": "NOT_EVALUATED_NO_ACCEPTED_PHASE_STATE",
                    "row_admission": "NON_ADMISSION",
                    "solver_message": diagnostics.get("solver_status", type(error).__name__),
                    "iterations": diagnostics.get("iterations", ""),
                    "material_balance_max_abs": diagnostics.get("material_balance_max_abs", ""),
                    "pressure_stationarity_max_relative": diagnostics.get(
                        "pressure_stationarity_max_relative", ""
                    ),
                    "chemical_potential_max_abs": diagnostics.get("chemical_potential_max_abs", ""),
                    "kkt_stationarity_max_abs": diagnostics.get("kkt_stationarity_max_abs", ""),
                    "phase_density_distance": diagnostics.get("phase_density_distance", ""),
                    "exact_derivatives": diagnostics.get("exact_derivatives", ""),
                    "globality_certificate": diagnostics.get("globality_certificate", False),
                    "failure_reason": str(error),
                }
            )
        rows.append(row)

    local_pass_rows = [row for row in rows if row["local_physical_status"] == "PASS"]
    agreement_pass_rows = [row for row in rows if row["composition_agreement_status"] == "PASS"]
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "environment": {
            "python": sys.version,
            "python_executable": sys.executable,
            "python_isolated": bool(sys.flags.isolated),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "implementation": platform.python_implementation(),
            "imports": origins,
        },
        "artifacts": {
            "provider": provider,
            "equilibrium": equilibrium,
            "equilibrium_commit": EQUILIBRIUM_COMMIT,
            "equilibrium_tree": EQUILIBRIUM_TREE,
        },
        "source": {
            "citation": metadata["citation"],
            "csv": {"path": str(args.source.resolve()), "sha256": SOURCE_SHA256},
            "metadata": {"path": str(metadata_path), "sha256": SOURCE_METADATA_SHA256},
            "official_download_sha256": OFFICIAL_SOURCE_HASHES,
            "source_contract_commit": SOURCE_CONTRACT_COMMIT,
            "tolerance_sha256": TOLERANCE_SHA256,
            "tolerance_basis": metadata["tolerance_contract"]["payload"],
        },
        "globality_certificate": False,
        "row_summary": {
            "total": len(rows),
            "package_local_accepted": len(local_pass_rows),
            "package_local_rejected": len(rows) - len(local_pass_rows),
            "composition_agreement_pass": len(agreement_pass_rows),
            "composition_agreement_fail": sum(
                row["composition_agreement_status"] == "FAIL" for row in rows
            ),
            "composition_not_evaluated": sum(
                row["composition_agreement_status"].startswith("NOT_EVALUATED") for row in rows
            ),
            "admitted_rows": sum(row["row_admission"] == "PASS" for row in rows),
        },
        "row_outcomes": [
            {
                "row_id": row["row_id"],
                "solver_status": row["solver_status"],
                "numerical_status": row["numerical_status"],
                "local_physical_status": row["local_physical_status"],
                "composition_agreement_status": row["composition_agreement_status"],
                "row_admission": row["row_admission"],
                "x_normalized_error": row["x_normalized_error"],
                "y_normalized_error": row["y_normalized_error"],
                "failure_reason": row["failure_reason"],
            }
            for row in rows
        ],
        "diagnostics_by_row": diagnostics_by_row,
        "admission": {
            "manager_reported_package_approval": "FINAL_PERMANENT_LAB_APPROVAL",
            "validation_package_local_campaign_status": (
                "PASS" if len(local_pass_rows) == len(rows) else "NON_ADMISSION"
            ),
            "predictive_agreement_status": (
                "PASS" if len(agreement_pass_rows) == len(rows) else "NON_ADMISSION"
            ),
            "overall_validation_status": (
                "PASS"
                if all(row["row_admission"] == "PASS" for row in rows)
                else "NON_ADMISSION"
            ),
        },
        "limitations": [
            "The calculation fixes two phases and provides no phase-discovery, TPD, continuation, or global-stability certificate.",
            "Rows with local solver acceptance but composition disagreement are model/data misses under the frozen 3*u_c contract, not solver defects.",
            "A package local-physical rejection is retained as such and receives no composition comparison.",
            "This validation transfers no runtime, release, publication, or promotion authority.",
        ],
    }
    validate_result_contract(receipt, rows)
    receipt["environment"]["contract_sha256"] = sha256_json(receipt["environment"])

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "may-2015-methane-ethane-flash.csv"
    receipt_path = output_dir / "may-2015-methane-ethane-flash.json"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ROW_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    receipt["outputs"] = {
        "csv": {"path": str(csv_path), "sha256": sha256_file(csv_path), "rows": len(rows)}
    }
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"receipt": str(receipt_path), **receipt["admission"]}, indent=2))
    return receipt


def main() -> int:
    args = build_parser().parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
