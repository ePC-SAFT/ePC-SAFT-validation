from __future__ import annotations

import ast
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "nist-srd69-propane-saturation.csv"
METADATA_PATH = ROOT / "data" / "nist-srd69-propane-saturation.yaml"
CHECKER_PATH = ROOT / "campaigns" / "check_nist_propane_source.py"
EXPECTED_CSV_SHA256 = "a70ba0e6e1401b8b72bffb7958b0038f18fc44b560c847dcd2323cea740e5138"
EXPECTED_METADATA_SHA256 = "c8b803f0ec85e2bcfd050da1ba16a8da98323a1dd0c370ad4ada572d31f6524e"
EXPECTED_SOURCE_HASHES = {
    "nist_query_download": "e98f6e71594eef0aaa786e84080a69c163b595e898bd5d34bd94081b55fc3da4",
    "nist_query_page": "1240d7da467561f554801996f34c94791e7e65e8566ace01d0f0c3bad7b67acc",
    "nist_recommended_citation": "b52cde42af9090457a4112956a8e2b749d8202d725ba1595daf875c1ecf8466e",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_contract() -> tuple[list[dict[str, str]], dict[str, object]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return rows, metadata


def test_retained_target_and_official_sources_are_hash_bound() -> None:
    rows, metadata = load_contract()

    assert len(rows) == 14
    assert sha256(CSV_PATH) == EXPECTED_CSV_SHA256
    assert sha256(METADATA_PATH) == EXPECTED_METADATA_SHA256
    assert metadata["citation"]["doi"] == "10.18434/T4D303"
    assert metadata["reference_equation"]["doi"] == "10.1021/je900217v"
    assert {
        name: source["sha256"] for name, source in metadata["sources"].items()
    } == EXPECTED_SOURCE_HASHES
    assert metadata["retained_files"]["csv"]["sha256"] == EXPECTED_CSV_SHA256


def test_rows_freeze_units_partitions_uncertainties_and_no_model_allowance() -> None:
    rows, metadata = load_contract()

    temperatures = [int(float(row["T_K"])) for row in rows]
    assert temperatures == list(range(100, 361, 20))
    assert Counter(row["role"] for row in rows) == {
        "training": 4,
        "held_out": 8,
        "stress": 2,
    }
    assert [int(float(row["T_K"])) for row in rows if row["role"] == "training"] == [
        160,
        220,
        280,
        340,
    ]
    assert rows[0]["p_sat_Pa"] == "0.025272318"
    assert rows[0]["rho_sat_liq_kg_m3"] == "718.14791"
    assert rows[-1]["p_sat_Pa"] == "3554538.7"
    assert rows[-1]["rho_sat_liq_kg_m3"] == "345.58350"
    assert rows[0]["source_pressure_relative_uncertainty"] == ""
    assert rows[-1]["source_liquid_density_relative_uncertainty"] == ""
    assert all(row["component_id"] == "propane" for row in rows)

    comparison = metadata["comparison_contract"]["payload"]
    assert comparison["pressure_comparison_allowance"] is None
    assert comparison["liquid_density_comparison_allowance"] is None
    assert comparison["model_accuracy_floor"] is None


def test_checker_is_stdlib_only_and_accepts_the_frozen_contract() -> None:
    imports = {
        (node.module if isinstance(node, ast.ImportFrom) else node.names[0].name).split(".")[0]
        for node in ast.walk(ast.parse(CHECKER_PATH.read_text(encoding="utf-8")))
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node.names
    }
    assert imports <= {
        "__future__",
        "argparse",
        "csv",
        "hashlib",
        "json",
        "math",
        "pathlib",
    }

    completed = subprocess.run(
        [sys.executable, str(CHECKER_PATH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "accepted"
    assert report["rows"] == 14
    assert report["partitions"] == {"training": 4, "held_out": 8, "stress": 2}
    assert report["csv_sha256"] == EXPECTED_CSV_SHA256
    assert report["metadata_sha256"] == EXPECTED_METADATA_SHA256
    assert report["download_verified"] is False
