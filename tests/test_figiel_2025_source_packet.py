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
LEDGER_PATH = ROOT / "data" / "figiel-2025-regression-target-ledger.csv"
PARAMETER_PATH = ROOT / "data" / "figiel-2025-parameter-provenance.csv"
METADATA_PATH = ROOT / "data" / "figiel-2025-regression-target-ledger.yaml"
CHECKER_PATH = ROOT / "campaigns" / "check_figiel_2025_source_packet.py"

EXPECTED_LEDGER_SHA256 = "f405a3e48d21cd979a8dd480d5f8cb3be40754f5d6babf368b505b5f305607f0"
EXPECTED_PARAMETER_SHA256 = "932e8baa90fcefbaa8c3a8730cdeadd83a4c01f0a3b109f4e4cd0319aee9312b"
EXPECTED_METADATA_SHA256 = "8ea06c6ca5452d01448a03f9a76cf7d0c35bb99c9abe23ccb1729d56c71d468f"
EXPECTED_SI_SHA256 = "005b38ed566ec3c09b87e1ca3a9dd6eeafc9ba75e1a30b9322291d770bb93895"
MAIN_MARKDOWN_SHA256 = "ce80533925a91bc59d8d0d8056113c40611ca26c2edf04aced76986d50bd4bae"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_source_identity_ledger_and_classifications_are_hash_bound() -> None:
    ledger = read_csv(LEDGER_PATH)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    assert sha256(LEDGER_PATH) == EXPECTED_LEDGER_SHA256
    assert sha256(METADATA_PATH) == EXPECTED_METADATA_SHA256
    assert len(ledger) == 407
    assert len({row["target_id"] for row in ledger}) == 407
    assert Counter(row["source_classification"] for row in ledger) == {
        "direct": 191,
        "table-derived": 47,
        "digitized": 90,
        "constructed": 43,
        "missing-primary-source": 36,
    }
    assert all(not row["uncertainty_value"] and not row["uncertainty_unit"] for row in ledger)
    assert metadata["citation"]["main_doi"] == "10.1021/acs.iecr.5c00475"
    assert metadata["citation"]["supporting_information_doi"] == "10.1021/acs.iecr.5c00475.s001"
    si = metadata["official_sources"]["official_si_pdf"]
    assert (si["figshare_article_id"], si["figshare_file_id"]) == (28888514, 54030209)
    assert si["size_bytes"] == 396182
    assert si["md5"] == "4c3d3964d6e61b908c3ce3b17bb4e6b0"
    assert si["sha256"] == EXPECTED_SI_SHA256
    assert metadata["migration_binding"] == {
        "decision": "D-023",
        "gate_commit": "9ceb1dae796b44fad7789762efcca9c11491e9c2",
        "gate_tree": "6757a261bffb9486a25f45194bde870605094bb0",
    }


def test_si_tables_and_equation_19_construction_remain_source_faithful() -> None:
    rows = read_csv(LEDGER_PATH)
    residual_averages = {
        row["species"]: Decimal(row["value"])
        for row in rows
        if row["role"] == "reported_average_target"
    }
    assert residual_averages == {
        "Li+": Decimal("-486.2"),
        "Na+": Decimal("-381.1"),
        "K+": Decimal("-309.1"),
        "Cl-": Decimal("-314.9"),
        "Br-": Decimal("-290.9"),
    }
    later_averages = {
        row["species"]: Decimal(row["value"])
        for row in rows
        if row["role"] == "reported_average_later_gate"
    }
    assert later_averages == {
        "H+": Decimal("-1094.5"),
        "I-": Decimal("-252.6"),
        "SO4^2-": Decimal("-1062.1"),
        "VO^2+": Decimal("-1895.0"),
        "V^3+": Decimal("-4202.1"),
    }
    averages = residual_averages | later_averages
    assert sum(row["role"] == "underlying_literature_value" for row in rows) == 37
    first_support = [row for row in rows if row["tracer_status"] == "first_tracer_support"]
    assert len(first_support) == 32
    assert {row["source_id"] for row in first_support} == {"figiel-2025-official-si"}
    assert {
        row["species"] for row in first_support
    } == {"Li+", "Na+", "K+", "Cl-", "Br-"}
    hamer = [
        row for row in rows if row["source_id"] == "hamer-wu-1972-aqueous-alkali-halides"
    ]
    assert len(hamer) == 164
    assert all(row["tracer_status"] == "later_capability_gate" for row in hamer)
    assert sum(row["quantity"] == "solution_mass_density" for row in rows) == 22
    assert sum(row["quantity"] == "osmotic_coefficient" for row in rows) == 5

    transfers = {
        (row["species"], row["solvent"], row["composition_value"]): Decimal(row["value"])
        for row in rows
        if row["role"] == "ion_organic_solvation_construction_input"
    }
    constructed = [row for row in rows if row["role"] == "constructed_ion_solvation_target"]
    assert len(transfers) == len(constructed) == 43
    for row in constructed:
        key = (row["species"], row["solvent"], row["composition_value"])
        assert Decimal(row["value"]) == averages[row["species"]] + transfers[key]


