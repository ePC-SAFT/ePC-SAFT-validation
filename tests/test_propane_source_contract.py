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
TARGET_PATH = ROOT / "data" / "glos-2004-propane-saturation.csv"
SOURCE_RECEIPT_PATH = ROOT / "data" / "glos-2004-propane-saturation-source.csv"
METADATA_PATH = ROOT / "data" / "glos-2004-propane-saturation.yaml"
AUXILIARY_CSV_PATH = ROOT / "data" / "nist-srd69-propane-reference-eos.csv"
AUXILIARY_METADATA_PATH = ROOT / "data" / "nist-srd69-propane-reference-eos.yaml"
CHECKER_PATH = ROOT / "campaigns" / "check_propane_source_contract.py"

EXPECTED_TARGET_SHA256 = "ccd1cfa15ec44432b06cbf22316d168c61b282631c9b1e1591e497b8d48b5676"
EXPECTED_SOURCE_RECEIPT_SHA256 = (
    "ed5eb703ccd3e6bb4c4cfa82ecd58c58f9da0c93ab07a204dee94d8b0ae8d081"
)
EXPECTED_METADATA_SHA256 = "ba31448989f565d05d63908076e836977780aa87199f208310e9b80b03f64697"
EXPECTED_AUXILIARY_CSV_SHA256 = (
    "4a05958854ed5fed28ce4f2b3dc1e98d2d5f833c3eb2f1290ce6428492f0051c"
)
EXPECTED_AUXILIARY_METADATA_SHA256 = (
    "b9cacce71cd0a25fc91cbcb68a7aea28e05d6b171acca9e26fd0ea29259d1587"
)
EXPECTED_OFFICIAL_SOURCE_HASHES = {
    "nist_thermoml_json": "322495c5a01c003e83376e5bad544c3abced330d5054ff0411a7a00b70a963c9",
    "nist_thermoml_xml": "1b2e47d4cafff0f21cf7779d8d01b522bc2fa8d885ce4d6ebc04c151e0504829",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_direct_source_target_and_metadata_are_hash_bound() -> None:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    assert sha256(TARGET_PATH) == EXPECTED_TARGET_SHA256
    assert sha256(SOURCE_RECEIPT_PATH) == EXPECTED_SOURCE_RECEIPT_SHA256
    assert sha256(METADATA_PATH) == EXPECTED_METADATA_SHA256
    assert metadata["citation"]["doi"] == "10.1016/j.jct.2004.07.017"
    assert metadata["citation"]["table_locator"].startswith("Table 2")
    assert {
        name: metadata["sources"][name]["sha256"] for name in EXPECTED_OFFICIAL_SOURCE_HASHES
    } == EXPECTED_OFFICIAL_SOURCE_HASHES
    verification = metadata["source_verification_contract"]["payload"]
    assert verification["mandatory_source_receipt_sha256"] == EXPECTED_SOURCE_RECEIPT_SHA256
    assert verification["required_datasets"] == [1, 2, 3]
    assert verification["required_source_rows"] == 63
    assert metadata["retained_files"]["target_csv"]["sha256"] == EXPECTED_TARGET_SHA256


def test_target_reproduces_receipt_partitions_and_reported_uncertainties() -> None:
    source_rows = read_csv(SOURCE_RECEIPT_PATH)
    target_rows = read_csv(TARGET_PATH)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    source = {
        (int(row["dataset_number"]), int(row["T_K"])): (
            Decimal(row["value"]),
            Decimal(row["expanded_uncertainty"]),
        )
        for row in source_rows
    }

    assert len(source_rows) == 63
    assert len(target_rows) == 24
    assert Counter(row["role"] for row in target_rows) == {
        "training": 4,
        "held_out": 18,
        "stress": 2,
    }
    for row in target_rows:
        temperature = int(row["T_K"])
        pressure, pressure_uncertainty = source[1, temperature]
        liquid_density, liquid_uncertainty = source[2, temperature]
        assert Decimal(row["p_sat_Pa"]) == pressure * 1000
        assert Decimal(row["p_sat_expanded_uncertainty_Pa"]) == pressure_uncertainty * 1000
        assert Decimal(row["rho_sat_liq_kg_m3"]) == liquid_density
        assert Decimal(row["rho_sat_liq_expanded_uncertainty_kg_m3"]) == liquid_uncertainty
        if (3, temperature) in source:
            vapor_density, vapor_uncertainty = source[3, temperature]
            assert Decimal(row["rho_sat_vap_kg_m3"]) == vapor_density
            assert Decimal(row["rho_sat_vap_expanded_uncertainty_kg_m3"]) == vapor_uncertainty
        else:
            assert row["rho_sat_vap_kg_m3"] == ""
            assert row["rho_sat_vap_expanded_uncertainty_kg_m3"] == ""

    comparison = metadata["comparison_contract"]["payload"]
    assert comparison["pressure_comparison_allowance"] is None
    assert comparison["liquid_density_comparison_allowance"] is None
    assert comparison["vapor_density_comparison_allowance"] is None
    assert comparison["model_accuracy_floor"] is None

    auxiliary_metadata = json.loads(AUXILIARY_METADATA_PATH.read_text(encoding="utf-8"))
    auxiliary_rows = read_csv(AUXILIARY_CSV_PATH)
    assert sha256(AUXILIARY_CSV_PATH) == EXPECTED_AUXILIARY_CSV_SHA256
    assert sha256(AUXILIARY_METADATA_PATH) == EXPECTED_AUXILIARY_METADATA_SHA256
    assert "fit_target_contract" not in auxiliary_metadata
    assert all(row["role"] == "reference_only" for row in auxiliary_rows)
    assert "not direct experimental" in auxiliary_metadata["source_audit"]["source_kind"]


def test_checker_is_stdlib_only_and_source_receipt_is_mandatory(tmp_path: Path) -> None:
    imports = {
        (node.module if isinstance(node, ast.ImportFrom) else node.names[0].name).split(".")[0]
        for node in ast.walk(ast.parse(CHECKER_PATH.read_text(encoding="utf-8")))
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node.names
    }
    assert imports <= {
        "__future__",
        "argparse",
        "csv",
        "decimal",
        "hashlib",
        "json",
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
    assert report["source_receipt_verified"] is True
    assert report["rows"] == 24
    assert report["partitions"] == {"training": 4, "held_out": 18, "stress": 2}
    assert report["source_receipt_sha256"] == EXPECTED_SOURCE_RECEIPT_SHA256
    assert report["target_sha256"] == EXPECTED_TARGET_SHA256
    assert report["metadata_sha256"] == EXPECTED_METADATA_SHA256
    assert report["auxiliary_reference_eos"]["role"] == "reference_only"

    missing_receipt = tmp_path / "missing-source-receipt.csv"
    failed = subprocess.run(
        [sys.executable, str(CHECKER_PATH), "--source-receipt", str(missing_receipt)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert failed.returncode != 0
    assert "FileNotFoundError" in failed.stderr
