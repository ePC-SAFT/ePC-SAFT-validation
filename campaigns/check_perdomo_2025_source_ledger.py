"""Validate the source-only Perdomo et al. 2025 HELD2 case ledger."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "data" / "perdomo-2025-held2-case-ledger.csv"
DEFAULT_SAMPLES = ROOT / "data" / "perdomo-2025-held2-published-samples.csv"
DEFAULT_METADATA = ROOT / "data" / "perdomo-2025-held2-source-ledger.yaml"

EXPECTED_CASE_COLUMNS = [
    "case_id",
    "section",
    "mixture",
    "phase_behavior",
    "published_flash_count",
    "temperature_contract",
    "pressure_contract",
    "feed_contract",
    "species_order",
    "charges",
    "eos_model",
    "parameter_source_availability",
    "reported_phase_count",
    "reported_composition_locator",
    "reproducibility_classification",
    "recommendation_role",
]
EXPECTED_SAMPLE_COLUMNS = [
    "sample_id",
    "case_id",
    "source_table",
    "source_lines",
    "input_1_name",
    "input_1_value",
    "input_1_unit",
    "input_2_name",
    "input_2_value",
    "input_2_unit",
    "temperature_K",
    "pressure_kPa",
    "reported_phase_count",
    "species_order",
    "phase_1_type",
    "phase_1_x",
    "phase_1_eta",
    "phase_1_volume_m3_mol",
    "phase_2_type",
    "phase_2_x",
    "phase_2_eta",
    "phase_2_volume_m3_mol",
    "iterations",
    "cpu_s",
    "source_anomaly",
]
EXPECTED_SOURCE_HASHES = {
    "zotero_markdown": "a55846342ac6a73379b2267c24d6e9bf792637aea1d66bd26b50e0230429b727",
    "permanent_lab_markdown": "522cba2efb44c6404b3b8b75eefb90c50a84cc4110333f30aa1f0eb1a21380d5",
    "article_pdf_visual_audit": "8be02605fc0e839c368362a80837ae2d4f029f97ba7ba6dc60b486548a790111",
    "official_supporting_workbook": "c659847256044fb783c3fe090454103e109cd13cb5696bb715910428f9935834",
}
EXPECTED_CASE_CLASSES = Counter(
    {
        "cross-eos-epcsaft-challenge-only": 8,
        "algorithmic-manufactured-only": 1,
    }
)
EXPECTED_TABLE_COUNTS = Counter(
    {"Table 3": 3, "Table 4": 3, "Table 5": 3, "Table 6": 6, "Table 7": 4, "Table 8": 7}
)
CLOSEST_CASE = "perdomo2025-licl-water-butanol-lle"
CLOSEST_SAMPLE = "table5-licl-4.58molal"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path, columns: list[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != columns:
            raise ValueError(f"unexpected columns in {path}: {reader.fieldnames}")
        return list(reader)


def decimals(value: str) -> list[Decimal]:
    return [Decimal(item) for item in value.split("|")]


def check(
    cases_path: Path,
    samples_path: Path,
    metadata_path: Path,
    verify_local_sources: bool = False,
) -> dict[str, object]:
    cases = read_csv(cases_path, EXPECTED_CASE_COLUMNS)
    samples = read_csv(samples_path, EXPECTED_SAMPLE_COLUMNS)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    if len(cases) != 9 or len(samples) != 26:
        raise ValueError(
            f"expected 9 cases and 26 samples, found {len(cases)} and {len(samples)}"
        )
    if len({row["case_id"] for row in cases}) != 9:
        raise ValueError("case identifiers are not unique")
    if len({row["sample_id"] for row in samples}) != 26:
        raise ValueError("sample identifiers are not unique")
    case_by_id = {row["case_id"]: row for row in cases}
    if any(row["case_id"] not in case_by_id for row in samples):
        raise ValueError("sample references an unknown case")

    if sum(int(row["published_flash_count"]) for row in cases) != 122917:
        raise ValueError("published Table 1 flash total changed")
    case_classes = Counter(row["reproducibility_classification"] for row in cases)
    if case_classes != EXPECTED_CASE_CLASSES:
        raise ValueError(f"case classifications changed: {case_classes}")
    if Counter(row["source_table"] for row in samples) != EXPECTED_TABLE_COUNTS:
        raise ValueError("published sample table counts changed")
    for row in cases:
        if row["eos_model"] not in {
            "SAFT-gamma-Mie GC electrolyte",
            "SAFT-gamma-Mie GC neutral HELD",
        }:
            raise ValueError(f"unexpected EOS label in {row['case_id']}")
        if int(row["reported_phase_count"]) != 2:
            raise ValueError(f"unexpected reported phase count in {row['case_id']}")

    anomaly_ids: list[str] = []
    for row in samples:
        case = case_by_id[row["case_id"]]
        if row["species_order"] != case["species_order"]:
            raise ValueError(f"species order drift in {row['sample_id']}")
        charges = decimals(case["charges"])
        if int(row["reported_phase_count"]) != 2:
            raise ValueError(f"unexpected phase count in {row['sample_id']}")
        for phase in ("phase_1_x", "phase_2_x"):
            composition = decimals(row[phase])
            if len(composition) != len(charges):
                raise ValueError(
                    f"composition length drift in {row['sample_id']} {phase}"
                )
            normalization_error = abs(sum(composition) - Decimal(1))
            charge_error = abs(
                sum(x * z for x, z in zip(composition, charges, strict=True))
            )
            if row["source_anomaly"]:
                anomaly_ids.append(row["sample_id"])
            if row["sample_id"] == "table8-wap0.0460" and phase == "phase_1_x":
                continue
            if normalization_error > Decimal("3e-5"):
                raise ValueError(
                    f"printed normalization exceeds audit allowance in {row['sample_id']}"
                )
            if charge_error > Decimal("1e-5"):
                raise ValueError(
                    f"printed electroneutrality exceeds audit allowance in {row['sample_id']}"
                )
    if sorted(set(anomaly_ids)) != ["table3-kcl-0.8molal", "table8-wap0.0460"]:
        raise ValueError(f"unexpected source anomaly set: {sorted(set(anomaly_ids))}")

    selected_case = case_by_id[CLOSEST_CASE]
    if (
        selected_case["recommendation_role"]
        != "closest-perdomo-candidate-blocked-source-records"
    ):
        raise ValueError("closest-case role changed")
    selected_sample = next(row for row in samples if row["sample_id"] == CLOSEST_SAMPLE)
    organic = decimals(selected_sample["phase_1_x"])
    aqueous = decimals(selected_sample["phase_2_x"])
    midpoint = [
        (left + right) / 2 for left, right in zip(organic, aqueous, strict=True)
    ]
    recommendation = metadata["recommended_first_tracer"]
    if midpoint != [
        Decimal(value) for value in recommendation["raw_equal_phase_midpoint"]
    ]:
        raise ValueError("recommended midpoint is not the exact endpoint mean")
    midpoint_sum = sum(midpoint)
    if midpoint_sum != Decimal(recommendation["raw_midpoint_sum"]):
        raise ValueError("recommended midpoint sum changed")
    normalized = [value / midpoint_sum for value in midpoint]
    expected_normalized = [
        Decimal(value) for value in recommendation["normalized_equal_phase_feed"]
    ]
    if any(
        abs(left - right) > Decimal("1e-28")
        for left, right in zip(normalized, expected_normalized, strict=True)
    ):
        raise ValueError("normalized recommended feed changed")
    if normalized[0] != normalized[1] or sum(normalized) != Decimal(1):
        raise ValueError("recommended feed is not normalized and charge balanced")

    retained = metadata["retained_files"]
    observed_hashes = {
        "case_ledger_csv": sha256(cases_path),
        "published_samples_csv": sha256(samples_path),
    }
    for name, observed in observed_hashes.items():
        if retained[name]["sha256"] != observed:
            raise ValueError(f"retained file hash mismatch: {name}")
    source_hashes = {
        name: source["sha256"] for name, source in metadata["bound_sources"].items()
    }
    if source_hashes != EXPECTED_SOURCE_HASHES:
        raise ValueError("bound source identities changed")
    if metadata["classification_contract"]["ledger_counts"] != {
        "fully-reproducible": 0,
        "blocked-missing-saft-gamma-mie-parameters-or-proprietary-inputs": 0,
        "algorithmic-manufactured-only": 1,
        "cross-eos-epcsaft-challenge-only": 8,
    }:
        raise ValueError("metadata classification counts changed")
    if recommendation["status"] != "not_selected_source_incomplete":
        raise ValueError("source-incomplete candidate status changed")
    if recommendation["source_completeness"] != "blocked_missing_epcsaft_records":
        raise ValueError("closest candidate source-completeness status changed")
    if set(recommendation["future_decisions"].values()) != {"not_run"}:
        raise ValueError("future model decisions were populated")
    if recommendation["globality_certificate"] != "not_guaranteed":
        raise ValueError("globality boundary changed")

    screen = metadata["d026_epcsaft_two_liquid_screen"]
    if screen["migration_binding"] != {
        "decision": "D-026",
        "gate_commit": "3a4ef0a0c6b98c43405d3cafc1ac4f5f87afa68d",
        "gate_tree": "9307c3f79581b6e0479d4ac2468932b2a68e5f5b",
    }:
        raise ValueError("unexpected D-026 Migration binding")
    if screen["decision"] != "NO_SOURCE_COMPLETE_PERDOMO_TWO_LIQUID_CASE":
        raise ValueError("D-026 source-screen decision changed")
    if screen["screen_counts"] != {
        "cases_screened": 9,
        "ineligible_not_two_liquid": 5,
        "two_liquid_blocked_source_records": 4,
        "source_complete_two_liquid": 0,
    }:
        raise ValueError("D-026 source-screen counts changed")
    case_screen = screen["case_screen"]
    blocked = [row for row in case_screen if row["outcome"] == "blocked_source_records"]
    if len(blocked) != 4:
        raise ValueError("D-026 blocked LLE case count changed")
    fallback = screen["fallback"]
    if (
        fallback["case_id"] != "ascani2022-case-study-2"
        or fallback["remaining_source_gaps"]
        or fallback["source_status"]
        != "SOURCE_COMPLETE_FOR_BOUNDED_ASCANI_EPCSAFT_ADVANCED_MODEL"
        or fallback["provider_gap"].split(":", 1)[0] != "PROVIDER_NOT_YET_CAPABLE"
    ):
        raise ValueError("D-026 Ascani fallback contract changed")
    ascani_binding = screen["provider_source_snapshot"]["bound_validation_packets"][
        "ascani_case_study_2_source_contract"
    ]
    if sha256(ROOT / ascani_binding["path"]) != ascani_binding["sha256"]:
        raise ValueError("D-026 Ascani source-contract binding changed")

    verified_sources: list[str] = []
    if verify_local_sources:
        for name in ("zotero_markdown", "permanent_lab_markdown"):
            source = metadata["bound_sources"][name]
            path = Path(source["execution_locator"])
            if not path.is_file() or sha256(path) != source["sha256"]:
                raise ValueError(f"local source verification failed: {name}")
            verified_sources.append(name)

    return {
        "status": "no_source_complete_perdomo_two_liquid_case",
        "cases": len(cases),
        "published_samples": len(samples),
        "published_flash_total": 122917,
        "classification_counts": dict(sorted(case_classes.items())),
        "table_counts": dict(sorted(EXPECTED_TABLE_COUNTS.items())),
        "source_anomalies": ["table3-kcl-0.8molal", "table8-wap0.0460"],
        "closest_case": CLOSEST_CASE,
        "selected_fallback": fallback["case_id"],
        "selected_fallback_source_status": fallback["source_status"],
        "closest_sample": CLOSEST_SAMPLE,
        "selected_case": None,
        "fallback_case": "ascani2022-case-study-2",
        "case_ledger_sha256": observed_hashes["case_ledger_csv"],
        "published_samples_sha256": observed_hashes["published_samples_csv"],
        "metadata_sha256": sha256(metadata_path),
        "local_sources_verified": verified_sources,
        "model_output": "not_run",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--verify-local-sources", action="store_true")
    args = parser.parse_args()
    report = check(args.cases, args.samples, args.metadata, args.verify_local_sources)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
