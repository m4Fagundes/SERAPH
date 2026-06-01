"""Precision-Recall scatter of the ensemble study: Cellpose / PathoSAM / Consensus / Union,
both tissues, with iso-F1 contours. Reads ensemble_cellpose_pathosam.csv.

Run:  python -m benchmark.evaluationMethod.plot_ensemble
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CSV = Path("benchmark/results/ensemble_cellpose_pathosam.csv")
COLORS = {"Cellpose": "#1f77b4", "PathoSAM": "#ff7f0e", "Consenso": "#2ca02c", "Uniao": "#d62728"}
MARKERS = {"severe": "o", "healthy": "^"}


def iso_f1(ax, xlim, ylim):
    r = np.linspace(xlim[0], xlim[1], 300)
    for f in (0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85):
        p = (f * r) / (2 * r - f)
        p[(p <= 0) | (p > 1)] = np.nan
        ax.plot(r, p, color="lightgray", lw=0.8, ls="--", zorder=0)
        vis = np.where(np.isfinite(p) & (p >= ylim[0]) & (p <= ylim[1]))[0]
        if len(vis):
            j = vis[-1]
            ax.annotate(f"F1={f:g}", (r[j], p[j]), color="gray", fontsize=7, ha="left", va="center")


def main():
    df = pd.read_csv(CSV)
    xlim, ylim = (0.55, 0.92), (0.45, 0.92)
    fig, ax = plt.subplots(figsize=(10, 8))
    iso_f1(ax, xlim, ylim)
    for _, r in df.iterrows():
        c = COLORS.get(r["method"], "#555")
        ax.scatter(r["recall"], r["precision"], color=c, marker=MARKERS.get(r["tissue"], "o"),
                   s=160, edgecolors="k", linewidths=0.6, zorder=4)
        ax.annotate(f"{r['method']} ({r['tissue']})\nF1={r['f1']:.2f}",
                    (r["recall"], r["precision"]), fontsize=7, xytext=(6, 4),
                    textcoords="offset points", color=c)
    # legend: method colors + tissue markers
    from matplotlib.lines import Line2D
    leg = [Line2D([0], [0], marker="s", color="w", markerfacecolor=COLORS[m], markersize=10, label=m)
           for m in COLORS]
    leg += [Line2D([0], [0], marker=MARKERS[t], color="k", linestyle="", markersize=9,
                   label=f"{t}") for t in MARKERS]
    ax.legend(handles=leg, loc="lower left", fontsize=8, ncol=2)
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.grid(True, alpha=0.25)
    ax.set_title("Ensemble Cellpose + PathoSAM — Precisão × Recall (severe ● / healthy ▲)")
    out = Path("benchmark/results/ensemble_pr.png")
    fig.savefig(out, dpi=170, bbox_inches="tight")
    print(f"Saved -> {out}")


if __name__ == "__main__":
    main()