def test_parameter_provenance_covers_tables_without_promoting_blanks() -> None:
    rows = read_csv(PARAMETER_PATH)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    assert sha256(PARAMETER_PATH) == EXPECTED_PARAMETER_SHA256
    assert len(rows) == 122
    assert Counter(row["provenance_classification"] for row in rows) == {
        "fitted-in-Figiel-2025": 57,
        "inherited-from-cited-source": 33,
        "fixed-or-assumed": 13,
        "blank-or-unpublished": 19,
    }
    assert Counter(row["recovery_target"] for row in rows) == {"true": 90, "false": 32}
    assert all(row["source_artifact_sha256"] == MAIN_MARKDOWN_SHA256 for row in rows)
    assert all(
        row["provenance_classification"] == "blank-or-unpublished"
        and row["recovery_target"] == "false"
        for row in rows
        if not row["reported_value"]
    )
    assert all(
        row["provenance_classification"] == "fitted-in-Figiel-2025"
        and row["recovery_target"] == "true"
        for row in rows
        if row["reported_value"] == "0"
    )
    assert {row["cell_id"] for row in rows if row["reported_value"] == "0"} == {
        "t4-K+-Cl-",
        "t4-K+-I-",
        "t4-VO^2+-SO4^2-",
        "t5-Br--ethanol",
        "t5-H+-water",
    }

    stage_a = [row for row in rows if row["staged_order"] == "A"]
    assert {(row["component_i"], row["parameter"]) for row in stage_a} == {
        (ion, "born_diameter") for ion in ("Li+", "Na+", "K+", "Cl-", "Br-")
    }
    assert all(row["provenance_classification"] == "fitted-in-Figiel-2025" for row in stage_a)
    table2_f = [row for row in rows if row["parameter"] == "solvent_solvation_factor"]
    assert {row["component_i"]: row["reported_value"] for row in table2_f} == {
        "water": "1.5",
        "methanol": "1.4",
        "ethanol": "1.6",
    }
    assert all(row["provenance_classification"] == "fitted-in-Figiel-2025" for row in table2_f)
    ordinary = [
        row
        for row in rows
        if row["source_location"].startswith("main paper Table 3")
        and row["component_i"] in {"Li+", "Na+", "K+", "Cl-", "Br-"}
        and row["parameter"] in {"segment_diameter", "dispersion_energy_over_k"}
    ]
    assert len(ordinary) == 10
    assert all(row["provenance_classification"] == "inherited-from-cited-source" for row in ordinary)
    assert metadata["retained_files"]["parameter_provenance"]["sha256"] == EXPECTED_PARAMETER_SHA256
    assert set(metadata["staged_parameter_recovery"]) == set("ABCDEFGH")


def test_checker_is_stdlib_only_and_does_not_depend_on_local_source_paths() -> None:
    imports = {
        (node.module if isinstance(node, ast.ImportFrom) else node.names[0].name).split(".")[0]
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
    assert "/home/tnnrpolley21/Zotero" not in checker_source
    assert "/home/tnnrpolley21/Workspaces/Engineering/ePC-SAFT/" not in checker_source

    completed = subprocess.run(
        [sys.executable, str(CHECKER_PATH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "source_packet_ready"
    assert report["ledger_rows"] == 407
    assert report["parameter_provenance"] == {
        "rows": 122,
        "recovery_targets": 90,
        "non_targets": 32,
    }
    assert report["comparison_threshold"] is None
