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
CSV_PATH = ROOT / "data" / "ascani-2022-case-study-2-tracer.csv"
METADATA_PATH = ROOT / "data" / "ascani-2022-case-study-2-tracer.yaml"
CHECKER_PATH = ROOT / "campaigns" / "check_ascani_2022_source_contract.py"

EXPECTED_CSV_SHA256 = "388f62d02f995fc89fb099bb625a907713eebe70f19ea631688cc8e4169acecd"
EXPECTED_METADATA_SHA256 = (
    "9ac51dae619c4fd5ba4afbf01e4930083e4b3da39a13f332890da704fa18c4c6"
)
EXPECTED_SOURCE_HASHES = {
    "main_markdown": "c0b73c10aa1ce9830e29f34aa3c1d1af4b889971959c3245a2deb7efdd979cd6",
    "supporting_information_markdown": "a6a61508cbaae805f2e360686785318953747a66c27d9102936e77be7f472c03",
}
EXPECTED_PARAMETER_SOURCE_PDFS = {
    "ascani_held_2021": "9ab259a8dfb27a052fcf49782e6ab75132140d94c5f8f695215a2703f1d010ab",
    "nann_held_sadowski_2013": "aeb3562f76ac9b3a8ee11779696933aead55a5bd0e6e6bb67bd82f38bf691313",
    "held_et_al_2014": "dea9aa05e2ee8eb1c675873fa9d8737943312484874d844f01b45613da261acf",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> tuple[dict[str, str], dict[str, object]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return rows[0], json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def test_source_identity_archive_hashes_and_migration_binding_are_frozen() -> None:
    _, metadata = load()

    assert sha256(CSV_PATH) == EXPECTED_CSV_SHA256
    assert sha256(METADATA_PATH) == EXPECTED_METADATA_SHA256
    assert metadata["migration_binding"] == {
        "decision": "D-024",
        "gate_commit": "4527864ffcd37f5e9a524500dfd99d5a34c85672",
        "gate_tree": "6a4f9711787c333c146566be8947df2c60f1fc68",
    }
    assert metadata["d026_selection_binding"] == {
        "decision": "D-026",
        "gate_commit": "3a4ef0a0c6b98c43405d3cafc1ac4f5f87afa68d",
        "gate_tree": "9307c3f79581b6e0479d4ac2468932b2a68e5f5b",
        "selection": "ascani_case_study_2_source_complete_pending_distinct_provider_bundle",
    }
    assert {
        name: source["sha256"] for name, source in metadata["primary_sources"].items()
    } == EXPECTED_SOURCE_HASHES
    assert {
        name: source["pdf_sha256"]
        for name, source in metadata["bound_parameter_sources"].items()
    } == EXPECTED_PARAMETER_SOURCE_PDFS
    assert (
        metadata["bound_parameter_sources"]["ascani_held_2021"][
            "permanent_lab_pdf_sha256"
        ]
        == "b26bb94b84e676c15a5ff40f878f0e0d1488c6994990c3c3e7d968630f2fa464"
    )
    archive = metadata["lab_archive_provenance"]
    assert archive["source_and_model_input_hashes"] == {
        "case2_paper_phase_compositions_csv": "eb139d8cdc90f3e21a612dc4125e481c2bb200d1f922b1167279de0296143344",
        "paper_table5_fugacity_csv": "591892ef0c01a13060a16edbce08466b65ba31d2be27174815e423cc19650d88",
        "pure_component_parameters_csv": "13928e22d419413076ac21586c230416bab7945f6676bef53d516fc915a81146",
        "binary_interaction_source_manifest_csv": "d55c1fa59c961d8727808491ad89915968e5949ae6401efe76bbd00142166dde",
        "k_ij_csv": "4d3e587faa598acbf058b6162d86b7ec541b376c1dac84169b96f39e57c2e690",
        "l_ij_csv": "97a69ff9c60c77329775ed4f760bb3f3ea015929510f86f434e397210f616920",
        "k_hb_ij_csv": "6f956c05e6fee9ec151c7e097dd98557a3d1a6a31a8f8adb07a7b0d45f3d513c",
    }
    assert archive["permitted_historical_output_hashes"] == {
        "summary_json": "d1178d8d02b3f8d6f83929d7ca3818e58b965c52430d0d93ab92e545632891a1",
        "phase_split_csv": "a3ab6456bceca8fd8fda2343cbc9e8e4efae5d5533a6df67a24f9347d9aac10f",
        "stability_summary_csv": "2275895adfb1a80b5cb3b5fd13171667d1ca4b1fa4d751fc5eebac3de977795b",
    }


def test_tracer_preserves_formula_values_and_explicit_species_derivations() -> None:
    row, metadata = load()

    assert [
        Decimal(row[f"feed_w_{name}_formula"])
        for name in ("water", "butanol", "nacl", "kcl")
    ] == [
        Decimal("0.8094"),
        Decimal("0.1728"),
        Decimal("0.0054"),
        Decimal("0.0124"),
    ]
    explicit_feed = [
        Decimal(row[f"feed_x_{name}_explicit"])
        for name in ("water", "butanol", "na", "k", "cl")
    ]
    assert explicit_feed == [
        Decimal("0.9403742328474496"),
        Decimal("0.04879524350242891"),
        Decimal("0.0019339333595015447"),
        Decimal("0.0034813284655591703"),
        Decimal("0.005415261825060715"),
    ]
    assert abs(sum(explicit_feed) - Decimal(1)) <= Decimal("1e-15")
    assert explicit_feed[2] + explicit_feed[3] == explicit_feed[4]

    for phase in ("organic", "aqueous"):
        explicit = [
            Decimal(row[f"{phase}_x_{name}_explicit"])
            for name in ("water", "butanol", "na", "k", "cl")
        ]
        assert abs(sum(explicit) - Decimal(1)) <= Decimal("1e-27")
        assert abs(explicit[2] + explicit[3] - explicit[4]) <= Decimal("1e-27")

    assert [
        Decimal(row[name])
        for name in (
            "ln_f_water_bar",
            "ln_f_butanol_bar",
            "ln_f_kcl_pair_bar",
            "ln_f_nacl_pair_bar",
        )
    ] == [
        Decimal("-3.521"),
        Decimal("-5.088"),
        Decimal("-206.733"),
        Decimal("-224.891"),
    ]
    assert metadata["source_classification"]["model_comparison_allowance"] is None
    assert (
        metadata["tracer_contract"]["paper_formula_phase_compositions"][
            "classification"
        ]
        == "direct paper-reported ePC-SAFT advanced calculation output, not direct experimental data"
    )
    assert len(metadata["missing_upstream_provenance"]) == 3

    screen = metadata["d026_source_completeness_screen"]
    assert (
        screen["case_source_status"]
        == "SOURCE_COMPLETE_FOR_BOUNDED_ASCANI_EPCSAFT_ADVANCED_MODEL"
    )
    assert screen["unresolved_ascani_source_records"] == []
    assert screen["provider_status"] == "PROVIDER_NOT_YET_CAPABLE"
    assert screen["hybrid_figiel_status"] == (
        "NOT_SOURCE_COMPLETE_FOR_HYBRID_FIGIEL_SSM_DS_1_BUTANOL"
    )
    assert "NOT_APPLICABLE" in " ".join(
        screen["source_backed_records"]["pure_and_association"]
    )
    assert (
        "Ascani 2022 SI Eq. S4"
        in screen["water_butanol_l_ij_sign_convention"]["target_authority"]
    )
    assert screen["model_output"] == "not_run"


def test_checker_is_stdlib_only_and_negative_space_stays_explicit() -> None:
    _, metadata = load()
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
    assert "ePC-SAFT/analyses" not in checker_source

    archive = metadata["lab_archive_provenance"]
    assert (
        archive["authority"]
        == "checker data only; no runtime, algorithm, numerical, solver, or acceptance authority"
    )
    negative_space = " ".join(archive["negative_space"])
    for phrase in (
        "Do not reuse, port, restore, call, imitate",
        "archived seeds, controller, API, solver behavior, tolerances",
        "cannot validate or determine the new algorithm",
    ):
        assert phrase in negative_space
    assert (
        archive["historical_witnesses"]["strong_negative_witness_min_tpd"]
        == "-0.09607343786579076"
    )

    support = metadata["supporting_numerical_literature"]
    assert (
        support["classification"]
        == "general numerical-conditioning support only; not electrolyte-LLE or HELD2 evidence"
    )
    assert support["line_ranges"] == {
        "broad_concentration_scales_conditioning": "23-27",
        "exact_derivatives_and_automatic_differentiation": "121-132",
        "dimensionless_objective": "134-138",
        "nonnegative_variables_phase_sums_material_balances": "141-187",
        "inventory_normalization_and_review_checks": "301-307",
    }
    for excluded in (
        "settings or tolerances",
        "multiplier unscaling",
        "start policy",
        "scientific-gate relaxation",
    ):
        assert excluded in support["negative_space"]

    prerequisite = metadata["published_model_bundle_prerequisites"]
    assert prerequisite["status"] == (
        "source_complete_for_ascani_epcsaft_advanced_not_implemented_not_run"
    )
    assert "current Khudaida" in prerequisite["bundle_identity"]
    assert "insufficient" in prerequisite["bundle_identity"]
    challenge = metadata["future_installed_challenge"]
    assert challenge["algorithm_source"] == "current Perdomo HELD2"
    assert set(challenge["five_decision_layers"].values()) == {"not_run"}
    assert challenge["globality_certificate"] == "not_guaranteed"

    completed = subprocess.run(
        [sys.executable, str(CHECKER_PATH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert (
        report["status"] == "source_complete_for_bounded_ascani_epcsaft_advanced_model"
    )
    assert report["rows"] == 1
    assert report["model_output"] == "not_run"
    assert report["d026_unresolved_ascani_source_records"] == 0
    assert report["provider_status"] == "PROVIDER_NOT_YET_CAPABLE"
    assert report["csv_sha256"] == EXPECTED_CSV_SHA256
    assert report["metadata_sha256"] == EXPECTED_METADATA_SHA256
