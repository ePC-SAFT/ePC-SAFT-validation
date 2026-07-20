#!/usr/bin/env python3
"""Validate the exact neutral-held-v1 wheels through public installed APIs."""

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


CAMPAIGN_ID = "neutral-held-v1-installed-artifact-validation"
MIGRATION_GATE_COMMIT = "2ab33646c9ef6069670fc37279dc19e0e7bc69ea"
MIGRATION_GATE_TREE = "dcb96f150e59c32e7453fa5eadf2b6102f39e715"
PROVIDER_SHA256 = "17c6735ee117469b13b76b6a669d0b4430071c8eaebdf1e405baefc9adcb838b"
PROVIDER_IMPLEMENTATION_COMMIT = "0cd75b96f1dddba024c324df500493bd1564bf5c"
PROVIDER_CANDIDATE_RECORD_COMMIT = "25e597289b044ff3e5af70b3572279293555b9f9"
EQUILIBRIUM_SHA256 = "8ecd70e0192b76b3a107629201c3e8bf34f2d945ca7c8192f824a0df7c9dde12"
EQUILIBRIUM_RUNTIME_COMMIT = "8318e755d4a8e490822fdf7bb2685d8c5af6436c"
EQUILIBRIUM_EVIDENCE_COMMIT = "db6cef273496b840a5b31426aa017b830bc7b94d"
CANDIDATE_RECEIPT_SHA256 = "a8a1fe6f0836cef3afd9edfe390fb2d131b1a7a441e160f4cd7176524038dc30"
SOURCE_SHA256 = "5cd1e74925a3c6504f5106dcf911f2cae2d6e99a5133fccc20454d8991bdbc7f"
SOURCE_METADATA_SHA256 = "d43433e93b354e01f96d330c760818a24b775026461ce795e45774cfb11ac94e"
TOLERANCE_SHA256 = "ad744526678355be6ca47cf27ab9ff7ae66b7661c27e36ffe259c5b6295f1016"
SOURCE_CONTRACT_COMMIT = "73a37f5935e919a34d1e4fa3af285951d6fac8e7"
CASES_SHA256 = "5aceaada58e3010d4232b8f3cf0f0447e2c174a33bbc54c9be7b8675464aa771"
PARAMETER_FINGERPRINT = "sha256:307fcb28d535b94782f3e3caf4012c0c8c0dc87ee4239d6c316de56553543286"
GAS_CONSTANT_J_PER_MOL_K = 8.31446261815324
RHO_REFERENCE_MOL_M3 = 1.0

CASE_FIELDS = (
    "case_id", "source_row_id", "case_role", "T_K", "P_Pa", "feed_z_methane",
    "expected_phase_count", "returned_phase_count", "phase_1_x_methane",
    "phase_1_density_mol_m3", "phase_1_fraction", "phase_2_x_methane",
    "phase_2_density_mol_m3", "phase_2_fraction", "outcome", "search_status",
    "solver_status", "numerical_status", "physical_status", "attempts",
    "major_iterations", "best_tpd", "lower_bound", "upper_bound", "held_gap",
    "material_balance_max_abs", "recomputed_material_balance_max_abs",
    "pressure_stationarity_max_relative", "kkt_stationarity_max_abs",
    "chemical_potential_max_relative", "confirmation_succeeded",
    "confirmation_max_difference", "search_profiles", "sampled_audit_status",
    "sampled_accepted_points", "sampled_violating_points", "sampled_minimum_gap",
    "sampled_localization_status", "total_free_energy_audit_error",
    "phase_count_status", "source_x_methane", "source_y_methane",
    "x_comparison_allowance", "y_comparison_allowance", "x_signed_error",
    "y_signed_error", "composition_agreement_status", "case_decision",
    "parameter_fingerprint", "globality_certificate", "failure_reason",
    "provider_wheel_sha256", "equilibrium_wheel_sha256", "source_csv_sha256",
    "tolerance_sha256", "case_contract_sha256",
)

