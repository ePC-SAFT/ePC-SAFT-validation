#!/usr/bin/env python3
"""Render retained pure-saturation regression tables without package imports."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output-stem", required=True, type=Path)
    return parser


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 19:
        raise ValueError("expected all 19 methane/ethane reporting rows")
    return rows


def _normalize_svg(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(line.rstrip() for line in lines) + "\n", encoding="utf-8")


def render(csv_path: Path, output_stem: Path) -> None:
    rows = _read_rows(csv_path)
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 9.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.22,
            "grid.linewidth": 0.6,
            "svg.hashsalt": "consumer-slice-2-pure-saturation-regression-v1",
        }
    )
    fig, axes = plt.subplots(2, 2, figsize=(8.2, 6.2))
    colors = {"methane": "#0072B2", "ethane": "#D55E00"}
    labels = {"methane": "Methane", "ethane": "Ethane"}
    for column, component in enumerate(("methane", "ethane")):
        selected = sorted(
            (row for row in rows if row["component_id"] == component),
            key=lambda row: float(row["temperature_k"]),
        )
        temperature = [float(row["temperature_k"]) for row in selected]
        observed_pressure = [float(row["observed_pressure_pa"]) / 1.0e6 for row in selected]
        fitted_pressure = [float(row["fitted_predicted_pressure_pa"]) / 1.0e6 for row in selected]
        observed_density = [float(row["observed_liquid_density_kg_m3"]) for row in selected]
        fitted_density = [float(row["fitted_predicted_liquid_density_kg_m3"]) for row in selected]
        pressure_ax = axes[0, column]
        density_ax = axes[1, column]
        pressure_ax.plot(temperature, fitted_pressure, color=colors[component], lw=1.8, label="Fitted model")
        density_ax.plot(temperature, fitted_density, color=colors[component], lw=1.8, label="Fitted model")
        for partition, marker, face in (
            ("training", "o", "white"),
            ("held_out", "s", "white"),
            ("stress", "X", colors[component]),
        ):
            points = [(i, row) for i, row in enumerate(selected) if row["partition"] == partition]
            if not points:
                continue
            indices = [item[0] for item in points]
            scatter_kw = {
                "marker": marker,
                "s": 31,
                "edgecolor": colors[component],
                "facecolor": face,
                "linewidth": 1.0,
                "zorder": 3,
                "label": partition.replace("_", " ").title() + " observation",
            }
            pressure_ax.scatter([temperature[i] for i in indices], [observed_pressure[i] for i in indices], **scatter_kw)
            density_ax.scatter([temperature[i] for i in indices], [observed_density[i] for i in indices], **scatter_kw)
        pressure_ax.set_yscale("log")
        pressure_ax.set_title(f"{labels[component]} saturation pressure")
        pressure_ax.set_xlabel("Temperature, $T$ (K)")
        pressure_ax.set_ylabel("Saturation pressure, $P_{sat}$ (MPa)")
        density_ax.set_title(f"{labels[component]} saturated-liquid density")
        density_ax.set_xlabel("Temperature, $T$ (K)")
        density_ax.set_ylabel(r"Liquid density, $\rho_l$ (kg m$^{-3}$)")
        pressure_ax.legend(frameon=False, fontsize=7.5)
        density_ax.legend(frameon=False, fontsize=7.5)
    fig.suptitle("Pure-saturation regression: NIST observations and fitted installed artifact", fontsize=12)
    fig.tight_layout(rect=(0.0, 0.055, 1.0, 0.95), h_pad=1.6, w_pad=1.1)
    fig.text(
        0.5,
        0.012,
        "Start-model predictions are not exposed by the public regression result; 100 K ethane is an excluded stress failure.",
        ha="center",
        va="bottom",
        fontsize=7.5,
    )
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    svg_path = output_stem.with_suffix(".svg")
    fig.savefig(svg_path, metadata={"Date": None})
    _normalize_svg(svg_path)
    fig.savefig(output_stem.with_suffix(".png"), dpi=220, metadata={"Software": "Matplotlib"})
    fig.savefig(
        output_stem.with_suffix(".pdf"),
        metadata={"CreationDate": None, "ModDate": None, "Title": "Pure-saturation regression validation"},
    )
    plt.close(fig)


def main() -> int:
    args = build_parser().parse_args()
    render(args.csv.resolve(), args.output_stem.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
