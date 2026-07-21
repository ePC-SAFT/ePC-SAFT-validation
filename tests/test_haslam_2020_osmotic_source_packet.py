from __future__ import annotations

import ast
import csv
import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "data" / "haslam-2020-osmotic-provider-source-ledger.yaml"
SOURCE_ROW_PATH = ROOT / "data" / "haslam-2020-osmotic-provider-source-row.csv"
CHECKER_PATH = ROOT / "campaigns" / "check_haslam_2020_osmotic_source_packet.py"

EXPECTED_LEDGER_SHA256 = (
    "b12d592b7886e5b8701103c3a41f5b211b3b46b1f5b617f345bc5e3f793c3741"
)
EXPECTED_SOURCE_ROW_SHA256 = (
    "fa2e68e8bc1224f2c6d5b80ad79e6643a08b5944276274067084c40aee2b4f45"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> tuple[dict[str, object], dict[str, str]]:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    with SOURCE_ROW_PATH.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return ledger, rows[0]


def test_source_identities_and_authority_boundary_are_frozen() -> None:
    ledger, _ = load()

    assert sha256(LEDGER_PATH) == EXPECTED_LEDGER_SHA256
    assert sha256(SOURCE_ROW_PATH) == EXPECTED_SOURCE_ROW_SHA256
    assert ledger["decision"] == "PARTIAL_SOURCE_COVERAGE"
    assert ledger["migration_binding"] == {
        "commit": "bcf93699f75278920d094f5dfb4ee0da3b6d83e8",
        "tree": "de17bddbabf2f321696b329cbee961b721a79bdb",
    }
    haslam = ledger["sources"]["haslam_2020"]
    assert haslam["doi"] == "10.1021/acs.jced.0c00746"
    assert haslam["pdf_sha256"] == (
        "ef1d694c61caa1cc9665a9569223d2a7acf3c9b834feea1de9afd9c08e433044"
    )
    assert "printed page 5880, Table 8" in haslam["table_8_locator"]
    assert "printed page 5882" in haslam["condition_locator"]
    hamer = ledger["sources"]["hamer_wu_1972"]
    assert hamer["doi"] == "10.1063/1.3253108"
    assert hamer["official_pdf_sha256"] == (
        "8399084b29b4db4ce35ab47ed679446dbedb9bf1686f99f43fce7b2073ee4beb"
    )
    assert "equations 3.4 prime and 3.5" in hamer["definition_locator"]
    markdown = ledger["sources"]["hamer_wu_mathpix_markdown"]
    assert markdown["sha256"] == (
        "289c44242c919bc5902dc0eff395c20d29a7285e20c9c8e3432cad48461e2d33"
    )
    assert markdown["authority"] == (
        "extraction-only locator and transcription aid; never source authority"
    )


def test_thermodynamic_contract_and_single_nacl_oracle_are_exact() -> None:
    ledger, row = load()

    contract = ledger["thermodynamic_contract"]
    assert contract["quantity"] == "dimensionless practical molal osmotic coefficient"
    assert contract["molality_unit"] == "mol/kg"
    assert "formula-unit molality" in contract["molality"]
    assert "salt-free solvent" in contract["molality"]
    assert "sum of ionic stoichiometric coefficients" in contract["nu"]
    assert "M_solv in kg/mol" in contract["si_equivalent"]
    assert (
        "pure solvent at the same temperature and pressure"
        in contract["solvent_activity"]
    )
    assert contract["temperature_K"] == "298.15"
    assert contract["haslam_pressure_MPa"] == "0.101"

    assert row["salt"] == "NaCl"
    assert row["source_pressure_MPa"] == ""
    assert Decimal(row["target_pressure_MPa"]) == Decimal("0.101")
    assert Decimal(row["molality_mol_kg"]) == Decimal("1.000")
    assert int(row["nu"]) == 2
    assert Decimal(row["phi"]) == Decimal("0.936")
    assert row["source_table"] == "Table 16"
    assert row["source_pdf_page"] == "22"
    assert row["source_printed_page"] == "1067"
    assert row["haslam_exact_selected_subset"] == "false"
    assert "references 181-186" in row["haslam_selection_status"]
    assert "not Haslam Table 8 reproduction" in row["claim_role"]
    assert ledger["exact_oracle"]["haslam_exact_selected_subset"] is False


def test_coverage_gap_and_checker_remain_compact_and_model_free() -> None:
    ledger, _ = load()

    coverage = ledger["provider_six_salt_coverage"]
    assert {entry["salt"] for entry in coverage} == {
        "LiCl",
        "LiBr",
        "NaCl",
        "NaBr",
        "KCl",
        "KBr",
    }
    assert all(entry["provider_catalog"] == "supported" for entry in coverage)
    assert all(entry["exact_haslam_rows_in_packet"] == 0 for entry in coverage)
    assert all(
        entry["selection_status"] == "unknown-missing-row-selection-manifest"
        for entry in coverage
    )
    iodides = ledger["unsupported_haslam_scope"]["iodides"]
    assert {entry["salt"] for entry in iodides} == {"LiI", "NaI", "KI"}
    assert all("I-minus-absent" in entry["status"] for entry in iodides)
    selection = ledger["haslam_selection_provenance"]
    assert selection["classification"] == "unknown-missing-row-selection-manifest"
    assert "cannot establish full Haslam Table 8 reproduction" in selection["effect"]

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
        "csv",
        "decimal",
        "hashlib",
        "json",
        "pathlib",
    }
    checker_source = CHECKER_PATH.read_text(encoding="utf-8")
    assert "import epcsaft" not in checker_source
    assert "reference_state(" not in checker_source

    completed = subprocess.run(
        [sys.executable, str(CHECKER_PATH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "PARTIAL_SOURCE_COVERAGE"
    assert report["source_rows"] == 1
    assert report["haslam_exact_selected_rows"] == 0
    assert report["model_output"] == "not_run"
    assert report["source_row_sha256"] == EXPECTED_SOURCE_ROW_SHA256
    assert report["ledger_sha256"] == EXPECTED_LEDGER_SHA256
