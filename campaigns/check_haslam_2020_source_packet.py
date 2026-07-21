"""Validate the frozen Haslam 2020 Table-8 source packet without package imports."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "data" / "hamer-wu-1972-haslam-table8.csv"
TARGETS = ROOT / "data" / "haslam-2020-table8-targets.csv"
LEDGER = ROOT / "data" / "haslam-2020-table8-source-ledger.yaml"
SALTS = ("LiCl", "LiBr", "LiI", "NaCl", "NaBr", "NaI", "KCl", "KBr", "KI")
GRID = (
    0.001,
    0.002,
    0.005,
    0.01,
    0.02,
    0.05,
    0.1,
    0.2,
    0.3,
    0.4,
    0.5,
    0.6,
    0.7,
    0.8,
    0.9,
    1.0,
    1.2,
    1.4,
    1.6,
    1.8,
    2.0,
    2.5,
    3.0,
)
EXPECTED_SOURCE_HASHES = {
    "haslam": "ef1d694c61caa1cc9665a9569223d2a7acf3c9b834feea1de9afd9c08e433044",
    "hamer_pdf": "a20e0029c929b4e1df2cc8cd7aba10ecbbada3dd0f35689a102d16d18fc34ca6",
    "hamer_md": "289c44242c919bc5902dc0eff395c20d29a7285e20c9c8e3432cad48461e2d33",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate() -> dict[str, object]:
    with SOURCE.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    with TARGETS.open(newline="", encoding="utf-8") as stream:
        targets = list(csv.DictReader(stream))
    if len(rows) != 207 or len(targets) != 18:
        raise ValueError("unexpected Haslam source-packet shape")
    required_columns = {
        "row_id",
        "source_pdf_page",
        "phi_table8_binding",
        "gamma_table8_binding",
        "miac_repository_sha256",
        "miac_repository_row_status",
        "osmotic_repository_row_status",
    }
    if not required_columns.issubset(rows[0]):
        raise ValueError("source-to-row provenance columns are incomplete")
    for salt in SALTS:
        selected = [row for row in rows if row["salt"] == salt]
        if tuple(float(row["molality_mol_kg"]) for row in selected) != GRID:
            raise ValueError(f"{salt} does not reproduce the 23-point Hamer-Wu grid")
        if any(not (0.0 < float(row["osmotic_coefficient"]) < 2.0) for row in selected):
            raise ValueError(f"{salt} has invalid osmotic coefficients")
        if any(not (0.0 < float(row["gamma_pm_m"]) < 2.0) for row in selected):
            raise ValueError(f"{salt} has invalid mean ionic activity coefficients")
    kbr = next(
        row for row in rows if row["salt"] == "KBr" and row["molality_mol_kg"] == "1.4"
    )
    if float(kbr["gamma_pm_m"]) != 0.602:
        raise ValueError("KBr 1.4 mol/kg OCR reconciliation changed")
    exact_phi = {
        row["salt"]
        for row in targets
        if row["observable"] == "osmotic_coefficient"
        and row["subset_status"] == "EXACT_HAMER_WU_SUBSET"
    }
    exact_gamma = {
        row["salt"]
        for row in targets
        if row["observable"] == "gamma_pm_m"
        and row["subset_status"] == "EXACT_HAMER_WU_SUBSET"
    }
    if exact_phi != {"LiBr", "LiI", "NaI", "KI"}:
        raise ValueError("exact Phi subset classification changed")
    if exact_gamma != {"LiCl", "LiBr", "LiI", "NaBr", "NaI", "KCl", "KI"}:
        raise ValueError("exact gamma subset classification changed")
    matched = [
        row
        for row in rows
        if row["miac_repository_row_status"] == "VERIFIED_VALUE_MATCH"
    ]
    absent = [row for row in rows if row["miac_repository_row_status"] == "ROW_ABSENT"]
    if len(matched) != 199 or len(absent) != 8:
        raise ValueError("nine-file MIAC reconciliation changed")
    if {row["salt"] for row in absent} != {"NaBr"}:
        raise ValueError("unexpected MIAC repository gaps")
    oracle = next(row for row in rows if row["row_id"] == "HW1972-T10-LiBr-m0.001")
    if (
        oracle["source_pdf_page"] != "19"
        or oracle["osmotic_coefficient"] != "0.989"
        or oracle["phi_table8_binding"] != "DIRECT_HAMER_WU_EXACT_HASLAM_SUBSET"
    ):
        raise ValueError("exact LiBr Phi oracle changed")
    ledger = LEDGER.read_text(encoding="utf-8")
    for value in EXPECTED_SOURCE_HASHES.values():
        if value not in ledger:
            raise ValueError(f"source hash absent from ledger: {value}")
    for token in (
        "0.101",
        "method_assumption",
        "No row is truncated",
        "unavailable_papers",
        "equation 3.5",
        "reference: 185",
    ):
        if token not in ledger:
            raise ValueError(f"source-ledger contract missing: {token}")
    return {
        "status": "source_packet_ready_partial_coverage",
        "rows": len(rows),
        "targets": len(targets),
        "source_csv_sha256": sha256(SOURCE),
        "target_ledger_sha256": sha256(TARGETS),
        "ledger_sha256": sha256(LEDGER),
        "exact_phi_rows": 4 * 23,
        "exact_gamma_rows": 7 * 23,
    }


if __name__ == "__main__":
    print(validate())
