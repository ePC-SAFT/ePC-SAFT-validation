import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "may-2015-neutral-held-cases.yaml"
CHECKER = ROOT / "campaigns" / "check_neutral_held_cases.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_neutral_held_cases", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_case_contract_is_source_only_and_complete() -> None:
    checker = _load_checker()
    summary = checker.check(CASES, ROOT / "data" / "may-2015-methane-ethane-vle.csv")
    assert summary["status"] == "cases_ready"
    assert summary["case_count"] == 18
    assert summary["midpoint_cases"] == 17
    assert summary["one_phase_cases"] == 1
    assert summary["sampled_audit_cases"] == 3


def test_row_011_liquid_case_is_the_frozen_source_backed_inference() -> None:
    contract = json.loads(CASES.read_text(encoding="utf-8"))
    derived = next(case for case in contract["cases"] if case["case_id"] == "may2015-row-011-liquid-side")
    assert derived["source_row_id"] == "may2015-ch4-c2h6-011"
    assert derived["feed_z_methane"] == 0.5627
    assert derived["derivation"] == "x_methane - 2*x_comparison_allowance"
    assert derived["expected_phase_count"] == 1
    assert derived["phase_count_evidence"] == "source-backed-inference"


def test_sampled_audit_grid_and_no_model_outputs_are_frozen() -> None:
    contract = json.loads(CASES.read_text(encoding="utf-8"))
    audit = contract["sampled_gibbs_audit"]
    assert audit["case_ids"] == [
        "may2015-row-001-midpoint",
        "may2015-row-012-midpoint",
        "may2015-row-011-liquid-side",
    ]
    assert audit["composition_grid"]["points"] == 1001
    assert audit["composition_grid"]["minimum"] == 1e-8
    assert audit["composition_grid"]["maximum"] == 1.0 - 1e-8
    assert audit["dimensionless_tangent_chord_allowance"] == 1e-6
    forbidden = {"model_output", "held_output", "phase_fractions", "model_phases"}
    for case in contract["cases"]:
        assert forbidden.isdisjoint(case)
