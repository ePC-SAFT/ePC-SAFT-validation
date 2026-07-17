import ast
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "pure_saturation_regression.py"
PLOTTER = ROOT / "campaigns" / "plot_pure_saturation_regression.py"


def _load_campaign():
    spec = importlib.util.spec_from_file_location("pure_saturation_regression", CAMPAIGN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_campaign_contract_rejects_unbound_artifacts_and_incomplete_status(tmp_path: Path) -> None:
    campaign = _load_campaign()
    parser = campaign.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(ValueError, match="wheel"):
        campaign.require_wheel(tmp_path / "provider.txt")
    with pytest.raises(ValueError, match="component status is missing"):
        campaign.validate_result_contract(
            {"components": [{"solver_status": "PASS", "numerical_status": "PASS"}]},
            [],
            [],
        )


def test_plotter_is_package_independent() -> None:
    tree = ast.parse(PLOTTER.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(name.startswith(("epcsaft", "epcsaft_regression")) for name in imported)
