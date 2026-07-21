"""Validate the canonical partial Haslam/Hamer-Wu osmotic source packet."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "data" / "haslam-2020-osmotic-provider-source-ledger.yaml"
DEFAULT_SOURCE_ROW = ROOT / "data" / "haslam-2020-osmotic-provider-source-row.csv"

EXPECTED_SOURCE_ROW_SHA256 = (
    "fa2e68e8bc1224f2c6d5b80ad79e6643a08b5944276274067084c40aee2b4f45"
)
EXPECTED_COLUMNS = [
    "row_id",
    "salt",
    "solvent",
    "temperature_K",
    "source_pressure_MPa",
    "target_pressure_MPa",
    "molality_mol_kg",
    "nu",
    "phi",
    "quantity",
    "quantity_unit",
    "molality_basis",
    "solvent_activity_reference",
    "solvent_molar_mass_basis",
    "source_doi",
    "source_table",
    "source_pdf_page",
    "source_printed_page",
    "source_row_locator",
    "source_pdf_sha256",
    "extraction_markdown_sha256",
    "source_classification",
    "haslam_exact_selected_subset",
    "haslam_selection_status",
    "provider_catalog_status",
    "claim_role",
    "uncertainty",
]
EXPECTED_MIGRATION_BINDING = {
    "commit": "bcf93699f75278920d094f5dfb4ee0da3b6d83e8",
    "tree": "de17bddbabf2f321696b329cbee961b721a79bdb",
}
EXPECTED_PROVIDER_COVERAGE = {
    "LiCl": (23, "180", ("Li+", "Cl-")),
    "LiBr": (23, "179", ("Li+", "Br-")),
    "NaCl": (40, "181-186", ("Na+", "Cl-")),
    "NaBr": (23, "182,187", ("Na+", "Br-")),
    "KCl": (37, "181,188,189", ("K+", "Cl-")),
    "KBr": (24, "179", ("K+", "Br-")),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_source_row(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(f"unexpected source-row columns: {reader.fieldnames}")
        rows = list(reader)
    if len(rows) != 1:
        raise ValueError(
            f"expected exactly one canonical source row, found {len(rows)}"
        )
    return rows[0]


def check(
    ledger_path: Path,
    source_row_path: Path,
    verify_local_sources: bool = False,
    official_hamer_pdf: Path | None = None,
) -> dict[str, object]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    row = read_source_row(source_row_path)

    if ledger["decision"] != "PARTIAL_SOURCE_COVERAGE":
        raise ValueError("packet decision must remain PARTIAL_SOURCE_COVERAGE")
    if ledger["migration_binding"] != EXPECTED_MIGRATION_BINDING:
        raise ValueError("Migration binding changed")
    if sha256(source_row_path) != EXPECTED_SOURCE_ROW_SHA256:
        raise ValueError("canonical source-row CSV hash changed")
    retained = ledger["retained_files"]["source_row_csv"]
    if retained != {
        "path": "data/haslam-2020-osmotic-provider-source-row.csv",
        "sha256": EXPECTED_SOURCE_ROW_SHA256,
        "rows": 1,
    }:
        raise ValueError("retained source-row contract changed")

    haslam = ledger["sources"]["haslam_2020"]
    hamer = ledger["sources"]["hamer_wu_1972"]
    markdown = ledger["sources"]["hamer_wu_mathpix_markdown"]
    if haslam["doi"] != "10.1021/acs.jced.0c00746":
        raise ValueError("Haslam DOI changed")
    if (
        haslam["pdf_sha256"]
        != "ef1d694c61caa1cc9665a9569223d2a7acf3c9b834feea1de9afd9c08e433044"
    ):
        raise ValueError("Haslam article artifact changed")
    if "printed page 5880, Table 8" not in haslam["table_8_locator"]:
        raise ValueError("Haslam Table 8 locator changed")
    if "printed page 5882" not in haslam["condition_locator"]:
        raise ValueError("Haslam condition locator changed")
    if hamer["doi"] != "10.1063/1.3253108":
        raise ValueError("Hamer-Wu DOI changed")
    if (
        hamer["official_pdf_sha256"]
        != "8399084b29b4db4ce35ab47ed679446dbedb9bf1686f99f43fce7b2073ee4beb"
    ):
        raise ValueError("official Hamer-Wu artifact changed")
    if (
        hamer["zotero_pdf_sha256"]
        != "a20e0029c929b4e1df2cc8cd7aba10ecbbada3dd0f35689a102d16d18fc34ca6"
    ):
        raise ValueError("Zotero Hamer-Wu artifact changed")
    if (
        markdown["sha256"]
        != "289c44242c919bc5902dc0eff395c20d29a7285e20c9c8e3432cad48461e2d33"
    ):
        raise ValueError("Hamer-Wu extraction Markdown changed")
    if (
        markdown["authority"]
        != "extraction-only locator and transcription aid; never source authority"
    ):
        raise ValueError("extraction Markdown gained source authority")

    contract = ledger["thermodynamic_contract"]
    expected_contract = {
        "quantity": "dimensionless practical molal osmotic coefficient",
        "symbol": "Phi",
        "molality_unit": "mol/kg",
        "temperature_K": "298.15",
        "haslam_pressure_MPa": "0.101",
    }
    if any(contract[key] != value for key, value in expected_contract.items()):
        raise ValueError("thermodynamic scalar contract changed")
    for phrase in (
        "formula-unit molality",
        "salt-free solvent",
        "M_solv in kg/mol",
        "pure solvent at the same temperature and pressure",
        "sum of ionic stoichiometric coefficients",
    ):
        if phrase not in " ".join(str(value) for value in contract.values()):
            raise ValueError(f"thermodynamic basis missing: {phrase}")

    expected_row_values = {
        "row_id": "hamer-wu-1972-nacl-phi-m1",
        "salt": "NaCl",
        "solvent": "water",
        "temperature_K": "298.15",
        "source_pressure_MPa": "",
        "target_pressure_MPa": "0.101",
        "molality_mol_kg": "1.000",
        "nu": "2",
        "phi": "0.936",
        "quantity": "practical_molal_osmotic_coefficient",
        "quantity_unit": "dimensionless",
        "source_doi": "10.1063/1.3253108",
        "source_table": "Table 16",
        "source_pdf_page": "22",
        "source_printed_page": "1067",
        "source_pdf_sha256": hamer["official_pdf_sha256"],
        "extraction_markdown_sha256": markdown["sha256"],
        "haslam_exact_selected_subset": "false",
        "provider_catalog_status": "current-provider-catalog-supported",
    }
    if any(row[key] != value for key, value in expected_row_values.items()):
        raise ValueError("canonical NaCl Phi row changed")
    if Decimal(row["phi"]) != Decimal("0.936") or Decimal(
        row["molality_mol_kg"]
    ) != Decimal("1.000"):
        raise ValueError("canonical NaCl numerical oracle changed")
    if "references 181-186" not in row["haslam_selection_status"]:
        raise ValueError("NaCl row was incorrectly promoted into the Haslam subset")
    oracle = ledger["exact_oracle"]
    if oracle["haslam_exact_selected_subset"] is not False:
        raise ValueError("one-row oracle was incorrectly labeled as Haslam-selected")
    if (
        oracle["claim"].split(";")[0]
        != "Exact property-definition and one-row supported-salt numerical oracle only"
    ):
        raise ValueError("one-row claim boundary changed")

    coverage = ledger["provider_six_salt_coverage"]
    if len(coverage) != 6:
        raise ValueError("expected exactly six current Provider salts")
    observed_coverage = {
        entry["salt"]: (
            entry["haslam_table_8_phi_n"],
            entry["haslam_table_8_phi_refs"],
            tuple(entry["ions"]),
        )
        for entry in coverage
    }
    if observed_coverage != EXPECTED_PROVIDER_COVERAGE:
        raise ValueError("six-salt coverage matrix changed")
    if any(
        entry["provider_catalog"] != "supported"
        or entry["exact_haslam_rows_in_packet"] != 0
        or entry["selection_status"] != "unknown-missing-row-selection-manifest"
        for entry in coverage
    ):
        raise ValueError("supported-salt selection status changed")
    iodides = ledger["unsupported_haslam_scope"]["iodides"]
    if {entry["salt"] for entry in iodides} != {"LiI", "NaI", "KI"}:
        raise ValueError("Haslam iodide scope changed")
    if any("unsupported-I-minus-absent" not in entry["status"] for entry in iodides):
        raise ValueError("iodide absence is not explicit")
    selection = ledger["haslam_selection_provenance"]
    if selection["classification"] != "unknown-missing-row-selection-manifest":
        raise ValueError("missing Haslam row selection was inferred")
    if "cannot establish full Haslam Table 8 reproduction" not in selection["effect"]:
        raise ValueError("partial-coverage limitation changed")

    verified_sources: list[str] = []
    if verify_local_sources:
        local_sources = {
            "haslam_pdf": (Path(haslam["pdf_execution_locator"]), haslam["pdf_sha256"]),
            "hamer_zotero_pdf": (
                Path(hamer["zotero_pdf_execution_locator"]),
                hamer["zotero_pdf_sha256"],
            ),
            "hamer_markdown": (Path(markdown["execution_locator"]), markdown["sha256"]),
        }
        for name, (path, expected_hash) in local_sources.items():
            if not path.is_file() or sha256(path) != expected_hash:
                raise ValueError(f"local source verification failed: {name}")
            verified_sources.append(name)
    if official_hamer_pdf is not None:
        if (
            not official_hamer_pdf.is_file()
            or sha256(official_hamer_pdf) != hamer["official_pdf_sha256"]
        ):
            raise ValueError("official Hamer-Wu PDF verification failed")
        verified_sources.append("official_hamer_wu_pdf")

    return {
        "status": "PARTIAL_SOURCE_COVERAGE",
        "source_rows": 1,
        "oracle": {"salt": "NaCl", "molality_mol_kg": "1.000", "phi": "0.936"},
        "haslam_exact_selected_rows": 0,
        "provider_supported_salts": sorted(EXPECTED_PROVIDER_COVERAGE),
        "unsupported_iodides": sorted(entry["salt"] for entry in iodides),
        "haslam_selection_provenance": selection["classification"],
        "source_row_sha256": sha256(source_row_path),
        "ledger_sha256": sha256(ledger_path),
        "verified_sources": verified_sources,
        "model_output": "not_run",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--source-row", type=Path, default=DEFAULT_SOURCE_ROW)
    parser.add_argument("--verify-local-sources", action="store_true")
    parser.add_argument("--official-hamer-pdf", type=Path)
    args = parser.parse_args()
    report = check(
        args.ledger,
        args.source_row,
        verify_local_sources=args.verify_local_sources,
        official_hamer_pdf=args.official_hamer_pdf,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
