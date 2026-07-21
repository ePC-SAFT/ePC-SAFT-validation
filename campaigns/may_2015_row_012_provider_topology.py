#!/usr/bin/env python3
"""Run the public-Provider-only May row-012 topology diagnostic."""

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
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Callable


CONTRACT_SHA256 = "52c40bcc3d59014068f91486c2aff19fdc3f997d20ae3aeabbe34543273ecf15"
SOURCE_SHA256 = "5cd1e74925a3c6504f5106dcf911f2cae2d6e99a5133fccc20454d8991bdbc7f"
SOURCE_METADATA_SHA256 = "d43433e93b354e01f96d330c760818a24b775026461ce795e45774cfb11ac94e"
PROVIDER_SHA256 = "17c6735ee117469b13b76b6a669d0b4430071c8eaebdf1e405baefc9adcb838b"
PARAMETER_FINGERPRINT = "sha256:307fcb28d535b94782f3e3caf4012c0c8c0dc87ee4239d6c316de56553543286"
GAS_CONSTANT_J_PER_MOL_K = 8.31446261815324
RHO_REFERENCE_MOL_M3 = 1.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-wheel", required=True, type=require_wheel)
    parser.add_argument("--contract", required=True, type=require_file)
    parser.add_argument("--source", required=True, type=require_file)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _verify_wheel(wheel: Path) -> dict[str, Any]:
    if sha256_file(wheel) != PROVIDER_SHA256:
        raise ValueError("Provider wheel SHA-256 mismatch")
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        message = BytesParser().parsebytes(archive.read(metadata_name))
        record_name = metadata_name.removesuffix("METADATA") + "RECORD"
        record_rows = list(csv.reader(archive.read(record_name).decode("utf-8").splitlines()))
    if str(message["Name"]) != "epcsaft":
        raise ValueError("wheel distribution is not epcsaft")
    distribution = importlib.metadata.distribution("epcsaft")
    if distribution.version != str(message["Version"]):
        raise ValueError("installed Provider version does not match the supplied wheel")
    verified = 0
    for member, encoded_hash, *_ in record_rows:
        if not encoded_hash:
            continue
        algorithm, expected = encoded_hash.split("=", 1)
        if algorithm != "sha256":
            raise ValueError(f"unsupported RECORD algorithm: {algorithm}")
        installed = Path(distribution.locate_file(member)).resolve()
        actual = base64.urlsafe_b64encode(hashlib.sha256(installed.read_bytes()).digest()).rstrip(b"=").decode()
        if actual != expected:
            raise ValueError(f"installed RECORD mismatch: {member}")
        verified += 1
    return {
        "path": str(wheel),
        "sha256": PROVIDER_SHA256,
        "distribution": "epcsaft",
        "version": distribution.version,
        "installed_root": str(Path(distribution.locate_file("")).resolve()),
        "record_members_verified": verified,
    }


def _verify_public_import(module: Any, installed_root: str) -> str:
    origin = Path(module.__file__).resolve()
    if not origin.is_relative_to(Path(installed_root)):
        raise RuntimeError(f"epcsaft import is outside the verified installation: {origin}")
    project_root = Path(__file__).resolve().parents[2]
    sibling_provider = project_root / "ePC-SAFT"
    for entry in sys.path:
        if entry and Path(entry).resolve().is_relative_to(sibling_provider):
            raise RuntimeError(f"sibling Provider source is present on sys.path: {entry}")
    if "epcsaft_equilibrium" in sys.modules:
        raise RuntimeError("Equilibrium runtime was imported into the Provider-only diagnostic")
    return str(origin)


