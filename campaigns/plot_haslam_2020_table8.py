"""Render retained Haslam Table-8 cross-EOS rows without recomputing the model."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


SALTS = ("LiCl", "LiBr", "LiI", "NaCl", "NaBr", "NaI", "KCl", "KBr", "KI")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--output-base", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    with args.rows.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    plt.rcParams.update(
        {
            "font.family": "serif",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
        }
    )
    figure, axes = plt.subplots(3, 3, figsize=(11.2, 9.1), sharex=True)
    for axis, salt in zip(axes.flat, SALTS, strict=True):
        gamma = [
            row
            for row in rows
            if row["salt"] == salt and row["observable"] == "gamma_pm_m"
        ]
        phi = [
            row
            for row in rows
            if row["salt"] == salt and row["observable"] == "osmotic_coefficient"
        ]
        for selected, exact, marker, color in (
            (gamma, True, "o", "#1B1B1B"),
            (gamma, False, "^", "#888888"),
            (phi, True, "x", "#285F86"),
            (phi, False, "+", "#9AAAB5"),
        ):
            points = [
                row
                for row in selected
                if (row["source_subset_status"] == "EXACT_HAMER_WU_SUBSET") is exact
            ]
            axis.scatter(
                [float(row["molality_mol_kg"]) for row in points],
                [float(row["literature_value"]) for row in points],
                s=23,
                marker=marker,
                facecolors="white" if marker in {"o", "^"} else None,
                edgecolors=color if marker in {"o", "^"} else None,
                color=color,
                linewidths=0.9,
                zorder=4 if selected is gamma else 3,
            )
        evaluated = [row for row in gamma if row["artifact_status"] == "EVALUATED"]
        if evaluated:
            axis.plot(
                [float(row["molality_mol_kg"]) for row in evaluated],
                [float(row["model_value"]) for row in evaluated],
                color="#A13A2A",
                linewidth=1.8,
                marker="o",
                markersize=2.2,
                zorder=2,
            )
        axis.set_xscale("log")
        axis.set_title(
            salt
            if evaluated
            else salt + r"  ($\gamma_{\pm}$ model NE; I$^{-}$ absent)",
            fontsize=12 if evaluated else 9.5,
        )
        axis.grid(True, which="major", color="#D9D9D9", linewidth=0.55)
        axis.tick_params(direction="out")
    figure.supxlabel(r"Formula-unit molality, $m$ / mol kg$^{-1}$", y=0.035)
    figure.supylabel(
        r"Dimensionless coefficient, $\Phi$ or $\gamma_{\pm}^{m}$", x=0.015
    )
    legend = [
        Line2D(
            [],
            [],
            marker="o",
            linestyle="none",
            markerfacecolor="white",
            markeredgecolor="#1B1B1B",
            label=r"exact Table-8 $\gamma_{\pm}^{m}$ source",
        ),
        Line2D(
            [],
            [],
            marker="^",
            linestyle="none",
            markerfacecolor="white",
            markeredgecolor="#888888",
            label=r"partial Hamer-Wu $\gamma_{\pm}^{m}$ grid",
        ),
        Line2D(
            [],
            [],
            marker="x",
            linestyle="none",
            color="#285F86",
            label=r"exact Table-8 $\Phi$ source",
        ),
        Line2D(
            [],
            [],
            marker="+",
            linestyle="none",
            color="#9AAAB5",
            label=r"partial Hamer-Wu $\Phi$ grid",
        ),
        Line2D(
            [],
            [],
            color="#A13A2A",
            linewidth=1.8,
            marker="o",
            markersize=3,
            label=r"clean ePC-SAFT $\gamma_{\pm}^{m}$",
        ),
    ]
    figure.legend(
        handles=legend,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.93),
        ncols=5,
        frameon=False,
    )
    figure.suptitle(
        "Haslam Table 8 source grid: aqueous alkali halides at 298.15 K and 0.101 MPa",
        y=0.985,
    )
    figure.text(
        0.5,
        0.012,
        "Cross-EOS comparison. Provider has no public Φ observable; iodides are absent.",
        ha="center",
        fontsize=9,
    )
    figure.subplots_adjust(
        left=0.075, right=0.985, bottom=0.09, top=0.84, wspace=0.18, hspace=0.28
    )
    figure.savefig(args.output_base.with_suffix(".png"), bbox_inches="tight", dpi=220)
    figure.savefig(args.output_base.with_suffix(".svg"), bbox_inches="tight")
    figure.savefig(args.output_base.with_suffix(".pdf"), bbox_inches="tight")
    svg = args.output_base.with_suffix(".svg")
    svg.write_text(
        "\n".join(
            line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()
        )
        + "\n",
        encoding="utf-8",
    )
    retained = {
        "rows_csv": args.rows,
        "comparison_csv": args.comparison,
        "receipt_json": args.receipt,
        "plot_png": args.output_base.with_suffix(".png"),
        "plot_svg": args.output_base.with_suffix(".svg"),
        "plot_pdf": args.output_base.with_suffix(".pdf"),
    }
    manifest = {
        "schema_version": 1,
        "campaign_id": "haslam-2020-table8-cross-eos",
        "command": sys.argv,
        "retained_files": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in retained.items()
        },
        "plot_input_rows_sha256": sha256(args.rows),
    }
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    plt.close(figure)


if __name__ == "__main__":
    main()
