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
    "b2e17682992e94a1edcfa84df0fb497130cf9f158eda2ea502f865b3d7a52553"
)


def load_campaign():
    spec = importlib.util.spec_from_file_location(
        "perdomo_table3_public_route", CAMPAIGN
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_perdomo_input_column_derives_frozen_public_feed(
    tmp_path: Path,
) -> None:
    campaign = load_campaign()
    # The accepted D-025 result is bound to SOURCE_COMMIT, not to the evolving
    # canonical ledger used by later source-selection decisions.
    snapshot_paths = []
    for source_path in (METADATA, CASES, SAMPLES):
        snapshot = tmp_path / source_path.name
        snapshot.write_bytes(
            subprocess.check_output(
                [
                    "git",
                    "show",
                    f"{campaign.SOURCE_COMMIT}:{source_path.relative_to(ROOT)}",
                ],
                cwd=ROOT,
            )
        )
        snapshot_paths.append(snapshot)
    source = campaign.load_source_contract(*snapshot_paths)

    assert source["sample_id"] == "table3-nacl-5.6molal"
    assert source["feed_derivation"]["normalized_feed"] == list(campaign.FEED_Z)
    assert source["reported_phase_count"] == 2


def test_public_route_result_keeps_package_and_source_decisions_separate() -> None:
    campaign = load_campaign()
    record = json.loads(RECORD.read_text(encoding="utf-8"))

    assert hashlib.sha256(RECORD.read_bytes()).hexdigest() == EXPECTED_RECORD_SHA256
    assert campaign.check_record(record)["status"] == (
        "PUBLIC_ROUTE_PASS_SOURCE_TOPOLOGY_DISAGREEMENT"
    )
    assert record["public_route_audit"]["symbol"] == ("epcsaft_equilibrium.tp_flash")
    diagnostics = record["public_route_audit"]["result"]["diagnostics"]
    assert diagnostics["outcome"] == "one_phase"
    assert diagnostics["attempts"] == 30
    assert diagnostics["search_status"] == "complete_no_negative_found"
    assert diagnostics["best_tpd"] == -1.6139519381498581e-12
    assert diagnostics["root_completeness"] == "not_proven"
    assert diagnostics["globality_certificate"] == "not_guaranteed"
    assert diagnostics["solver_status"] == "passed"
    assert diagnostics["numerical_status"] == "passed"
    assert diagnostics["physical_status"] == "passed"
    assert diagnostics["failure_reason"] == ""
    assert record["frozen_search_contract"] == {
        "declared_starts": 30,
        "observed_attempts": 30,
        "private_adapter_called": False,
        "search_profile": "perdomo-held2-stage-i-installed-v1",
        "search_status": "complete_no_negative_found",
        "seed": 2025,
    }
    comparison = record["source_comparison"]
    assert comparison["published_phase_count"] == 2
    assert comparison["returned_phase_count"] == 1
    assert comparison["topology_status"] == "disagreement_cross_eos"
    assert comparison["topology_disagreement"] is True
    assert comparison["endpoint_status"] == ("not_evaluated_phase_count_disagreement")
    assert record["decisions"] == {
        "artifact_input": "PASS",
        "globality": "NOT_GUARANTEED",
        "numerical": "PASS",
        "physical": "PASS",
        "predictive_endpoint_comparison": "NOT_EVALUATED",
        "public_route": "PASS",
        "root_completeness": "NOT_PROVEN",
        "search_completeness": "PASS_DECLARED_30_OF_30",
        "solver": "PASS",
        "source_topology_comparison": "DISAGREEMENT_CROSS_EOS",
    }
    assert record["execution_accounting"] == {
        "canonical_execution": "hardened_public_replay_1",
        "hardened_public_solver_executions": 1,
        "scientific_status": "completed_and_retained",
        "serialization_reruns": 0,
    }
    assert record["root_evidence"] == {
        "detected_roots": {
            "classification": "package_reported_context_not_publicly_exposed",
            "value": 3,
        },
        "mechanically_stable_roots": {
            "classification": "package_reported_context_not_publicly_exposed",
            "value": 2,
        },
        "package_context_source": {
            "commit": "8a7164869975c03291fcf3296b1228b4b4a0f5b4",
            "owner": "epcsaft-equilibrium",
            "tree": "744132063d8b26ae3ef7ba7eb3094226aec31fd6",
        },
        "public_surface_boundary": (
            "HeldDiagnostics exposes root_completeness but not detected-root "
            "or mechanically-stable-root counts; Validation does not infer "
            "those counts from the accepted phase."
        ),
        "public_terminal_root_completeness": "not_proven",
        "selected_molar_volume_m3_per_mol": 0.9849669199245724,
    }
    assert record["globality_certificate"] == "not_guaranteed"


def test_artifact_source_and_public_only_negative_space_are_hash_bound() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))

    assert record["artifacts"]["provider"]["sha256"] == (
        "9e4da0d7ba7896bcd2ec096400553d935e0516c61f1bd9f41f2370ab68ab36ea"
    )
    assert record["artifacts"]["equilibrium"]["sha256"] == (
        "41192aa4ab1821a0546ba100352dfd9254c67884d26511ea1504205647aa08d4"
    )
    assert record["artifacts"]["equilibrium"]["wheel_record_sha256"] == (
        "dba4daeaa74bf98783debc42c5c6d5b8f007841b7bf4566c47793b7052eac974"
    )
    provider_members = {
        member["member"]: member["sha256"]
        for member in record["artifacts"]["provider"]["required_members"]
    }
    assert provider_members["epcsaft/include/epcsaft/native_sdk_v1.h"] == (
        "51ac8d251ffbc53e019c8cf7828fd51d2a011ff2871b3e606eb08573a1c9183b"
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
        "PUBLIC_ROUTE_PASS_SOURCE_TOPOLOGY_DISAGREEMENT"
    )
