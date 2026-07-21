from __future__ import annotations

import ast
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "data" / "perdomo-2025-held2-case-ledger.csv"
SAMPLES_PATH = ROOT / "data" / "perdomo-2025-held2-published-samples.csv"
METADATA_PATH = ROOT / "data" / "perdomo-2025-held2-source-ledger.yaml"
CHECKER_PATH = ROOT / "campaigns" / "check_perdomo_2025_source_ledger.py"

EXPECTED_CASES_SHA256 = (
    "279a1ff76efdca4a27032fea841bdb1e6127ada334b14871e46b13683cb1bcf8"
)
EXPECTED_SAMPLES_SHA256 = (
    "92338efdb800f8a4546a0ed9bbd0944021586735c181963057c86e3e9b4f7c1f"
)
EXPECTED_METADATA_SHA256 = (
    "28d008aa6e56d4f3faeae0ffeea4967cee931941530f27b48a4f31ea5b797d7f"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, object]]:
    with CASES_PATH.open(newline="", encoding="utf-8") as stream:
        cases = list(csv.DictReader(stream))
    with SAMPLES_PATH.open(newline="", encoding="utf-8") as stream:
        samples = list(csv.DictReader(stream))
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return cases, samples, metadata


def test_source_identities_counts_and_case_classes_are_frozen() -> None:
    cases, samples, metadata = load()

    assert sha256(CASES_PATH) == EXPECTED_CASES_SHA256
    assert sha256(SAMPLES_PATH) == EXPECTED_SAMPLES_SHA256
    assert sha256(METADATA_PATH) == EXPECTED_METADATA_SHA256
    assert len(cases) == 9
    assert len(samples) == 26
    assert sum(int(row["published_flash_count"]) for row in cases) == 122917
    assert Counter(row["reproducibility_classification"] for row in cases) == {
        "cross-eos-epcsaft-challenge-only": 8,
        "algorithmic-manufactured-only": 1,
    }
    assert Counter(row["source_table"] for row in samples) == {
        "Table 3": 3,
        "Table 4": 3,
        "Table 5": 3,
        "Table 6": 6,
        "Table 7": 4,
        "Table 8": 7,
    }
    assert {
        name: source["sha256"] for name, source in metadata["bound_sources"].items()
    } == {
        "zotero_markdown": "a55846342ac6a73379b2267c24d6e9bf792637aea1d66bd26b50e0230429b727",
        "permanent_lab_markdown": "522cba2efb44c6404b3b8b75eefb90c50a84cc4110333f30aa1f0eb1a21380d5",
        "article_pdf_visual_audit": "8be02605fc0e839c368362a80837ae2d4f029f97ba7ba6dc60b486548a790111",
        "official_supporting_workbook": "c659847256044fb783c3fe090454103e109cd13cb5696bb715910428f9935834",
    }
    assert metadata["citation"]["doi"] == "10.1016/j.compchemeng.2024.108977"
    assert metadata["citation"]["supporting_data_doi"] == "10.5281/zenodo.13646853"


def test_closest_tracer_arithmetic_and_source_anomaly_are_explicit() -> None:
    cases, samples, metadata = load()

    selected = next(
        row for row in samples if row["sample_id"] == "table5-licl-4.58molal"
    )
    organic = [Decimal(value) for value in selected["phase_1_x"].split("|")]
    aqueous = [Decimal(value) for value in selected["phase_2_x"].split("|")]
    midpoint = [
        (left + right) / 2 for left, right in zip(organic, aqueous, strict=True)
    ]
    recommendation = metadata["recommended_first_tracer"]
    assert midpoint == [
        Decimal(value) for value in recommendation["raw_equal_phase_midpoint"]
    ]
    normalized = [value / sum(midpoint) for value in midpoint]
    assert all(
        abs(left - Decimal(right)) <= Decimal("1e-28")
        for left, right in zip(
            normalized, recommendation["normalized_equal_phase_feed"], strict=True
        )
    )
    assert normalized[0] == normalized[1]
    assert sum(normalized) == Decimal(1)
    selected_case = next(
        row for row in cases if row["case_id"] == recommendation["case_id"]
    )
    assert selected_case["species_order"] == "Li+|Cl-|water|1-butanol"
    assert selected_case["charges"] == "+1|-1|0|0"
    assert recommendation["status"] == "not_selected_source_incomplete"
    assert recommendation["source_completeness"] == "blocked_missing_epcsaft_records"
    assert set(recommendation["future_decisions"].values()) == {"not_run"}

    anomalies = [row for row in samples if row["source_anomaly"]]
    assert [row["sample_id"] for row in anomalies] == [
        "table3-kcl-0.8molal",
        "table8-wap0.0460",
    ]
    charge_anomaly = next(
        row for row in anomalies if row["sample_id"] == "table8-wap0.0460"
    )
    anomalous_aqueous = [
        Decimal(value) for value in charge_anomaly["phase_1_x"].split("|")
    ]
    assert anomalous_aqueous[1] != 2 * anomalous_aqueous[0]
    anomaly_contracts = metadata["published_sample_contract"]["source_anomalies"]
    assert [item["sample_id"] for item in anomaly_contracts] == [
        "table3-kcl-0.8molal",
        "table8-wap0.0460",
    ]
    assert all("never silently correct" in item["policy"] for item in anomaly_contracts)