SURFACE_FIELDS = (
    "audit_case_id", "grid_index", "x_methane", "branch", "status",
    "molar_density_mol_m3", "residual_helmholtz", "g_bar",
    "support_line_g_bar", "gap_above_support", "failure_reason",
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


def require_file(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"required file does not exist: {path}")
    return path


def require_wheel(value: str | Path) -> Path:
    path = require_file(value)
    if path.suffix != ".whl":
        raise ValueError(f"artifact is not a wheel: {path}")
    return path


def _wheel_metadata(wheel: Path) -> tuple[str, str, list[list[str]]]:
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        message = BytesParser().parsebytes(archive.read(metadata_name))
        record_name = metadata_name.removesuffix("METADATA") + "RECORD"
        rows = list(csv.reader(archive.read(record_name).decode("utf-8").splitlines()))
    return str(message["Name"]), str(message["Version"]), rows


def verify_installed_wheel(wheel: Path, distribution_name: str, expected_sha256: str) -> dict[str, Any]:
    observed = sha256_file(wheel)
    if observed != expected_sha256:
        raise ValueError(f"{distribution_name} wheel SHA-256 mismatch: {observed}")
    name, version, record_rows = _wheel_metadata(wheel)
    if name != distribution_name:
        raise ValueError(f"wheel distribution is {name!r}, expected {distribution_name!r}")
    distribution = importlib.metadata.distribution(distribution_name)
    if distribution.version != version:
        raise ValueError(f"installed {distribution_name} version does not match the wheel")
    verified = 0
    for member, encoded_hash, *_ in record_rows:
        if not encoded_hash:
            continue
        algorithm, expected = encoded_hash.split("=", 1)
        if algorithm != "sha256":
            raise ValueError(f"unsupported RECORD hash algorithm: {algorithm}")
        installed = Path(distribution.locate_file(member)).resolve()
        if not installed.is_file():
            raise ValueError(f"installed wheel member is missing: {member}")
        actual = base64.urlsafe_b64encode(hashlib.sha256(installed.read_bytes()).digest()).rstrip(b"=").decode()
        if actual != expected:
            raise ValueError(f"installed RECORD mismatch: {member}")
        verified += 1
    if verified == 0:
        raise ValueError("wheel RECORD has no hashed members")
    return {
        "path": str(wheel), "sha256": observed, "distribution": name, "version": version,
        "installed_root": str(Path(distribution.locate_file("")).resolve()),
        "record_members_verified": verified,
    }


def _verify_module_origin(module: Any, installed_root: str) -> str:
    origin = Path(module.__file__).resolve()
    if not origin.is_relative_to(Path(installed_root)):
        raise RuntimeError(f"module did not originate from the verified installation: {origin}")
    return str(origin)


def _reject_source_paths() -> None:
    project_root = Path(__file__).resolve().parents[2]
    forbidden = (project_root / "ePC-SAFT", project_root / "ePC-SAFT-equilibrium")
    for entry in sys.path:
        if not entry:
            continue
        resolved = Path(entry).resolve()
        if any(resolved == root or resolved.is_relative_to(root) for root in forbidden):
            raise RuntimeError(f"sibling source checkout is present on sys.path: {resolved}")


def load_inputs(cases_path: Path, source_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    if sha256_file(cases_path) != CASES_SHA256:
        raise ValueError("case contract SHA-256 changed")
    if sha256_file(source_path) != SOURCE_SHA256:
        raise ValueError("May source CSV SHA-256 changed")
    metadata_path = source_path.with_suffix(".yaml")
    if sha256_file(metadata_path) != SOURCE_METADATA_SHA256:
        raise ValueError("May source metadata SHA-256 changed")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata["tolerance_contract"]["sha256"] != TOLERANCE_SHA256:
        raise ValueError("May tolerance contract changed")
    contract = json.loads(cases_path.read_text(encoding="utf-8"))
    with source_path.open(encoding="utf-8", newline="") as handle:
        source_rows = {row["row_id"]: row for row in csv.DictReader(handle)}
    if len(contract["cases"]) != 18 or len(source_rows) != 17:
        raise ValueError("campaign requires 18 frozen cases over all 17 source rows")
    return contract, source_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-wheel", required=True, type=require_wheel)
    parser.add_argument("--equilibrium-wheel", required=True, type=require_wheel)
    parser.add_argument("--candidate-receipt", required=True, type=require_file)
    parser.add_argument("--cases", required=True, type=require_file)
    parser.add_argument("--source", required=True, type=require_file)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def _public_gibbs(epcsaft: Any, model: Any, temperature_k: float, pressure_pa: float, x: float, phase: str | None) -> dict[str, Any]:
    label = "single" if phase is None else phase
    try:
        result = model.evaluate(
            temperature=temperature_k * epcsaft.unit_registry.kelvin,
            pressure=pressure_pa * epcsaft.unit_registry.pascal,
            mole_fractions=(x, 1.0 - x),
            phase=phase,
        )
        rho = float(result.molar_density.to("mole / meter ** 3").magnitude)
        ideal = x * (math.log(x * rho / RHO_REFERENCE_MOL_M3) - 1.0)
        ideal += (1.0 - x) * (math.log((1.0 - x) * rho / RHO_REFERENCE_MOL_M3) - 1.0)
        g_bar = ideal + float(result.residual_helmholtz) + pressure_pa / (
            rho * GAS_CONSTANT_J_PER_MOL_K * temperature_k
        )
        return {
            "branch": label, "status": "accepted", "molar_density_mol_m3": rho,
            "residual_helmholtz": float(result.residual_helmholtz), "g_bar": g_bar,
            "failure_reason": "",
        }
    except Exception as error:
        return {
            "branch": label, "status": "failed", "molar_density_mol_m3": "",
            "residual_helmholtz": "", "g_bar": "", "failure_reason": f"{type(error).__name__}: {error}",
        }


def _sample_surface(epcsaft: Any, model: Any, case: Mapping[str, Any], grid: Mapping[str, Any]) -> list[dict[str, Any]]:
    points = int(grid["points"])
    minimum = float(grid["minimum"])
    spacing = float(grid["spacing"])
    rows: list[dict[str, Any]] = []
    for index in range(points):
        x = minimum + index * spacing
        for phase in (None, "vapor", "liquid"):
            row = _public_gibbs(epcsaft, model, float(case["T_K"]), float(case["P_Pa"]), x, phase)
            row.update({
                "audit_case_id": case["case_id"], "grid_index": index, "x_methane": x,
                "support_line_g_bar": "", "gap_above_support": "",
            })
            rows.append(row)
    return rows


def audit_line(rows: list[dict[str, Any]], *, intercept: float, slope: float, allowance: float) -> dict[str, Any]:
    gaps: list[float] = []
    for row in rows:
        if row["status"] != "accepted":
            continue
        support = intercept + slope * float(row["x_methane"])
        gap = float(row["g_bar"]) - support
        row["support_line_g_bar"] = support
        row["gap_above_support"] = gap
        gaps.append(gap)
    if not gaps:
        return {"status": "FAIL", "accepted_points": 0, "violating_points": 0, "minimum_gap": None}
    violations = sum(gap < -allowance for gap in gaps)
    return {
        "status": "PASS" if violations == 0 else "FAIL",
        "accepted_points": len(gaps), "violating_points": violations, "minimum_gap": min(gaps),
    }


def _nearest_public_state(epcsaft: Any, model: Any, case: Mapping[str, Any], phase: Any) -> dict[str, Any]:
    candidates = [
        _public_gibbs(epcsaft, model, float(case["T_K"]), float(case["P_Pa"]), float(phase.mole_fractions[0]), branch)
        for branch in (None, "vapor", "liquid")
    ]
    accepted = [candidate for candidate in candidates if candidate["status"] == "accepted"]
    if not accepted:
        raise RuntimeError("no public pressure-state branch accepted a returned HELD phase composition")
    selected = min(
        accepted,
        key=lambda item: abs(float(item["molar_density_mol_m3"]) - float(phase.molar_density_mol_m3))
        / max(float(phase.molar_density_mol_m3), 1.0),
    )
    selected["relative_density_difference"] = abs(
        float(selected["molar_density_mol_m3"]) - float(phase.molar_density_mol_m3)
    ) / max(float(phase.molar_density_mol_m3), 1.0)
    return selected


def _localization(rows: list[dict[str, Any]], targets: list[float], allowance: float) -> dict[str, Any]:
    accepted = [row for row in rows if row["status"] == "accepted" and row["gap_above_support"] != ""]
    if not accepted:
        return {"status": "FAIL", "target_errors": []}
    split = sum(targets) / len(targets)
    errors: list[float] = []
    for index, target in enumerate(targets):
        candidates = accepted
        if len(targets) == 2:
            candidates = [row for row in accepted if (float(row["x_methane"]) <= split) == (index == 0)]
        closest = min(candidates, key=lambda row: abs(float(row["gap_above_support"])))
        errors.append(abs(float(closest["x_methane"]) - target))
    return {"status": "PASS" if all(error <= allowance for error in errors) else "FAIL", "target_errors": errors}


def _audit_result(epcsaft: Any, model: Any, case: Mapping[str, Any], result: Any, surface: list[dict[str, Any]], audit: Mapping[str, Any]) -> dict[str, Any]:
    allowance = float(audit["dimensionless_tangent_chord_allowance"])
    localization_allowance = float(audit["composition_grid"]["localization_allowance"])
    phases = sorted(result.phases, key=lambda phase: phase.mole_fractions[0])
    public_states = [_nearest_public_state(epcsaft, model, case, phase) for phase in phases]
    if len(phases) == 2:
        x0, x1 = (float(phase.mole_fractions[0]) for phase in phases)
        g0, g1 = (float(state["g_bar"]) for state in public_states)
        slope = (g1 - g0) / (x1 - x0)
        intercept = g0 - slope * x0
        targets = [x0, x1]
    elif len(phases) == 1:
        x0 = float(phases[0].mole_fractions[0])
        spacing = float(audit["composition_grid"]["spacing"])
        branch = None if public_states[0]["branch"] == "single" else public_states[0]["branch"]
        left = _public_gibbs(epcsaft, model, float(case["T_K"]), float(case["P_Pa"]), x0 - spacing, branch)
        right = _public_gibbs(epcsaft, model, float(case["T_K"]), float(case["P_Pa"]), x0 + spacing, branch)
        if left["status"] != "accepted" or right["status"] != "accepted":
            raise RuntimeError("public pressure-state finite tangent could not be formed")
        slope = (float(right["g_bar"]) - float(left["g_bar"])) / (2.0 * spacing)
        intercept = float(public_states[0]["g_bar"]) - slope * x0
        targets = [x0]
    else:
        raise RuntimeError("HELD returned an unsupported phase count")
    line = audit_line(surface, intercept=intercept, slope=slope, allowance=allowance)
    localization = _localization(surface, targets, localization_allowance)
    feed = float(case["feed_z_methane"])
    support_at_feed = intercept + slope * feed
    energy_error = float(result.total_free_energy_over_rt) - support_at_feed
    line["status"] = "PASS" if line["status"] == "PASS" and abs(energy_error) <= allowance else "FAIL"
    return {
        **line, "localization": localization, "intercept": intercept, "slope": slope,
        "support_at_feed": support_at_feed, "total_free_energy_error": energy_error,
        "public_phase_states": public_states,
    }


def _blank_case(case: Mapping[str, Any], source: Mapping[str, str] | None) -> dict[str, Any]:
    row = {field: "" for field in CASE_FIELDS}
    row.update({
        "case_id": case["case_id"], "source_row_id": case["source_row_id"],
        "case_role": "may_coexistence_midpoint" if case["expected_phase_count"] == 2 else "derived_liquid_side",
        "T_K": case["T_K"], "P_Pa": case["P_Pa"], "feed_z_methane": case["feed_z_methane"],
        "expected_phase_count": case["expected_phase_count"], "globality_certificate": "not_guaranteed",
        "provider_wheel_sha256": PROVIDER_SHA256, "equilibrium_wheel_sha256": EQUILIBRIUM_SHA256,
        "source_csv_sha256": SOURCE_SHA256, "tolerance_sha256": TOLERANCE_SHA256,
        "case_contract_sha256": CASES_SHA256, "parameter_fingerprint": PARAMETER_FINGERPRINT,
    })
    if source is not None:
        row.update({
            "source_x_methane": source["x_methane"], "source_y_methane": source["y_methane"],
            "x_comparison_allowance": source["x_comparison_allowance"],
            "y_comparison_allowance": source["y_comparison_allowance"],
        })
    return row


def _environment(origins: Mapping[str, str]) -> dict[str, Any]:
    distributions = sorted(
        (str(item.metadata["Name"]), item.version)
        for item in importlib.metadata.distributions() if item.metadata["Name"]
    )
    return {
        "python": sys.version, "python_executable": sys.executable,
        "python_executable_sha256": sha256_file(Path(sys.executable).resolve()),
        "python_isolated": bool(sys.flags.isolated), "platform": platform.platform(),
        "machine": platform.machine(), "imports": dict(origins),
        "installed_distributions": [{"name": name, "version": version} for name, version in distributions],
    }


def validate_result_contract(receipt: Mapping[str, Any], rows: list[dict[str, Any]]) -> None:
    if receipt.get("globality_certificate") != "not_guaranteed":
        raise ValueError("globality must remain not_guaranteed")
    if len(rows) != 18:
        raise ValueError("result must retain all 18 frozen cases")
    if any(row.get("globality_certificate") != "not_guaranteed" for row in rows):
        raise ValueError("every case must disclaim guaranteed globality")
    required = {"artifact_integrity", "solver", "numerical", "physical", "sampled_phase_set", "predictive_agreement"}
    if not required <= set(receipt.get("decisions", {})):
        raise ValueError("decision layers are incomplete")


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not sys.flags.isolated:
        raise RuntimeError("campaign must run with Python isolated mode (-I)")
    _reject_source_paths()
    if sha256_file(args.candidate_receipt) != CANDIDATE_RECEIPT_SHA256:
        raise ValueError("candidate receipt SHA-256 mismatch")
    contract, source_rows = load_inputs(args.cases, args.source)
    provider = verify_installed_wheel(args.provider_wheel, "epcsaft", PROVIDER_SHA256)
    equilibrium = verify_installed_wheel(args.equilibrium_wheel, "epcsaft-equilibrium", EQUILIBRIUM_SHA256)
    epcsaft = importlib.import_module("epcsaft")
    epcsaft_equilibrium = importlib.import_module("epcsaft_equilibrium")
    origins = {
        "epcsaft": _verify_module_origin(epcsaft, provider["installed_root"]),
        "epcsaft_equilibrium": _verify_module_origin(epcsaft_equilibrium, equilibrium["installed_root"]),
    }
    model = epcsaft.EPCSAFT(
        epcsaft.ParameterBundle.from_catalog("gross-2001-methane-ethane", version=1).select(("methane", "ethane"))
    )
    if model.parameter_fingerprint != PARAMETER_FINGERPRINT:
        raise RuntimeError("installed provider returned the wrong parameter fingerprint")

    audit_case_ids = set(contract["sampled_gibbs_audit"]["case_ids"])
    result_rows: list[dict[str, Any]] = []
    surface_rows: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {}
    audit_summaries: dict[str, Any] = {}
    for case in contract["cases"]:
        source = source_rows.get(case["source_row_id"])
        row = _blank_case(case, source)
        case_surface: list[dict[str, Any]] = []
        if case["case_id"] in audit_case_ids:
            case_surface = _sample_surface(epcsaft, model, case, contract["sampled_gibbs_audit"]["composition_grid"])
        try:
            result = epcsaft_equilibrium.tp_flash(
                model,
                float(case["T_K"]) * epcsaft.unit_registry.kelvin,
                float(case["P_Pa"]) * epcsaft.unit_registry.pascal,
                (float(case["feed_z_methane"]), 1.0 - float(case["feed_z_methane"])),
            )
            diag = asdict(result.diagnostics)
            diagnostics[case["case_id"]] = diag
            if diag["globality_certificate"] != "not_guaranteed":
                raise RuntimeError("candidate made a forbidden globality claim")
            if not diag["search_profiles"] or diag["search_status"] == "search_exhausted":
                raise RuntimeError("candidate did not complete its declared finite search")
            phases = sorted(result.phases, key=lambda phase: phase.molar_density_mol_m3, reverse=True)
            fractions = [result.phase_fractions[result.phases.index(phase)] for phase in phases]
            balance = max(
                abs(sum(fraction * phase.mole_fractions[i] for fraction, phase in zip(fractions, phases, strict=True)) - ((float(case["feed_z_methane"]), 1.0 - float(case["feed_z_methane"])))[i])
                for i in range(2)
            )
            row.update({
                "returned_phase_count": len(phases), "outcome": diag["outcome"],
                "search_status": diag["search_status"], "solver_status": diag["solver_status"],
                "numerical_status": diag["numerical_status"], "physical_status": diag["physical_status"],
                "attempts": diag["attempts"], "major_iterations": diag["major_iterations"],
                "best_tpd": diag["best_tpd"], "lower_bound": diag["lower_bound"],
                "upper_bound": diag["upper_bound"], "held_gap": diag["held_gap"],
                "material_balance_max_abs": diag["material_balance_max_abs"],
                "recomputed_material_balance_max_abs": balance,
                "pressure_stationarity_max_relative": diag["pressure_stationarity_max_relative"],
                "kkt_stationarity_max_abs": diag["kkt_stationarity_max_abs"],
                "chemical_potential_max_relative": diag["chemical_potential_max_relative"],
                "confirmation_succeeded": diag["confirmation_succeeded"],
                "confirmation_max_difference": diag["confirmation_max_difference"],
                "search_profiles": "|".join(diag["search_profiles"]),
                "phase_count_status": "PASS" if len(phases) == int(case["expected_phase_count"]) else "FAIL",
                "parameter_fingerprint": result.parameter_fingerprint,
            })
            for index, (phase, fraction) in enumerate(zip(phases, fractions, strict=True), start=1):
                row[f"phase_{index}_x_methane"] = phase.mole_fractions[0]
                row[f"phase_{index}_density_mol_m3"] = phase.molar_density_mol_m3
                row[f"phase_{index}_fraction"] = fraction
            if case_surface:
                audit_result = _audit_result(epcsaft, model, case, result, case_surface, contract["sampled_gibbs_audit"])
                audit_summaries[case["case_id"]] = audit_result
                row.update({
                    "sampled_audit_status": audit_result["status"],
                    "sampled_accepted_points": audit_result["accepted_points"],
                    "sampled_violating_points": audit_result["violating_points"],
                    "sampled_minimum_gap": audit_result["minimum_gap"],
                    "sampled_localization_status": audit_result["localization"]["status"],
                    "total_free_energy_audit_error": audit_result["total_free_energy_error"],
                })
            else:
                row["sampled_audit_status"] = "NOT_SAMPLED_BY_FROZEN_PLAN"
                row["sampled_localization_status"] = "NOT_SAMPLED_BY_FROZEN_PLAN"
            if int(case["expected_phase_count"]) == 2 and len(phases) == 2 and source is not None:
                model_x = float(phases[0].mole_fractions[0])
                model_y = float(phases[1].mole_fractions[0])
                x_error = model_x - float(source["x_methane"])
                y_error = model_y - float(source["y_methane"])
                agreement = abs(x_error) <= float(source["x_comparison_allowance"]) and abs(y_error) <= float(source["y_comparison_allowance"])
                row.update({
                    "x_signed_error": x_error, "y_signed_error": y_error,
                    "composition_agreement_status": "PASS" if agreement else "FAIL",
                })
            elif int(case["expected_phase_count"]) == 2:
                row["composition_agreement_status"] = "NOT_EVALUATED_PHASE_COUNT"
            else:
                row["composition_agreement_status"] = "NOT_APPLICABLE_DERIVED_CASE"
            algorithm_ok = all(diag[name] == "passed" for name in ("solver_status", "numerical_status", "physical_status"))
            sampled_ok = row["sampled_audit_status"] in {"PASS", "NOT_SAMPLED_BY_FROZEN_PLAN"}
            localization_ok = row["sampled_localization_status"] in {"PASS", "NOT_SAMPLED_BY_FROZEN_PLAN"}
            row["case_decision"] = "PASS" if algorithm_ok and row["phase_count_status"] == "PASS" and sampled_ok and localization_ok else "NON_ADMISSION"
        except epcsaft_equilibrium.FlashError as error:
            diag = asdict(error.diagnostics)
            diagnostics[case["case_id"]] = diag
            row.update({
                "outcome": diag["outcome"], "search_status": diag["search_status"],
                "solver_status": diag["solver_status"], "numerical_status": diag["numerical_status"],
                "physical_status": diag["physical_status"], "attempts": diag["attempts"],
                "major_iterations": diag["major_iterations"], "best_tpd": diag["best_tpd"],
                "lower_bound": diag["lower_bound"], "upper_bound": diag["upper_bound"],
                "held_gap": diag["held_gap"], "material_balance_max_abs": diag["material_balance_max_abs"],
                "pressure_stationarity_max_relative": diag["pressure_stationarity_max_relative"],
                "kkt_stationarity_max_abs": diag["kkt_stationarity_max_abs"],
                "chemical_potential_max_relative": diag["chemical_potential_max_relative"],
                "confirmation_succeeded": diag["confirmation_succeeded"],
                "confirmation_max_difference": diag["confirmation_max_difference"],
                "search_profiles": "|".join(diag["search_profiles"]),
                "sampled_audit_status": "NOT_EVALUATED_NO_HELD_STATE",
                "sampled_localization_status": "NOT_EVALUATED_NO_HELD_STATE",
                "phase_count_status": "FAIL", "composition_agreement_status": "NOT_EVALUATED_NO_HELD_STATE",
                "case_decision": "NON_ADMISSION", "failure_reason": str(error),
            })
        surface_rows.extend(case_surface)
        result_rows.append(row)

    may_rows = [row for row in result_rows if row["case_role"] == "may_coexistence_midpoint"]
    decisions = {
        "artifact_integrity": "PASS",
        "solver": "PASS" if all(row["solver_status"] == "passed" for row in result_rows) else "NON_ADMISSION",
        "numerical": "PASS" if all(row["numerical_status"] == "passed" for row in result_rows) else "NON_ADMISSION",
        "physical": "PASS" if all(row["physical_status"] == "passed" for row in result_rows) else "NON_ADMISSION",
        "declared_search_completion": "PASS" if all(row["search_status"] != "search_exhausted" and row["returned_phase_count"] != "" for row in result_rows) else "NON_ADMISSION",
        "sampled_phase_set": "PASS" if all(row["sampled_audit_status"] == "PASS" and row["sampled_localization_status"] == "PASS" for row in result_rows if row["case_id"] in audit_case_ids) else "NON_ADMISSION",
        "one_phase_behavior": "PASS" if result_rows[-1]["case_decision"] == "PASS" else "NON_ADMISSION",
        "two_phase_behavior": "PASS" if all(row["phase_count_status"] == "PASS" for row in may_rows) else "NON_ADMISSION",
        "predictive_agreement": "PASS" if all(row["composition_agreement_status"] == "PASS" for row in may_rows) else "NON_ADMISSION",
    }
    decisions["installed_artifact_campaign"] = "PASS" if all(
        decisions[name] == "PASS" for name in (
            "artifact_integrity", "solver", "numerical", "physical", "declared_search_completion",
            "sampled_phase_set", "one_phase_behavior", "two_phase_behavior",
        )
    ) else "NON_ADMISSION"

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cases_output = output_dir / "neutral-held-v1-cases.csv"
    surface_output = output_dir / "neutral-held-v1-sampled-gibbs.csv"
    receipt_output = output_dir / "neutral-held-v1-validation.json"
    with cases_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CASE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(result_rows)
    with surface_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SURFACE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(surface_rows)
    environment = _environment(origins)
    environment["contract_sha256"] = sha256_json(environment)
    receipt: dict[str, Any] = {
        "schema_version": 1, "campaign_id": CAMPAIGN_ID,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv], "globality_certificate": "not_guaranteed",
        "migration_gate": {"commit": MIGRATION_GATE_COMMIT, "tree": MIGRATION_GATE_TREE},
        "artifacts": {
            "provider": {**provider, "implementation_commit": PROVIDER_IMPLEMENTATION_COMMIT, "candidate_record_commit": PROVIDER_CANDIDATE_RECORD_COMMIT},
            "equilibrium": {**equilibrium, "runtime_commit": EQUILIBRIUM_RUNTIME_COMMIT, "evidence_commit": EQUILIBRIUM_EVIDENCE_COMMIT},
            "candidate_receipt": {"path": str(args.candidate_receipt), "sha256": CANDIDATE_RECEIPT_SHA256},
        },
        "source": {
            "csv": {"path": str(args.source), "sha256": SOURCE_SHA256},
            "metadata_sha256": SOURCE_METADATA_SHA256, "tolerance_sha256": TOLERANCE_SHA256,
            "source_contract_commit": SOURCE_CONTRACT_COMMIT,
            "cases": {"path": str(args.cases), "sha256": CASES_SHA256},
        },
        "environment": environment,
        "counts": {
            "cases": len(result_rows), "may_coexistence_cases": len(may_rows),
            "derived_one_phase_cases": 1, "sampled_audit_cases": len(audit_case_ids),
            "sampled_rows": len(surface_rows),
            "package_accepted_cases": sum(row["returned_phase_count"] != "" for row in result_rows),
            "predictive_pass_rows": sum(row["composition_agreement_status"] == "PASS" for row in may_rows),
            "predictive_fail_rows": sum(row["composition_agreement_status"] == "FAIL" for row in may_rows),
            "predictive_not_evaluated_rows": sum(row["composition_agreement_status"].startswith("NOT_EVALUATED") for row in may_rows),
        },
        "decisions": decisions, "audit_summaries": audit_summaries,
        "diagnostics_by_case": diagnostics,
        "outputs": {
            "cases_csv": {"path": str(cases_output), "sha256": sha256_file(cases_output), "rows": len(result_rows)},
            "sampled_gibbs_csv": {"path": str(surface_output), "sha256": sha256_file(surface_output), "rows": len(surface_rows)},
        },
        "limitations": [
            "The public pressure-state scan is finite sampled evidence and is not a continuous globality proof.",
            "globality_certificate remains not_guaranteed for every case and decision layer.",
            "Experimental composition disagreement is an EOS/data outcome, not a solver defect.",
            "This record transfers no runtime, promotion, publication, release, or authority.",
        ],
    }
    validate_result_contract(receipt, result_rows)
    receipt_output.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_output), "counts": receipt["counts"], "decisions": decisions}, indent=2, sort_keys=True))
    return receipt


def main() -> int:
    run(build_parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
