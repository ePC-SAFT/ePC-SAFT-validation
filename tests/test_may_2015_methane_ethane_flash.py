import ast
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "may_2015_methane_ethane_flash.py"
PLOTTER = ROOT / "campaigns" / "plot_may_2015_methane_ethane_flash.py"


def _load_campaign():
    spec = importlib.util.spec_from_file_location("may_2015_methane_ethane_flash", CAMPAIGN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_flash_contract_requires_frozen_source_and_local_non_global_rows(tmp_path: Path) -> None:
    campaign = _load_campaign()
    parser = campaign.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    changed_source = tmp_path / "changed.csv"
    changed_source.write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source CSV SHA-256"):
        campaign.load_source(changed_source)
    with pytest.raises(ValueError, match="17 rows"):
        campaign.validate_result_contract(
            {"globality_certificate": False},
            [{"globality_certificate": False, "row_admission": "PASS"}],
        )


def test_flash_plotter_is_package_independent() -> None:
    tree = ast.parse(PLOTTER.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(name.startswith(("epcsaft", "epcsaft_equilibrium")) for name in imported)
