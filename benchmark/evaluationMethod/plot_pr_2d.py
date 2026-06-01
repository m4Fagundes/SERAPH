"""2D precision-recall plot per tissue, annotating each threshold point with
recall and F1. Light iso-F1 contours in the background for reference.

Run:  python -m benchmark.evaluationMethod.plot_pr_2d
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path("benchmark/results")
TISSUES = ["severe", "healthy"]
COLORS = {"Cellpose": "#1f77b4", "CellViT-SAM": "#2ca02c", "PathoSAM": "#ff7f0e"}
XLIM = (0.30, 0.88)   # zoom on the populated recall region
YLIM = (0.45, 0.90)   # ...and precision (top extended so healthy Cellpose isn't clipped)


def iso_f1(ax):
    r = np.linspace(XLIM[0], XLIM[1], 300)
    for f in (0.4, 0.5, 0.6, 0.7, 0.8):
        p = (f * r) / (2 * r - f)          # precision s.t. F1 == f
        p[(p <= 0) | (p > 1)] = np.nan
        ax.plot(r, p, color="lightgray", lw=0.8, ls="--", zorder=0)
        # label where the iso line is inside the visible window
        vis = np.where(np.isfinite(p) & (p >= YLIM[0]) & (p <= YLIM[1]))[0]
        if len(vis):
            j = vis[-1]
            ax.annotate(f"F1={f:g}", (r[j], p[j]), color="gray",
                        fontsize=7, ha="left", va="center")


def plot_tissue(ax, df, title):
    iso_f1(ax)
    for model, g in df.groupby("model"):
        g = g.sort_values("threshold")
        x, y, f1 = g["recall"].to_numpy(), g["precision"].to_numpy(), g["f1"].to_numpy()
        c = COLORS.get(model, "#555")
        ax.plot(x, y, "-o", color=c, label=model, markersize=5, lw=1.6, zorder=3)
        for xi, yi, fi in zip(x, y, f1):
            ax.annotate(f"r={xi:.2f}\nF1={fi:.2f}", (xi, yi), color=c, fontsize=5.5,
                        xytext=(3, 3), textcoords="offset points", zorder=4)
        bi = f1.argmax()
        ax.scatter([x[bi]], [y[bi]], color=c, marker="*", s=240,
                   edgecolors="k", linewidths=0.7, zorder=5)
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_xlim(*XLIM); ax.set_ylim(*YLIM)
    ax.set_title(title); ax.grid(True, alpha=0.25); ax.legend(loc="lower left")


def main():
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    for ax, tissue in zip(axes, TISSUES):
        csv = RESULTS / f"pr_sweep_{tissue}.csv"
        if not csv.exists():
            print(f"skip {tissue}"); continue
        plot_tissue(ax, pd.read_csv(csv), f"{tissue}  (★ = melhor F1)")
    fig.suptitle("Precisão × Recall por limiar — anotado com recall (r) e F1", fontsize=14)
    out = RESULTS / "pr_2d_severe_healthy.png"
    fig.savefig(out, dpi=170, bbox_inches="tight")
    print(f"Saved -> {out}")

    # individual high-res per tissue too
    for tissue in TISSUES:
        csv = RESULTS / f"pr_sweep_{tissue}.csv"
        if not csv.exists():
            continue
        fig1, ax = plt.subplots(figsize=(9, 8))
        plot_tissue(ax, pd.read_csv(csv), f"{tissue}  (★ = melhor F1)")
        o = RESULTS / f"pr_2d_{tissue}.png"
        fig1.savefig(o, dpi=170, bbox_inches="tight")
        print(f"Saved -> {o}")


if __name__ == "__main__":
    main()
