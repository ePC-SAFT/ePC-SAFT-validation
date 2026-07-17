from __future__ import annotations

import ast
import csv
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "may-2015-methane-ethane-vle.csv"
METADATA_PATH = ROOT / "data" / "may-2015-methane-ethane-vle.yaml"
CHECKER_PATH = ROOT / "campaigns" / "check_may_2015_source.py"

EXPECTED_COLUMNS = [
    "row_id",
    "pathway",
    "T_K",
    "P_Pa",
    "x_methane",
    "x_ethane",
    "u_x_methane",
    "uc_x_methane",
    "y_methane",
    "y_ethane",
    "u_y_methane",
    "uc_y_methane",
    "temperature_standard_uncertainty_K",
    "pressure_standard_uncertainty_Pa",
    "x_comparison_allowance",
    "y_comparison_allowance",
]
EXPECTED_CSV_SHA256 = "5cd1e74925a3c6504f5106dcf911f2cae2d6e99a5133fccc20454d8991bdbc7f"
EXPECTED_METADATA_SHA256 = "d43433e93b354e01f96d330c760818a24b775026461ce795e45774cfb11ac94e"
EXPECTED_SOURCE_HASHES = {
    "nist_thermoml_json": "77630e90db70bb6aabfdfa520f61f14cee5076ece0265754140a25f771659662",
    "nist_thermoml_xml": "311e35b53e27bc050e17c4146a466e087c24c7a15624c29ababc4b7897d7871a",
    "publisher_article_pdf": "53fd1bdd55dc6807ec76cf88626438d8dfceb3ec09149d4405ea36cfbe6b842a",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_contract() -> tuple[list[dict[str, str]], dict[str, object]]:
    missing = [path for path in (CSV_PATH, METADATA_PATH, CHECKER_PATH) if not path.is_file()]
    assert not missing, f"audited source-contract files do not exist: {missing}"
    with CSV_PATH.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == EXPECTED_COLUMNS
        rows = list(reader)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return rows, metadata


def test_retained_files_and_source_downloads_are_hash_bound() -> None:
    rows, metadata = load_contract()

    assert len(rows) == 17
    assert sha256(CSV_PATH) == EXPECTED_CSV_SHA256
    assert sha256(METADATA_PATH) == EXPECTED_METADATA_SHA256
    assert metadata["citation"]["doi"] == "10.1021/acs.jced.5b00610"
    assert metadata["citation"]["table_locator"] == "Table 5, page 3612 (PDF page 7)"
    assert {
        name: source["sha256"] for name, source in metadata["sources"].items()
    } == EXPECTED_SOURCE_HASHES
    assert metadata["retained_files"]["csv"]["sha256"] == EXPECTED_CSV_SHA256


def test_rows_preserve_binary_vle_and_uncertainty_contract() -> None:
    rows, metadata = load_contract()

    assert [row["row_id"] for row in rows] == [
        f"may2015-ch4-c2h6-{index:03d}" for index in range(1, 18)
    ]
    assert len({row["row_id"] for row in rows}) == len(rows)
    pathway_counts = Counter(row["pathway"] for row in rows)
    assert pathway_counts == {"isochoric": 5, "isothermal": 12}
    isothermal_temperatures = [
        float(row["T_K"]) for row in rows if row["pathway"] == "isothermal"
    ]
    assert len(isothermal_temperatures) >= 3
    assert max(isothermal_temperatures) - min(isothermal_temperatures) <= 0.02

    multiplier = metadata["tolerance_contract"]["payload"]["combined_standard_uncertainty_multiplier"]
    assert multiplier == 3.0
    assert metadata["tolerance_contract"]["payload"]["model_accuracy_floor"] is None
    for row in rows:
        values = {name: float(row[name]) for name in EXPECTED_COLUMNS[2:]}
        assert all(math.isfinite(value) for value in values.values())
        assert values["T_K"] > 0.0
        assert values["P_Pa"] > 0.0
        assert 0.0 < values["x_methane"] < 1.0
        assert 0.0 < values["y_methane"] < 1.0
        assert math.isclose(values["x_methane"] + values["x_ethane"], 1.0, abs_tol=1e-12)
        assert math.isclose(values["y_methane"] + values["y_ethane"], 1.0, abs_tol=1e-12)
        assert all(
            values[name] >= 0.0
            for name in (
                "u_x_methane",
                "uc_x_methane",
                "u_y_methane",
                "uc_y_methane",
                "temperature_standard_uncertainty_K",
                "pressure_standard_uncertainty_Pa",
            )
        )
        assert math.isclose(
            values["x_comparison_allowance"],
            multiplier * values["uc_x_methane"],
            abs_tol=1e-12,
        )
        assert math.isclose(
            values["y_comparison_allowance"],
            multiplier * values["uc_y_methane"],
            abs_tol=1e-12,
        )


def test_checker_is_stdlib_only_and_accepts_the_frozen_contract() -> None:
    load_contract()
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
    assert report["rows"] == 17
    assert report["csv_sha256"] == EXPECTED_CSV_SHA256
    assert report["metadata_sha256"] == EXPECTED_METADATA_SHA256
