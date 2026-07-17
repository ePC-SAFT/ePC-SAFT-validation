"""Render retained real-data predictions without recomputing the EOS."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def save(figure: plt.Figure, output_base: Path) -> None:
    for suffix, options in ((".png", {"dpi": 220}), (".svg", {}), (".pdf", {})):
        figure.savefig(output_base.with_suffix(suffix), bbox_inches="tight", **options)
    svg_path = output_base.with_suffix(".svg")
    normalized_svg = "\n".join(
        line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines()
    )
    svg_path.write_text(f"{normalized_svg}\n", encoding="utf-8")
    plt.close(figure)


def activity_plot(rows: list[dict[str, str]], output_base: Path) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(8.6, 7.0))
    for axis, ethanol_mass_percent in zip(axes.flat, (20, 40, 60, 80), strict=True):
        selected = [
            row
            for row in rows
            if int(row["ethanol_mass_percent"]) == ethanol_mass_percent
        ]
        molality = [float(row["molality_mol_kg"]) for row in selected]
        literature = [float(row["gamma_pm_m_literature"]) for row in selected]
        model = [float(row["gamma_pm_m_model"]) for row in selected]
        axis.scatter(
            molality,
            literature,
            s=28,
            facecolors="white",
            edgecolors="#171717",
            linewidths=0.9,
            label="Esteso et al. (1989)",
            zorder=3,
        )
        axis.plot(
            molality,
            model,
            color="#176B87",
            linewidth=1.8,
            label="clean provider",
            zorder=2,
        )
        axis.set_xscale("log")
        axis.set_title(f"{ethanol_mass_percent} wt% ethanol")
        axis.grid(True, which="major", color="#D7D7D7", linewidth=0.6)
        axis.tick_params(direction="out")
    figure.supxlabel(r"NaCl molality, $m$ / mol kg$^{-1}$", y=0.025)
    figure.supylabel(r"Mean ionic activity coefficient, $\gamma_{\pm}^{m}$", x=0.015)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.91),
        ncols=2,
        frameon=False,
    )
    figure.suptitle("NaCl activity in water–ethanol at 298.15 K", y=0.975)
    figure.subplots_adjust(
        left=0.10, right=0.985, bottom=0.10, top=0.82, wspace=0.20, hspace=0.30
    )
    save(figure, output_base)


def density_plot(rows: list[dict[str, str]], output_base: Path) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(10.2, 3.8))
    for axis, salt in zip(axes, ("LiCl", "LiBr", "NaBr"), strict=True):
        selected = [row for row in rows if row["salt"] == salt]
        molality = [float(row["molality_mol_kg"]) for row in selected]
        literature = [float(row["density_kg_m3_literature"]) for row in selected]
        model = [float(row["density_kg_m3_model"]) for row in selected]
        axis.scatter(
            molality,
            literature,
            s=38,
            facecolors="white",
            edgecolors="#171717",
            linewidths=1.0,
            label="Held et al. (2012)",
            zorder=3,
        )
        axis.plot(
            molality,
            model,
            color="#9C2F1F",
            linewidth=1.8,
            marker="o",
            markersize=3.0,
            label="clean provider",
            zorder=2,
        )
        axis.set_title(salt)
        axis.grid(True, color="#D7D7D7", linewidth=0.6)
        axis.tick_params(direction="out")
    figure.supxlabel(r"Salt molality, $m$ / mol kg$^{-1}$", y=0.02)
    figure.supylabel(r"Solution density, $\rho$ / kg m$^{-3}$", x=0.015)
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.88),
        ncols=2,
        frameon=False,
    )
    figure.suptitle("Ethanol electrolyte densities at 298.15 K", y=0.98)
    figure.subplots_adjust(left=0.09, right=0.985, bottom=0.18, top=0.72, wspace=0.25)
    save(figure, output_base)


def pure_ethanol_plot(rows: list[dict[str, str]], output_base: Path) -> None:
    if len(rows) != 1:
        raise ValueError("expected one pure-ethanol density row")
    row = rows[0]
    figure, axis = plt.subplots(figsize=(5.2, 3.8))
    values = [
        float(row["density_kg_m3_literature"]),
        float(row["density_kg_m3_model"]),
    ]
    axis.bar(
        ["Held et al. (2012)", "clean provider"],
        values,
        color=["white", "#6A4C93"],
        edgecolor="#171717",
        linewidth=1.0,
    )
    axis.set_ylabel(r"Liquid density, $\rho$ / kg m$^{-3}$")
    axis.set_title("Pure ethanol at 298.15 K and ambient pressure")
    axis.set_ylim(760.0, 800.0)
    axis.grid(True, axis="y", color="#D7D7D7", linewidth=0.6)
    axis.tick_params(direction="out")
    save(figure, output_base)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    arguments = parser.parse_args()
    results = arguments.results_dir.resolve()
    plt.rcParams.update(
        {
            "font.family": "serif",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
        }
    )
    activity_plot(
        read_rows(results / "esteso-1989-water-ethanol-nacl.csv"),
        results / "esteso-1989-water-ethanol-nacl",
    )
    density_plot(
        read_rows(results / "held-2012-ethanol-salt-density.csv"),
        results / "held-2012-ethanol-salt-density",
    )
    pure_ethanol_plot(
        read_rows(results / "held-2012-pure-ethanol-density.csv"),
        results / "held-2012-pure-ethanol-density",
    )


if __name__ == "__main__":
    main()
