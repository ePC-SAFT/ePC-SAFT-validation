import ast
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data" / "may-2015-row-012-provider-topology-diagnostic.yaml"
RUNNER = ROOT / "campaigns" / "may_2015_row_012_provider_topology.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("may_2015_row_012_provider_topology", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_contract_freezes_row_012_and_independent_public_route() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    source = contract["source"]
    assert source["row_id"] == "may2015-ch4-c2h6-012"
    assert source["source_liquid_x_methane"] == 0.6218
    assert source["source_vapor_y_methane"] == 0.7123
    assert source["feed_z_methane"] == pytest.approx((0.6218 + 0.7123) / 2.0)
    assert contract["artifact"]["equilibrium_runtime_used"] is False
    assert contract["objective"]["source_composition_root_selection"] == (
        "all distinct mechanically stable public roots at each explicit source composition"
    )
    assert contract["numerical_contract"]["globality"].startswith("finite adaptive evidence")


def test_runner_is_public_provider_only_and_requires_exact_inputs() -> None:
    runner = _load_runner()
    parser = runner.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(name.startswith("epcsaft_equilibrium") for name in imported)
    assert not any(name.startswith("epcsaft._") for name in imported)


def test_golden_section_refines_a_continuous_basin() -> None:
    runner = _load_runner()
    result = runner.golden_minimize(lambda x: (x - 0.314159) ** 2 + 2.0, 0.2, 0.5, 96, 1e-12)
    assert result["converged"] is True
    assert result["x"] == pytest.approx(0.314159, abs=2e-8)
    assert result["value"] == pytest.approx(2.0, abs=1e-14)
