from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "perdomo_table3_public_route.py"
METADATA = ROOT / "data" / "perdomo-2025-held2-source-ledger.yaml"
CASES = ROOT / "data" / "perdomo-2025-held2-case-ledger.csv"
SAMPLES = ROOT / "data" / "perdomo-2025-held2-published-samples.csv"
RECORD = ROOT / "results" / "perdomo-table3-public-route-validation.json"
EXPECTED_RECORD_SHA256 = (
    "2a712e44f3e0b7d29c3ac8513be7391209d0a946860284c6840f4cb97c7609a9"
)


def load_campaign():
    spec = importlib.util.spec_from_file_location(
        "perdomo_table3_public_route", CAMPAIGN
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_perdomo_input_column_derives_frozen_public_feed() -> None:
    campaign = load_campaign()
    source = campaign.load_source_contract(METADATA, CASES, SAMPLES)

    assert source["sample_id"] == "table3-nacl-5.6molal"
    assert source["feed_derivation"]["normalized_feed"] == list(campaign.FEED_Z)
    assert source["reported_phase_count"] == 2


def test_public_route_absence_stops_all_scientific_decision_layers() -> None:
    campaign = load_campaign()
    record = json.loads(RECORD.read_text(encoding="utf-8"))

    assert hashlib.sha256(RECORD.read_bytes()).hexdigest() == EXPECTED_RECORD_SHA256
    assert campaign.check_record(record)["status"] == (
        "NOT_EVALUATED_PUBLIC_ROUTE_ABSENT"
    )
    assert record["public_route_audit"]["symbol"] == ("epcsaft_equilibrium.tp_flash")
    diagnostics = record["public_route_audit"]["exception_diagnostics"]
    assert diagnostics["outcome"] == "invalid_input"
    assert diagnostics["attempts"] == 0
    assert diagnostics["failure_reason"] == "tp_flash requires exactly two components"
    assert record["frozen_search_contract"] == {
        "declared_starts": 30,
        "private_adapter_called": False,
        "seed": 2025,
        "status": "not_started_public_route_absent",
    }
    assert record["source_comparison"] == {
        "endpoint_status": "not_evaluated_no_public_result",
        "published_phase_count": 2,
        "returned_phase_count": None,
        "topology_disagreement": None,
        "topology_status": "not_evaluated_public_route_absent",
    }
    assert all(
        record["decisions"][axis] == "NOT_EVALUATED"
        for axis in (
            "solver",
            "numerical",
            "physical",
            "source_topology_comparison",
            "predictive_endpoint_comparison",
            "search_completeness",
        )
    )
    assert record["globality_certificate"] == "not_guaranteed"


def test_artifact_source_and_public_only_negative_space_are_hash_bound() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))

    assert record["artifacts"]["provider"]["sha256"] == (
        "9e4da0d7ba7896bcd2ec096400553d935e0516c61f1bd9f41f2370ab68ab36ea"
    )
    assert record["artifacts"]["equilibrium"]["sha256"] == (
        "ff34db9643b79dad9df0095c190d55f98e02f4fc268e073ec83594669b277831"
    )
    assert (
        record["artifacts"]["retained_package_trace_context_only"]["sha256"]
        == "0ff032a747992a6add25dc6228da0628fcf901dc176f7f408a61c7a9c82903df"
    )
    assert record["source"]["authority_commit"] == (
        "5620f030b1e4bf12cde2f97d739cb931653eb960"
    )
    assert record["source"]["metadata"]["sha256"] == (
        "2cce8ab35505b67622c4096604d4051122516b374bd36aea0ea12848eab8b436"
    )
    assert record["input"]["parameter_fingerprint"] == (
        "sha256:7c637771bc9f717b8f47b44bb2a61044c3fe83084dca7c3c16102fba0989912d"
    )
    assert record["environment"]["imports_from_isolated_site_packages"] is True
    assert all(
        "site-packages" in record["environment"][key]
        for key in ("provider_import_origin", "equilibrium_import_origin")
    )

    tree = ast.parse(CAMPAIGN.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(
        name.startswith(("epcsaft", "epcsaft_equilibrium")) for name in imported
    )
    private_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr.startswith("_held2")
    ]
    assert private_calls == []

    completed = subprocess.run(
        [sys.executable, str(CAMPAIGN), "check", str(RECORD)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == (
        "NOT_EVALUATED_PUBLIC_ROUTE_ABSENT"
    )
