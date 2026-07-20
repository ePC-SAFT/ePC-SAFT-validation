"""Validate the source-only Khudaida 2026 HELD2 tracer contract."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "khudaida-2026-held2-tracer.csv"
DEFAULT_METADATA = ROOT / "data" / "khudaida-2026-held2-tracer.yaml"

EXPECTED_COLUMNS = [
    "case_id",
    "role",
    "source_table",
    "source_figure",
    "temperature_K",
    "pressure_Pa",
    "salt_feed_mass_fraction",
    "tie_line",
    "organic_x_water_formula",
    "organic_x_ethanol_formula",
    "organic_x_isobutanol_formula",
    "organic_x_nacl_formula",
    "aqueous_x_water_formula",
    "aqueous_x_ethanol_formula",
    "aqueous_x_isobutanol_formula",
    "aqueous_x_nacl_formula",
    "organic_x_water_salt_free",
    "organic_x_ethanol_salt_free",
    "organic_x_isobutanol_salt_free",
    "aqueous_x_water_salt_free",
    "aqueous_x_ethanol_salt_free",
    "aqueous_x_isobutanol_salt_free",
    "midpoint_n_water",
    "midpoint_n_ethanol",
    "midpoint_n_isobutanol",
    "midpoint_n_nacl_formula",
    "explicit_n_na",
    "explicit_n_cl",
    "temperature_standard_uncertainty_K",
    "pressure_standard_uncertainty_Pa",
    "water_x_standard_uncertainty",
    "ethanol_x_standard_uncertainty",
    "isobutanol_x_standard_uncertainty",
    "nacl_x_standard_uncertainty",
]
EXPECTED_SOURCE_HASHES = {
    "main_markdown": "fc8feed1b91c17b0e03610dab2c86d989dccce342a72bf5f38285c3a4466954e",
    "supporting_information_markdown": "71a6aec2ba260196b0e15a2c09e8f69b7e44dc0c131def96eecfc10fdeb337be",
}
EXPECTED_LAB_TABLE_HASHES = {
    "tables_3_4_experimental_tielines_csv": "8eb728633eed0a9ab6afb477e834e801c68ff86eb4c656cc46a8eb09c7166a1c",
    "table_5_pure_component_parameters_csv": "2a1dea257bc42bb11934a49e88ef8359b8472996fd926611eb2c0d2fe78cfda1",
    "table_6_relative_dielectric_constants_csv": "708573ca37adef83cd9d3be3b286eaacf05243dde286b3308abeb05d9afeb4b0",
    "table_7_epcsaft_kij_csv": "4dda028bac9903c4722a628127be9470e644ccb52b7b7c9ae37386b61e51fb1b",
}
EXPECTED_MIGRATION_BINDING = {
    "decision": "D-024",
    "gate_commit": "97c3467232c5fbab1ce67ebd2353801ae13d17e0",
    "gate_tree": "17b72e724a2a70e4f7c5d9b8aa4d8558ef2992df",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decimal_values(row: dict[str, str], names: list[str]) -> list[Decimal]:
    return [Decimal(row[name]) for name in names]


def check(csv_path: Path, metadata_path: Path) -> dict[str, object]:
    with csv_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(f"unexpected CSV columns: {reader.fieldnames}")
        rows = list(reader)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    if len(rows) != 1:
        raise ValueError(f"expected one frozen tracer row, found {len(rows)}")
    row = rows[0]
    if metadata["migration_binding"] != EXPECTED_MIGRATION_BINDING:
        raise ValueError("unexpected D-024 migration binding")
    if metadata["citation"]["doi"] != "10.1021/acs.jced.5c00780":
        raise ValueError("unexpected source DOI")
    source_hashes = {
        name: source["sha256"] for name, source in metadata["primary_sources"].items()
    }
    if source_hashes != EXPECTED_SOURCE_HASHES:
        raise ValueError("primary Markdown source hashes changed")
    lab_hashes = metadata["lab_distillation"]["retained_table_hashes"]
    if lab_hashes != EXPECTED_LAB_TABLE_HASHES:
        raise ValueError("distilled lab table hashes changed")
    csv_hash = sha256(csv_path)
    if metadata["retained_files"]["tracer_csv"]["sha256"] != csv_hash:
        raise ValueError("retained tracer CSV hash does not match metadata")

    if (
        row["case_id"] != "khudaida2026-figure2-table3-tl4"
        or row["source_table"] != "Table 3"
        or row["source_figure"] != "Figure 2"
        or row["tie_line"] != "4"
    ):
        raise ValueError("unexpected first-tracer identity")
    if (
        Decimal(row["temperature_K"]) != Decimal("293.15")
        or Decimal(row["pressure_Pa"]) != Decimal("100000")
        or Decimal(row["salt_feed_mass_fraction"]) != Decimal("0.05")
    ):
        raise ValueError("unexpected first-tracer state")

    formula_names = ["water", "ethanol", "isobutanol", "nacl"]
    organic = decimal_values(row, [f"organic_x_{name}_formula" for name in formula_names])
    aqueous = decimal_values(row, [f"aqueous_x_{name}_formula" for name in formula_names])
    if organic != [Decimal(value) for value in ("0.3695", "0.0927", "0.5366", "0.0012")]:
        raise ValueError("organic Table 3 endpoint changed")
    if aqueous != [Decimal(value) for value in ("0.9486", "0.0092", "0.0037", "0.0385")]:
        raise ValueError("aqueous Table 3 endpoint changed")
    if sum(organic) != Decimal(1) or sum(aqueous) != Decimal(1):
        raise ValueError("formula-mole endpoint does not normalize")

    midpoint = decimal_values(
        row,
        [
            "midpoint_n_water",
            "midpoint_n_ethanol",
            "midpoint_n_isobutanol",
            "midpoint_n_nacl_formula",
        ],
    )
    if midpoint != [(left + right) / 2 for left, right in zip(organic, aqueous, strict=True)]:
        raise ValueError("formula-mole midpoint is not the exact endpoint mean")
    explicit = midpoint[:3] + decimal_values(row, ["explicit_n_na", "explicit_n_cl"])
    if explicit != [Decimal(value) for value in ("0.65905", "0.05095", "0.27015", "0.01985", "0.01985")]:
        raise ValueError("explicit dissociated species vector changed")
    if explicit[3] != explicit[4] or sum(explicit) != Decimal("1.01985"):
        raise ValueError("explicit vector does not preserve 1:1 NaCl dissociation")

    neutral_names = ["water", "ethanol", "isobutanol"]
    for phase, formula in (("organic", organic), ("aqueous", aqueous)):
        projected = decimal_values(
            row, [f"{phase}_x_{name}_salt_free" for name in neutral_names]
        )
        expected = [value / (Decimal(1) - formula[3]) for value in formula[:3]]
        if projected != expected or sum(projected) != Decimal(1):
            raise ValueError(f"{phase} Figure 2 salt-free projection changed")

    uncertainty = metadata["reported_uncertainty"]
    if uncertainty["model_comparison_allowance"] is not None:
        raise ValueError("source packet must not invent a model acceptance cutoff")
    expected_uncertainties = [
        Decimal("0.02"),
        Decimal("1000"),
        Decimal("0.0016"),
        Decimal("0.0007"),
        Decimal("0.0015"),
        Decimal("0.0002"),
    ]
    observed_uncertainties = decimal_values(
        row,
        [
            "temperature_standard_uncertainty_K",
            "pressure_standard_uncertainty_Pa",
            "water_x_standard_uncertainty",
            "ethanol_x_standard_uncertainty",
            "isobutanol_x_standard_uncertainty",
            "nacl_x_standard_uncertainty",
        ],
    )
    if observed_uncertainties != expected_uncertainties:
        raise ValueError("reported Table 3 uncertainties changed")

    model_bundle = metadata["published_model_bundle"]
    kij = model_bundle["table_7_kij"]
    if len(kij) != 10:
        raise ValueError("expected all ten printed Table 7 interaction cells")
    explicit_zeros = [
        entry
        for entry in kij
        if entry["provenance"] == "explicit-published-zero-missing-upstream-reference"
    ]
    if {(tuple(entry["pair"]), entry["value"], entry["reference"]) for entry in explicit_zeros} != {
        (("isobutanol", "Na+"), "0", None),
        (("isobutanol", "Cl-"), "0", None),
    }:
        raise ValueError("Table 7 explicit-zero provenance changed")
    requirements = " ".join(model_bundle["completeness_requirements"])
    for token in ("cross-association", "l_ij", "k_hb_ij", "Figiel", "No parameter tuning"):
        if token not in requirements:
            raise ValueError(f"model-bundle completeness requirement missing: {token}")

    challenge = metadata["future_installed_challenge"]
    if set(challenge["five_decision_layers"]) != {
        "artifact_input",
        "solver",
        "numerical",
        "physical",
        "predictive",
    } or set(challenge["five_decision_layers"].values()) != {"not_run"}:
        raise ValueError("five pre-model decision layers changed")
    if challenge["globality_certificate"] != "not_guaranteed":
        raise ValueError("finite HELD2 globality must remain not guaranteed")
    if set(challenge["terminal_classifications"]) != {
        "PARAMETER_CONTRACT_INCOMPLETE",
        "SOLVER_LIMIT",
        "MODEL_TOPOLOGY_MISS",
        "PREDICTIVE_MISS",
        "PREDICTIVE_PASS",
        "NOT_EVALUATED",
    }:
        raise ValueError("truthful terminal classifications changed")
    if challenge["status"] != "not_run_pending_migration_bound_provider_and_equilibrium_wheels":
        raise ValueError("source-only packet must remain not run")

    return {
        "status": "source_contract_ready",
        "case_id": row["case_id"],
        "rows": len(rows),
        "csv_sha256": csv_hash,
        "metadata_sha256": sha256(metadata_path),
        "primary_source_sha256": source_hashes,
        "lab_table_sha256": lab_hashes,
        "model_output": "not_run",
        "globality_certificate": challenge["globality_certificate"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the frozen source-only Khudaida 2026 HELD2 tracer contract."
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    args = parser.parse_args()
    print(json.dumps(check(args.csv, args.metadata), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
