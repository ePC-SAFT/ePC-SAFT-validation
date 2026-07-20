import ast
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "neutral_held_v1.py"
PLOTTER = ROOT / "campaigns" / "plot_neutral_held_v1.py"
RECORD = ROOT / "results" / "neutral-held-v1-validation.json"


def _load_campaign():
    spec = importlib.util.spec_from_file_location("neutral_held_v1", CAMPAIGN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_requires_exact_artifact_source_and_output_inputs() -> None:
    campaign = _load_campaign()
    parser = campaign.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    required = {
        "provider_wheel",
        "equilibrium_wheel",
        "candidate_receipt",
        "cases",
        "source",
        "output_dir",
    }
    assert required <= {action.dest for action in parser._actions}


def test_sampled_oracle_flags_points_below_a_line_only_beyond_allowance() -> None:
    campaign = _load_campaign()
    rows = [
        {"status": "accepted", "x_methane": 0.25, "g_bar": 1.2500005},
        {"status": "accepted", "x_methane": 0.50, "g_bar": 1.4999980},
        {"status": "failed", "x_methane": 0.75, "g_bar": ""},
    ]
    audit = campaign.audit_line(rows, intercept=1.0, slope=1.0, allowance=1e-6)
    assert audit["accepted_points"] == 2
    assert audit["violating_points"] == 1
    assert audit["minimum_gap"] == pytest.approx(-2e-6)
    assert audit["status"] == "FAIL"


def test_result_contract_separates_artifact_solver_numerical_physical_and_prediction() -> None:
    campaign = _load_campaign()
    receipt = {
        "globality_certificate": "not_guaranteed",
        "decisions": {
            "artifact_integrity": "PASS",
            "solver": "PASS",
            "numerical": "PASS",
            "physical": "PASS",
            "sampled_phase_set": "PASS",
            "predictive_agreement": "NON_ADMISSION",
        },
    }
    rows = [
        {
            "case_id": f"case-{index}",
            "globality_certificate": "not_guaranteed",
            "solver_status": "passed",
            "numerical_status": "passed",
            "physical_status": "passed",
        }
        for index in range(18)
    ]
    campaign.validate_result_contract(receipt, rows)
    bad = dict(receipt)
    bad["globality_certificate"] = "guaranteed"
    with pytest.raises(ValueError, match="globality"):
        campaign.validate_result_contract(bad, rows)


def test_campaign_and_plotter_use_no_private_or_sibling_package_imports() -> None:
    campaign_tree = ast.parse(CAMPAIGN.read_text(encoding="utf-8"))
    plot_tree = ast.parse(PLOTTER.read_text(encoding="utf-8"))
    campaign_imports = {
        alias.name
        for node in ast.walk(campaign_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    plot_imports = {
        alias.name
        for node in ast.walk(plot_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(name.startswith(("epcsaft._", "epcsaft_equilibrium._")) for name in campaign_imports)
    assert not any(name.startswith(("epcsaft", "epcsaft_equilibrium")) for name in plot_imports)


def test_retained_installed_artifact_evidence_is_hash_bound_and_non_global() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    assert record["globality_certificate"] == "not_guaranteed"
    assert record["artifacts"]["provider"]["sha256"] == "17c6735ee117469b13b76b6a669d0b4430071c8eaebdf1e405baefc9adcb838b"
    assert record["artifacts"]["equilibrium"]["sha256"] == "8ecd70e0192b76b3a107629201c3e8bf34f2d945ca7c8192f824a0df7c9dde12"
    assert record["artifacts"]["candidate_receipt"]["sha256"] == "a8a1fe6f0836cef3afd9edfe390fb2d131b1a7a441e160f4cd7176524038dc30"
    assert record["counts"]["cases"] == 18
    assert record["counts"]["sampled_rows"] == 9009
    assert record["decisions"]["artifact_integrity"] == "PASS"
    assert record["decisions"]["installed_artifact_campaign"] == "NON_ADMISSION"
    assert record["decisions"]["predictive_agreement"] == "NON_ADMISSION"
    for output in ("cases_csv", "sampled_gibbs_csv"):
        item = record["outputs"][output]
        path = Path(item["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    for bundle in record["outputs"]["plots"].values():
        for item in bundle.values():
            path = Path(item["path"])
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    with Path(record["outputs"]["cases_csv"]["path"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 18
    assert all(row["globality_certificate"] == "not_guaranteed" for row in rows)