def test_d026_screen_has_no_source_complete_perdomo_lle_and_freezes_fallback() -> None:
    cases, _, metadata = load()
    screen = metadata["d026_epcsaft_two_liquid_screen"]

    assert screen["migration_binding"] == {
        "decision": "D-026",
        "gate_commit": "3a4ef0a0c6b98c43405d3cafc1ac4f5f87afa68d",
        "gate_tree": "9307c3f79581b6e0479d4ac2468932b2a68e5f5b",
    }
    assert screen["decision"] == "NO_SOURCE_COMPLETE_PERDOMO_TWO_LIQUID_CASE"
    assert screen["screen_counts"] == {
        "cases_screened": 9,
        "ineligible_not_two_liquid": 5,
        "two_liquid_blocked_source_records": 4,
        "source_complete_two_liquid": 0,
    }
    closest = next(
        row for row in cases if row["case_id"] == "perdomo2025-licl-water-butanol-lle"
    )
    assert (
        closest["recommendation_role"]
        == "closest-perdomo-candidate-blocked-source-records"
    )
    blocked = [
        row
        for row in screen["case_screen"]
        if row["outcome"] == "blocked_source_records"
    ]
    assert len(blocked) == 4
    closest_screen = next(
        row for row in blocked if row["case_id"] == closest["case_id"]
    )
    missing = " ".join(closest_screen["missing_records_or_sources"])
    assert "Li+-1-butanol k_ij" in missing
    assert "Li+-1-butanol" in missing and "l_ij semantics" in missing
    assert "isobutanol" in " ".join(closest_screen["non_substitutions"])
    fallback = screen["fallback"]
    assert fallback["case_id"] == "ascani2022-case-study-2"
    assert fallback["remaining_source_gaps"] == []
    assert fallback["source_status"] == (
        "SOURCE_COMPLETE_FOR_BOUNDED_ASCANI_EPCSAFT_ADVANCED_MODEL"
    )
    assert fallback["provider_gap"].startswith("PROVIDER_NOT_YET_CAPABLE")
    assert "Na+-K+ NOT_APPLICABLE" in " ".join(fallback["provider_construction_gaps"])
    ascani_binding = screen["provider_source_snapshot"]["bound_validation_packets"][
        "ascani_case_study_2_source_contract"
    ]
    assert sha256(ROOT / ascani_binding["path"]) == ascani_binding["sha256"]
    assert (
        screen["equilibrium_status"]["classification"] == "READY_WAITING_PROVIDER_CASE"
    )


def test_checker_is_stdlib_only_and_source_packet_remains_model_free() -> None:
    _, _, metadata = load()
    imports = {
        (node.module if isinstance(node, ast.ImportFrom) else node.names[0].name).split(
            "."
        )[0]
        for node in ast.walk(ast.parse(CHECKER_PATH.read_text(encoding="utf-8")))
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node.names
    }
    assert imports <= {
        "__future__",
        "argparse",
        "collections",
        "csv",
        "decimal",
        "hashlib",
        "json",
        "pathlib",
    }
    checker_source = CHECKER_PATH.read_text(encoding="utf-8")
    assert "import epcsaft" not in checker_source
    assert "import epcsaft_equilibrium" not in checker_source
    assert "import epcsaft_provider" not in checker_source
    assert (
        metadata["recommended_first_tracer"]["globality_certificate"]
        == "not_guaranteed"
    )
    claim_boundary = " ".join(metadata["claim_boundary"])
    for phrase in (
        "No Provider or Equilibrium runtime",
        "No EOS substitution",
        "not direct experimental observations",
        "not automatically an algorithm defect",
    ):
        assert phrase in claim_boundary

    completed = subprocess.run(
        [sys.executable, str(CHECKER_PATH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "no_source_complete_perdomo_two_liquid_case"
    assert report["cases"] == 9
    assert report["published_samples"] == 26
    assert report["model_output"] == "not_run"
    assert report["selected_case"] is None
    assert report["fallback_case"] == "ascani2022-case-study-2"
    assert report["case_ledger_sha256"] == EXPECTED_CASES_SHA256
    assert report["published_samples_sha256"] == EXPECTED_SAMPLES_SHA256
    assert report["metadata_sha256"] == EXPECTED_METADATA_SHA256
