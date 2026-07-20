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
CSV_PATH = ROOT / "data" / "khudaida-2026-held2-tracer.csv"
METADATA_PATH = ROOT / "data" / "khudaida-2026-held2-tracer.yaml"
CHECKER_PATH = ROOT / "campaigns" / "check_khudaida_2026_source_contract.py"

EXPECTED_CSV_SHA256 = "cf048a88f19592b600d6a228ee46cdffc7fb64965108318796cd3d1b28553c24"
EXPECTED_METADATA_SHA256 = "1ac8423a5568fcf16c149d303cd9a0c11b8d33771c9fae6bfaa12f4224d866f5"
EXPECTED_SOURCE_HASHES = {
    "main_markdown": "fc8feed1b91c17b0e03610dab2c86d989dccce342a72bf5f38285c3a4466954e",
    "supporting_information_markdown": "71a6aec2ba260196b0e15a2c09e8f69b7e44dc0c131def96eecfc10fdeb337be",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> tuple[dict[str, str], dict[str, object]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return rows[0], json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def test_source_identity_and_distilled_table_hashes_are_frozen() -> None:
    _, metadata = load()

    assert sha256(CSV_PATH) == EXPECTED_CSV_SHA256
    assert sha256(METADATA_PATH) == EXPECTED_METADATA_SHA256
    assert metadata["migration_binding"] == {
        "decision": "D-024",
        "gate_commit": "97c3467232c5fbab1ce67ebd2353801ae13d17e0",
        "gate_tree": "17b72e724a2a70e4f7c5d9b8aa4d8558ef2992df",
    }
    assert {
        name: source["sha256"] for name, source in metadata["primary_sources"].items()
    } == EXPECTED_SOURCE_HASHES
    assert metadata["lab_distillation"]["retained_table_hashes"] == {
        "tables_3_4_experimental_tielines_csv": "8eb728633eed0a9ab6afb477e834e801c68ff86eb4c656cc46a8eb09c7166a1c",
        "table_5_pure_component_parameters_csv": "2a1dea257bc42bb11934a49e88ef8359b8472996fd926611eb2c0d2fe78cfda1",
        "table_6_relative_dielectric_constants_csv": "708573ca37adef83cd9d3be3b286eaacf05243dde286b3308abeb05d9afeb4b0",
        "table_7_epcsaft_kij_csv": "4dda028bac9903c4722a628127be9470e644ccb52b7b7c9ae37386b61e51fb1b",
    }


def test_first_tracer_preserves_formula_midpoint_and_dissociated_amount_basis() -> None:
    row, metadata = load()

    organic = [Decimal(row[f"organic_x_{name}_formula"]) for name in ("water", "ethanol", "isobutanol", "nacl")]
    aqueous = [Decimal(row[f"aqueous_x_{name}_formula"]) for name in ("water", "ethanol", "isobutanol", "nacl")]
    midpoint = [Decimal(value) for value in metadata["tracer_contract"]["equal_formula_mole_midpoint"]]
    assert midpoint == [(left + right) / 2 for left, right in zip(organic, aqueous, strict=True)]
    explicit = [Decimal(value) for value in metadata["tracer_contract"]["explicit_species_amounts"]]
    assert explicit == [
        Decimal("0.65905"),
        Decimal("0.05095"),
        Decimal("0.27015"),
        Decimal("0.01985"),
        Decimal("0.01985"),
    ]
    assert sum(midpoint) == Decimal(1)
    assert sum(explicit) == Decimal("1.01985")
    assert explicit[-2] == explicit[-1]

    bundle = metadata["published_model_bundle"]
    explicit_zeros = {
        tuple(entry["pair"]): entry
        for entry in bundle["table_7_kij"]
        if entry["value"] == "0"
    }
    assert set(explicit_zeros) == {("isobutanol", "Na+"), ("isobutanol", "Cl-")}
    assert all(
        entry["provenance"] == "explicit-published-zero-missing-upstream-reference"
        and entry["reference"] is None
        for entry in explicit_zeros.values()
    )
    assert metadata["reported_uncertainty"]["model_comparison_allowance"] is None
    challenge = metadata["future_installed_challenge"]
    assert set(challenge["five_decision_layers"].values()) == {"not_run"}
    assert challenge["globality_certificate"] == "not_guaranteed"


def test_checker_is_stdlib_only_and_reports_no_model_run() -> None:
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
    checker_source = CHECKER_PATH.read_text(encoding="utf-8")
    assert "import epcsaft" not in checker_source
    assert "ePC-SAFT/analyses" not in checker_source

    completed = subprocess.run(
        [sys.executable, str(CHECKER_PATH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "source_contract_ready"
    assert report["rows"] == 1
    assert report["model_output"] == "not_run"
    assert report["csv_sha256"] == EXPECTED_CSV_SHA256
    assert report["metadata_sha256"] == EXPECTED_METADATA_SHA256
