from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
CHECKER = ROOT / "campaigns" / "check_haslam_2020_source_packet.py"
CAMPAIGN = ROOT / "campaigns" / "haslam_2020_table8.py"
PLOTTER = ROOT / "campaigns" / "plot_haslam_2020_table8.py"
MANIFEST = ROOT / "results" / "haslam-2020-table8-manifest.json"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_packet_reproduces_only_identified_table8_subsets() -> None:
    result = _load(CHECKER).validate()
    assert result["status"] == "source_packet_ready_partial_coverage"
    assert result["rows"] == 207
    assert result["exact_phi_rows"] == 0
    assert result["exact_gamma_rows"] == 161


def test_conventional_cross_eos_aad_is_explicitly_not_source_verified() -> None:
    campaign = _load(CAMPAIGN)
    assert campaign.percent_aad([1.0, 2.0], [1.1, 1.8]) == pytest.approx(10.0)
    source = CAMPAIGN.read_text(encoding="utf-8")
    assert "method_assumption" in source
    assert "Haslam pointwise AAD equation was not located" in source


def test_campaign_and_plotter_have_no_private_or_sibling_runtime_imports() -> None:
    for path in (CAMPAIGN, PLOTTER):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert not any(name.startswith("epcsaft._") for name in imports)
        assert not any("lab" in name or "migration" in name for name in imports)


def test_retained_manifest_hashes_and_aads_recompute() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for item in manifest["retained_files"].values():
        path = ROOT / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    with (ROOT / "results/haslam-2020-table8.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    with (ROOT / "results/haslam-2020-table8-aad-comparison.csv").open(
        newline=""
    ) as stream:
        comparison = list(csv.DictReader(stream))
    campaign = _load(CAMPAIGN)
    receipt = json.loads(
        (ROOT / "results/haslam-2020-table8.json").read_text(encoding="utf-8")
    )
    assert receipt["artifact"]["sha256"] == (
        "961156a641435e33746a65d07d97e07a40243e0cfdf870932bd79961783afa96"
    )
    assert receipt["coverage"]["evaluated_rows"] == 368
    assert receipt["coverage"]["not_evaluated_rows"] == 46
    assert receipt["coverage"]["exact_table8_gamma_rows_evaluated"] == 138
    assert {
        (row["salt"], row["observable"])
        for row in rows
        if row["artifact_status"] == "NOT_EVALUATED"
    } == {("LiI", "gamma_pm_m"), ("LiI", "osmotic_coefficient")}
    for summary in comparison:
        if not summary["current_epcsaft_aad_percent"]:
            continue
        selected = [
            row
            for row in rows
            if row["salt"] == summary["salt"]
            and row["observable"] == summary["observable"]
            and row["artifact_status"] == "EVALUATED"
        ]
        assert campaign.percent_aad(
            [float(row["literature_value"]) for row in selected],
            [float(row["model_value"]) for row in selected],
        ) == pytest.approx(float(summary["current_epcsaft_aad_percent"]))
