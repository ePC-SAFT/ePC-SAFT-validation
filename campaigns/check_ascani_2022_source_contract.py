"""Validate the source-only Ascani 2022 Case Study 2 tracer contract."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "ascani-2022-case-study-2-tracer.csv"
DEFAULT_METADATA = ROOT / "data" / "ascani-2022-case-study-2-tracer.yaml"

EXPECTED_COLUMNS = [
    "case_id",
    "role",
    "temperature_K",
    "pressure_Pa",
    "feed_w_water_formula",
    "feed_w_butanol_formula",
    "feed_w_nacl_formula",
    "feed_w_kcl_formula",
    "feed_x_water_explicit",
    "feed_x_butanol_explicit",
    "feed_x_na_explicit",
    "feed_x_k_explicit",
    "feed_x_cl_explicit",
    "organic_x_water_formula",
    "organic_x_butanol_formula",
    "organic_x_nacl_formula",
    "organic_x_kcl_formula",
    "aqueous_x_water_formula",
    "aqueous_x_butanol_formula",
    "aqueous_x_nacl_formula",
    "aqueous_x_kcl_formula",
    "organic_x_water_explicit",
    "organic_x_butanol_explicit",
    "organic_x_na_explicit",
    "organic_x_k_explicit",
    "organic_x_cl_explicit",
    "aqueous_x_water_explicit",
    "aqueous_x_butanol_explicit",
    "aqueous_x_na_explicit",
    "aqueous_x_k_explicit",
    "aqueous_x_cl_explicit",
    "ln_f_water_bar",
    "ln_f_butanol_bar",
    "ln_f_kcl_pair_bar",
    "ln_f_nacl_pair_bar",
]
EXPECTED_SOURCE_HASHES = {
    "main_markdown": "c0b73c10aa1ce9830e29f34aa3c1d1af4b889971959c3245a2deb7efdd979cd6",
    "supporting_information_markdown": "a6a61508cbaae805f2e360686785318953747a66c27d9102936e77be7f472c03",
}
EXPECTED_MIGRATION_BINDING = {
    "decision": "D-024",
    "gate_commit": "4527864ffcd37f5e9a524500dfd99d5a34c85672",
    "gate_tree": "6a4f9711787c333c146566be8947df2c60f1fc68",
}
DERIVATION_ABS = Decimal("1e-27")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decimals(row: dict[str, str], names: list[str]) -> list[Decimal]:
    return [Decimal(row[name]) for name in names]


def explicit_phase(formula: list[Decimal]) -> list[Decimal]:
    water, butanol, nacl, kcl = formula
    amounts = [water, butanol, nacl, kcl, nacl + kcl]
    total = sum(amounts)
    return [amount / total for amount in amounts]


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
        raise ValueError("unexpected D-024 Migration binding")
    if metadata["citation"]["doi"] != "10.1021/acs.jced.1c00866":
        raise ValueError("unexpected Ascani DOI")
    source_hashes = {
        name: source["sha256"] for name, source in metadata["primary_sources"].items()
    }
    if source_hashes != EXPECTED_SOURCE_HASHES:
        raise ValueError("primary Markdown source hashes changed")
    csv_hash = sha256(csv_path)
    if metadata["retained_files"]["tracer_csv"]["sha256"] != csv_hash:
        raise ValueError("retained tracer CSV hash does not match metadata")

    if (
        row["case_id"] != "ascani2022-case-study-2"
        or row["role"] != "secondary_external_held2_tracer"
    ):
        raise ValueError("unexpected tracer identity")
    if Decimal(row["temperature_K"]) != Decimal("298.15") or Decimal(
        row["pressure_Pa"]
    ) != Decimal("100000"):
        raise ValueError("unexpected tracer state")

    feed_mass = decimals(
        row,
        [
            "feed_w_water_formula",
            "feed_w_butanol_formula",
            "feed_w_nacl_formula",
            "feed_w_kcl_formula",
        ],
    )
    if feed_mass != [
        Decimal(value) for value in ("0.8094", "0.1728", "0.0054", "0.0124")
    ] or sum(feed_mass) != Decimal(1):
        raise ValueError("formula-basis feed changed")
    explicit_feed = decimals(
        row,
        [
            "feed_x_water_explicit",
            "feed_x_butanol_explicit",
            "feed_x_na_explicit",
            "feed_x_k_explicit",
            "feed_x_cl_explicit",
        ],
    )
    if explicit_feed != [
        Decimal("0.9403742328474496"),
        Decimal("0.04879524350242891"),
        Decimal("0.0019339333595015447"),
        Decimal("0.0034813284655591703"),
        Decimal("0.005415261825060715"),
    ]:
        raise ValueError("explicit species feed changed")
    if (
        abs(sum(explicit_feed) - Decimal(1)) > Decimal("1e-15")
        or explicit_feed[2] + explicit_feed[3] != explicit_feed[4]
    ):
        raise ValueError(
            "explicit feed does not preserve normalization and charge stoichiometry"
        )

    formula_names = ["water", "butanol", "nacl", "kcl"]
    organic_formula = decimals(
        row, [f"organic_x_{name}_formula" for name in formula_names]
    )
    aqueous_formula = decimals(
        row, [f"aqueous_x_{name}_formula" for name in formula_names]
    )
    if organic_formula != [
        Decimal(value) for value in ("0.4426", "0.5570", "0.0000415", "0.000420")
    ]:
        raise ValueError("paper organic formula composition changed")
    if aqueous_formula != [
        Decimal(value) for value in ("0.9627", "0.0122", "0.0076", "0.0174")
    ]:
        raise ValueError("paper aqueous formula composition changed")
    explicit_names = ["water", "butanol", "na", "k", "cl"]
    for phase, formula in (("organic", organic_formula), ("aqueous", aqueous_formula)):
        observed = decimals(
            row, [f"{phase}_x_{name}_explicit" for name in explicit_names]
        )
        expected = explicit_phase(formula)
        if any(
            abs(left - right) > DERIVATION_ABS
            for left, right in zip(observed, expected, strict=True)
        ):
            raise ValueError(f"{phase} formula-to-explicit transformation changed")
        if (
            abs(sum(observed) - Decimal(1)) > DERIVATION_ABS
            or abs(observed[2] + observed[3] - observed[4]) > DERIVATION_ABS
        ):
            raise ValueError(
                f"{phase} explicit composition is not normalized and charge balanced"
            )

    fugacity = decimals(
        row,
        [
            "ln_f_water_bar",
            "ln_f_butanol_bar",
            "ln_f_kcl_pair_bar",
            "ln_f_nacl_pair_bar",
        ],
    )
    if fugacity != [
        Decimal(value) for value in ("-3.521", "-5.088", "-206.733", "-224.891")
    ]:
        raise ValueError("Table 5 log-fugacity values changed")

    if metadata["source_classification"]["model_comparison_allowance"] is not None:
        raise ValueError("source packet must not invent a model cutoff")
    if len(metadata["missing_upstream_provenance"]) != 3:
        raise ValueError("missing-upstream provenance list changed")
    archive = metadata["lab_archive_provenance"]
    negative_space = " ".join(archive["negative_space"])
    for token in (
        "Do not reuse",
        "seeds",
        "controller",
        "tolerances",
        "cannot validate",
    ):
        if token not in negative_space:
            raise ValueError(f"archive negative-space boundary missing: {token}")
    if (
        archive["historical_witnesses"]["strong_negative_witness_min_tpd"]
        != "-0.09607343786579076"
    ):
        raise ValueError("historical negative witness changed")

    support = metadata["supporting_numerical_literature"]
    if (
        support["sha256"]
        != "501d9bdb5dfd89cf5584e050cfcd9cc6580fac5395f809cb91d16d81d1bd1f38"
    ):
        raise ValueError("Belov-Aristova source hash changed")
    if support["line_ranges"] != {
        "broad_concentration_scales_conditioning": "23-27",
        "exact_derivatives_and_automatic_differentiation": "121-132",
        "dimensionless_objective": "134-138",
        "nonnegative_variables_phase_sums_material_balances": "141-187",
        "inventory_normalization_and_review_checks": "301-307",
    }:
        raise ValueError("Belov-Aristova line locators changed")
    if (
        support["classification"]
        != "general numerical-conditioning support only; not electrolyte-LLE or HELD2 evidence"
    ):
        raise ValueError("Belov-Aristova classification changed")

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
        raise ValueError("globality classification changed")

    return {
        "status": "source_contract_ready",
        "case_id": row["case_id"],
        "rows": len(rows),
        "csv_sha256": csv_hash,
        "metadata_sha256": sha256(metadata_path),
        "primary_source_sha256": source_hashes,
        "missing_upstream_sources": len(metadata["missing_upstream_provenance"]),
        "model_output": "not_run",
        "globality_certificate": challenge["globality_certificate"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the frozen source-only Ascani 2022 HELD2 tracer contract."
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    args = parser.parse_args()
    print(json.dumps(check(args.csv, args.metadata), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