def _load_contract(contract_path: Path, source_path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    if sha256_file(contract_path) != CONTRACT_SHA256:
        raise ValueError("diagnostic contract SHA-256 mismatch")
    if sha256_file(source_path) != SOURCE_SHA256:
        raise ValueError("May source CSV SHA-256 mismatch")
    metadata_path = source_path.with_suffix(".yaml")
    if sha256_file(metadata_path) != SOURCE_METADATA_SHA256:
        raise ValueError("May source metadata SHA-256 mismatch")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    with source_path.open(encoding="utf-8", newline="") as handle:
        rows = {row["row_id"]: row for row in csv.DictReader(handle)}
    row = rows[contract["source"]["row_id"]]
    expected = contract["source"]
    checks = {
        "T_K": expected["temperature_K"],
        "P_Pa": expected["pressure_Pa"],
        "x_methane": expected["source_liquid_x_methane"],
        "y_methane": expected["source_vapor_y_methane"],
    }
    if any(not math.isclose(float(row[name]), float(value), abs_tol=1e-12) for name, value in checks.items()):
        raise ValueError("row-012 source values do not match the diagnostic contract")
    if not math.isclose(
        expected["feed_z_methane"],
        0.5 * (expected["source_liquid_x_methane"] + expected["source_vapor_y_methane"]),
        abs_tol=1e-15,
    ):
        raise ValueError("row-012 feed is not the exact source-pair midpoint")
    return contract, row


def golden_minimize(
    function: Callable[[float], float],
    lower: float,
    upper: float,
    max_iterations: int,
    width: float,
) -> dict[str, Any]:
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = float(lower), float(upper)
    c = b - ratio * (b - a)
    d = a + ratio * (b - a)
    fc, fd = function(c), function(d)
    evaluations = 2
    iterations = 0
    while b - a > width and iterations < max_iterations:
        if fc <= fd:
            b, d, fd = d, c, fc
            c = b - ratio * (b - a)
            fc = function(c)
        else:
            a, c, fc = c, d, fd
            d = a + ratio * (b - a)
            fd = function(d)
        evaluations += 1
        iterations += 1
    x = 0.5 * (a + b)
    value = function(x)
    return {
        "x": x,
        "value": value,
        "bracket": [a, b],
        "iterations": iterations,
        "evaluations": evaluations + 1,
        "converged": b - a <= width,
    }


def _public_state(
    epcsaft: Any,
    model: Any,
    temperature_k: float,
    pressure_pa: float,
    x_methane: float,
    branch: str,
) -> dict[str, Any]:
    phase = None if branch == "single" else branch
    try:
        result = model.evaluate(
            temperature=temperature_k * epcsaft.unit_registry.kelvin,
            pressure=pressure_pa * epcsaft.unit_registry.pascal,
            mole_fractions=(x_methane, 1.0 - x_methane),
            phase=phase,
        )
        diagnostics = result.density_diagnostics
        if diagnostics is None:
            raise RuntimeError("public pressure state omitted density diagnostics")
        rho = float(result.molar_density.to("mole / meter ** 3").magnitude)
        derivative = float(
            diagnostics.pressure_density_derivative.to("pascal * meter ** 3 / mole").magnitude
        )
        ideal = x_methane * (math.log(x_methane * rho / RHO_REFERENCE_MOL_M3) - 1.0)
        ideal += (1.0 - x_methane) * (
            math.log((1.0 - x_methane) * rho / RHO_REFERENCE_MOL_M3) - 1.0
        )
        g_bar = ideal + float(result.residual_helmholtz) + pressure_pa / (
            rho * GAS_CONSTANT_J_PER_MOL_K * temperature_k
        )
        return {
            "status": "accepted",
            "request_branch": branch,
            "reported_branch": diagnostics.branch,
            "x_methane": x_methane,
            "molar_density_mol_m3": rho,
            "g_bar": g_bar,
            "stable": bool(diagnostics.stable),
            "pressure_density_derivative_Pa_m3_mol": derivative,
            "pressure_residual_Pa": float(diagnostics.pressure_residual.to("pascal").magnitude),
            "bracket_mol_m3": [
                float(diagnostics.bracket_lower.to("mole / meter ** 3").magnitude),
                float(diagnostics.bracket_upper.to("mole / meter ** 3").magnitude),
            ],
            "iterations": diagnostics.iterations,
            "mechanically_stable": bool(diagnostics.stable) and derivative > 0.0,
            "failure_reason": "",
        }
    except Exception as error:
        return {
            "status": "failed",
            "request_branch": branch,
            "x_methane": x_methane,
            "mechanically_stable": False,
            "failure_reason": f"{type(error).__name__}: {error}",
        }


def _root_set(states: list[dict[str, Any]], relative_density_tolerance: float) -> list[dict[str, Any]]:
    stable = sorted(
        (state for state in states if state["status"] == "accepted" and state["mechanically_stable"]),
        key=lambda state: state["molar_density_mol_m3"],
    )
    roots: list[dict[str, Any]] = []
    for state in stable:
        if roots and abs(state["molar_density_mol_m3"] - roots[-1]["molar_density_mol_m3"]) / max(
            state["molar_density_mol_m3"], roots[-1]["molar_density_mol_m3"], 1.0
        ) <= relative_density_tolerance:
            roots[-1]["aliases"].append(state["request_branch"])
            continue
        roots.append({**state, "aliases": [state["request_branch"]]})
    for index, root in enumerate(roots, start=1):
        root["root_identity"] = f"root-{index}-of-{len(roots)}"
    return roots


def _derivative_trace(
    state: Callable[[float, str], dict[str, Any]], feed: float, steps: list[float]
) -> list[dict[str, float]]:
    trace: list[dict[str, float]] = []
    for step in steps:
        values = [state(feed + offset * step, "single") for offset in (-2.0, -1.0, 1.0, 2.0)]
        if not all(value["status"] == "accepted" and value["mechanically_stable"] for value in values):
            raise RuntimeError(f"homogeneous feed derivative failed at step {step}")
        fm2, fm1, fp1, fp2 = (value["g_bar"] for value in values)
        slope = (fm2 - 8.0 * fm1 + 8.0 * fp1 - fp2) / (12.0 * step)
        trace.append({"step": step, "slope": slope})
    return trace


def _mesh_scan(
    state: Callable[[float, str], dict[str, Any]],
    feed_g: float,
    slope: float,
    feed: float,
    domain: list[float],
    points: int,
    branches: list[str],
    feed_exclusion: float,
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    lower, upper = domain
    spacing = (upper - lower) / (points - 1)
    branch_rows: dict[str, list[dict[str, Any]]] = {branch: [] for branch in branches}
    root_counts: dict[int, int] = {}
    minimum: dict[str, Any] | None = None
    for index in range(points):
        x = lower + index * spacing
        states = [state(x, branch) for branch in branches]
        roots = _root_set(states, 1e-9)
        root_counts[len(roots)] = root_counts.get(len(roots), 0) + 1
        for item in states:
            row = {**item, "index": index}
            if item["status"] == "accepted" and item["mechanically_stable"]:
                row["tpd"] = item["g_bar"] - feed_g - slope * (x - feed)
                if abs(x - feed) > feed_exclusion and (minimum is None or row["tpd"] < minimum["tpd"]):
                    minimum = row
            branch_rows[item["request_branch"]].append(row)
    return {
        "points": points,
        "spacing": spacing,
        "root_count_histogram": {str(key): value for key, value in sorted(root_counts.items())},
        "minimum": minimum,
    }, branch_rows


def _segments(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in rows:
        valid = row["status"] == "accepted" and row["mechanically_stable"]
        if valid:
            current.append(row)
        elif current:
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def _refine_minima(
    state: Callable[[float, str], dict[str, Any]],
    branch_rows: dict[str, list[dict[str, Any]]],
    feed_g: float,
    slope: float,
    feed: float,
    feed_exclusion: float,
    maximum_iterations: int,
    width: float,
) -> list[dict[str, Any]]:
    refined: list[dict[str, Any]] = []
    for branch, rows in branch_rows.items():
        for segment in _segments(rows):
            for index in range(1, len(segment) - 1):
                left, center, right = segment[index - 1 : index + 2]
                if abs(center["x_methane"] - feed) <= feed_exclusion:
                    continue
                if center["tpd"] <= left["tpd"] and center["tpd"] <= right["tpd"]:
                    def objective(x: float) -> float:
                        item = state(x, branch)
                        if item["status"] != "accepted" or not item["mechanically_stable"]:
                            raise ValueError("public branch disappeared inside a sampled basin")
                        return item["g_bar"] - feed_g - slope * (x - feed)

                    try:
                        result = golden_minimize(
                            objective,
                            left["x_methane"],
                            right["x_methane"],
                            maximum_iterations,
                            width,
                        )
                        refined.append({"branch": branch, "mesh_basin": [left["x_methane"], right["x_methane"]], **result})
                    except ValueError as error:
                        refined.append({
                            "branch": branch,
                            "mesh_basin": [left["x_methane"], right["x_methane"]],
                            "converged": False,
                            "failure_reason": str(error),
                        })
        for x in (feed - feed_exclusion, feed + feed_exclusion):
            item = state(x, branch)
            if item["status"] == "accepted" and item["mechanically_stable"]:
                refined.append({
                    "branch": branch,
                    "kind": "feed-exclusion-boundary",
                    "x": x,
                    "value": item["g_bar"] - feed_g - slope * (x - feed),
                    "converged": True,
                })
    return refined


def _topology_intervals(branch_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for branch, rows in branch_rows.items():
        result[branch] = [
            {
                "sampled_lower": segment[0]["x_methane"],
                "sampled_upper": segment[-1]["x_methane"],
                "points": len(segment),
                "density_range_mol_m3": [
                    min(row["molar_density_mol_m3"] for row in segment),
                    max(row["molar_density_mol_m3"] for row in segment),
                ],
                "minimum_pressure_density_derivative_Pa_m3_mol": min(
                    row["pressure_density_derivative_Pa_m3_mol"] for row in segment
                ),
                "maximum_absolute_pressure_residual_Pa": max(
                    abs(row["pressure_residual_Pa"]) for row in segment
                ),
            }
            for segment in _segments(rows)
        ]
    return result


def _environment(import_origin: str) -> dict[str, Any]:
    distributions = sorted(
        (str(item.metadata["Name"]), item.version)
        for item in importlib.metadata.distributions()
        if item.metadata["Name"]
    )
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "python_executable_sha256": sha256_file(Path(sys.executable).resolve()),
        "python_isolated": bool(sys.flags.isolated),
        "platform": platform.platform(),
        "epcsaft_import_origin": import_origin,
        "epcsaft_equilibrium_imported": "epcsaft_equilibrium" in sys.modules,
        "installed_distributions": [{"name": name, "version": version} for name, version in distributions],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not sys.flags.isolated:
        raise RuntimeError("diagnostic must run with Python isolated mode (-I)")
    contract, source_row = _load_contract(args.contract, args.source)
    artifact = _verify_wheel(args.provider_wheel)
    epcsaft = importlib.import_module("epcsaft")
    import_origin = _verify_public_import(epcsaft, artifact["installed_root"])
    model = epcsaft.EPCSAFT(
        epcsaft.ParameterBundle.from_catalog("gross-2001-methane-ethane", version=1).select(
            ("methane", "ethane")
        )
    )
    if model.parameter_fingerprint != PARAMETER_FINGERPRINT:
        raise RuntimeError("installed Provider parameter fingerprint mismatch")

    source = contract["source"]
    numerical = contract["numerical_contract"]
    temperature_k = float(source["temperature_K"])
    pressure_pa = float(source["pressure_Pa"])
    feed = float(source["feed_z_methane"])
    cache: dict[tuple[str, float], dict[str, Any]] = {}

    def state(x: float, branch: str) -> dict[str, Any]:
        key = (branch, float(x))
        if key not in cache:
            cache[key] = _public_state(epcsaft, model, temperature_k, pressure_pa, float(x), branch)
        return cache[key]

    feed_states = [state(feed, branch) for branch in numerical["public_branches"]]
    feed_roots = _root_set(feed_states, 1e-9)
    feed_state = state(feed, "single")
    if feed_state["status"] != "accepted" or not feed_state["mechanically_stable"]:
        raise RuntimeError("homogeneous public feed state is unavailable or mechanically unstable")
    derivative_trace = _derivative_trace(state, feed, numerical["support_derivative_steps"])
    slope = derivative_trace[-1]["slope"]

    mesh_summaries: list[dict[str, Any]] = []
    final_rows: dict[str, list[dict[str, Any]]] = {}
    for points in (
        int(numerical["initial_uniform_mesh_points"]),
        int(numerical["verification_uniform_mesh_points"]),
    ):
        summary, rows = _mesh_scan(
            state,
            feed_state["g_bar"],
            slope,
            feed,
            numerical["composition_domain"],
            points,
            numerical["public_branches"],
            numerical["feed_point_exclusion_absolute"],
        )
        mesh_summaries.append(summary)
        final_rows = rows

    refined = _refine_minima(
        state,
        final_rows,
        feed_state["g_bar"],
        slope,
        feed,
        numerical["feed_point_exclusion_absolute"],
        numerical["golden_section_max_iterations"],
        numerical["golden_section_composition_width"],
    )
    candidates = [
        {"branch": summary["minimum"]["request_branch"], "x": summary["minimum"]["x_methane"], "value": summary["minimum"]["tpd"], "kind": "mesh-minimum"}
        for summary in mesh_summaries
        if summary["minimum"] is not None
    ]
    candidates.extend(item for item in refined if item.get("converged") and "value" in item)
    minimum = min(candidates, key=lambda item: item["value"])

    x_source = float(source["source_liquid_x_methane"])
    y_source = float(source["source_vapor_y_methane"])
    source_x_states = [state(x_source, branch) for branch in numerical["public_branches"]]
    source_y_states = [state(y_source, branch) for branch in numerical["public_branches"]]
    source_x_roots = _root_set(source_x_states, 1e-9)
    source_y_roots = _root_set(source_y_states, 1e-9)
    if not source_x_roots or not source_y_roots:
        raise RuntimeError("an explicit May source composition has no mechanically stable public root")
    source_chords = [
        {
            "source_x_root": left["root_identity"],
            "source_y_root": right["root_identity"],
            "gibbs_chord_minus_homogeneous_feed": (
                0.5 * left["g_bar"] + 0.5 * right["g_bar"] - feed_state["g_bar"]
            ),
        }
        for left in source_x_roots
        for right in source_y_roots
    ]
    source_chord_delta = min(
        item["gibbs_chord_minus_homogeneous_feed"] for item in source_chords
    )

    derivative_delta = abs(derivative_trace[-1]["slope"] - derivative_trace[-2]["slope"])
    mesh_delta = abs(mesh_summaries[-1]["minimum"]["tpd"] - mesh_summaries[-2]["minimum"]["tpd"])
    maximum_distance = max(feed - numerical["composition_domain"][0], numerical["composition_domain"][1] - feed)
    numerical_uncertainty = max(1e-12, derivative_delta * maximum_distance, mesh_delta)
    lower_support_resolved = minimum["value"] < -numerical_uncertainty
    source_chord_above_feed = source_chord_delta > numerical_uncertainty

    all_refinements_converged = all(item.get("converged", False) for item in refined)
    decisions = {
        "artifact_integrity": "PASS",
        "solver": "PASS" if feed_state["mechanically_stable"] and source_x_roots and source_y_roots else "NON_ADMISSION",
        "numerical": "PASS" if all_refinements_converged and derivative_delta <= numerical_uncertainty and mesh_delta <= numerical_uncertainty else "NON_ADMISSION",
        "physical": "PASS" if all(root["mechanically_stable"] for root in feed_roots) else "NON_ADMISSION",
        "predictive_topology": (
            "LOWER_SUPPORT_FOUND"
            if lower_support_resolved
            else "MODEL_DATA_TOPOLOGY_MISS_SUPPORTED"
            if source_chord_above_feed
            else "MODEL_TOPOLOGY_UNRESOLVED"
        ),
        "globality": "NOT_GUARANTEED_FINITE_ADAPTIVE_EVIDENCE",
    }
    status = (
        "DIAGNOSTIC_REVIEW_READY"
        if decisions["artifact_integrity"] == decisions["solver"] == decisions["numerical"] == decisions["physical"] == "PASS"
        else "MODEL_TOPOLOGY_UNRESOLVED"
    )
    receipt = {
        "schema_version": 1,
        "diagnostic_id": contract["diagnostic_id"],
        "status": status,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "contract": {"path": str(args.contract), "sha256": CONTRACT_SHA256},
        "source": {
            "path": str(args.source),
            "sha256": SOURCE_SHA256,
            "row": source_row,
            "citation_locator": source["citation_locator"],
        },
        "artifact": {
            **artifact,
            "implementation_commit": contract["artifact"]["provider_implementation_commit"],
            "candidate_commit": contract["artifact"]["provider_candidate_commit"],
            "parameter_fingerprint": model.parameter_fingerprint,
            "equilibrium_runtime_used": False,
            "equilibrium_context_only": contract["artifact"]["equilibrium_context_only"],
        },
        "environment": _environment(import_origin),
        "objective": contract["objective"],
        "numerical_contract": numerical,
        "feed": {
            "x_methane": feed,
            "state": feed_state,
            "all_public_roots": feed_roots,
            "support_derivative_trace": derivative_trace,
            "support_slope": slope,
        },
        "source_pair": {
            "source_x_composition": x_source,
            "source_y_composition": y_source,
            "source_x_public_requests": source_x_states,
            "source_y_public_requests": source_y_states,
            "source_x_stable_roots": source_x_roots,
            "source_y_stable_roots": source_y_roots,
            "phase_fraction_each": 0.5,
            "root_pair_chords": source_chords,
            "minimum_gibbs_chord_minus_homogeneous_feed": source_chord_delta,
            "above_homogeneous_feed_resolved": source_chord_above_feed,
        },
        "search": {
            "mesh_summaries": mesh_summaries,
            "topology_intervals": _topology_intervals(final_rows),
            "adaptive_minima": refined,
            "minimum_excluding_feed": minimum,
            "evaluated_public_states": len(cache),
            "lower_support_resolved": lower_support_resolved,
            "numerical_uncertainty": numerical_uncertainty,
            "derivative_convergence_delta": derivative_delta,
            "mesh_minimum_convergence_delta": mesh_delta,
            "globality_certificate": "not_guaranteed",
        },
        "decisions": decisions,
        "interpretation": (
            "No lower public-Provider Gibbs support was resolved away from the feed, while the explicit May source x/y chord lies above the homogeneous feed. This supports an installed-Provider model/data predictive-topology miss at row 012; it is not an Equilibrium failure, Provider implementation defect, or mathematical global proof."
            if decisions["predictive_topology"] == "MODEL_DATA_TOPOLOGY_MISS_SUPPORTED"
            else "The bounded diagnostic did not resolve the model topology claim."
        ),
        "limitations": [
            "The search is finite and adaptive but is not a mathematical global proof.",
            "Only public installed Provider pressure states are used; Equilibrium runtime is neither imported nor called.",
            "No package, tolerance, resource, receipt, promotion, or authority is changed.",
        ],
    }
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": status,
        "decisions": decisions,
        "minimum_excluding_feed": minimum,
        "source_chord_minus_feed": source_chord_delta,
        "output": str(args.output.resolve()),
    }, indent=2, sort_keys=True))
    return receipt


def main() -> int:
    run(build_parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
