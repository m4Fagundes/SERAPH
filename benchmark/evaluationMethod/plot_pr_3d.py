"""3D plot of the threshold sweep: recall (X) x precision (Y) x threshold (Z).

Threshold is min-max normalized per model (0 = most permissive, 1 = most strict)
so the three models share the Z axis despite different native scales
(Cellpose cellprob -2..2; CellViT/PathoSAM foreground 0.1..0.9).

Run:  python -m benchmark.evaluationMethod.plot_pr_3d
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

RESULTS = Path("benchmark/results")
TISSUES = ["severe", "healthy"]
COLORS = {"Cellpose": "#1f77b4", "CellViT-SAM": "#2ca02c", "PathoSAM": "#ff7f0e"}


def norm(v: pd.Series) -> np.ndarray:
    v = v.to_numpy(dtype=float)
    span = v.max() - v.min()
    return (v - v.min()) / span if span else np.zeros_like(v)


def add_panel(ax, df, title):
    for model, g in df.groupby("model"):
        g = g.sort_values("threshold")
        z = norm(g["threshold"])
        x, y = g["recall"].to_numpy(), g["precision"].to_numpy()
        c = COLORS.get(model, "#555")
        ax.plot(x, y, z, "-o", color=c, label=model, markersize=4, linewidth=1.8)
        # best-F1 point as a star
        bi = g["f1"].to_numpy().argmax()
        ax.scatter([x[bi]], [y[bi]], [z[bi]], color=c, marker="*", s=180,
                   edgecolors="k", linewidths=0.6, zorder=5)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_zlabel("Limiar (0=permissivo → 1=rígido)")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_zlim(0, 1)
    ax.set_title(title)
    ax.view_init(elev=22, azim=-60)


def main():
    fig = plt.figure(figsize=(15, 7))
    for i, tissue in enumerate(TISSUES, 1):
        csv = RESULTS / f"pr_sweep_{tissue}.csv"
        if not csv.exists():
            print(f"skip {tissue}: {csv} not found")
            continue
        df = pd.read_csv(csv)
        ax = fig.add_subplot(1, 2, i, projection="3d")
        add_panel(ax, df, f"{tissue}  (★ = melhor F1)")
        if i == 1:
            ax.legend(loc="upper left")
    fig.suptitle("Curvas Precisão-Recall-Limiar por modelo", fontsize=14)
    out = RESULTS / "pr_3d_severe_healthy.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    print(f"Saved -> {out}")

    # also a single combined panel (both tissues, dashed = healthy)
    fig2 = plt.figure(figsize=(9, 8))
    ax = fig2.add_subplot(111, projection="3d")
    for tissue, style in [("severe", "-o"), ("healthy", "--^")]:
        csv = RESULTS / f"pr_sweep_{tissue}.csv"
        if not csv.exists():
            continue
        df = pd.read_csv(csv)
        for model, g in df.groupby("model"):
            g = g.sort_values("threshold")
            ax.plot(g["recall"], g["precision"], norm(g["threshold"]), style,
                    color=COLORS.get(model, "#555"), markersize=3, linewidth=1.5,
                    label=f"{model} ({tissue})")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_zlabel("Limiar (0=permissivo → 1=rígido)")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_zlim(0, 1)
    ax.view_init(elev=22, azim=-60)
    ax.set_title("Severe (—) vs Healthy (- -)")
    ax.legend(loc="upper left", fontsize=8)
    out2 = RESULTS / "pr_3d_combined.png"
    fig2.savefig(out2, dpi=160, bbox_inches="tight")
    print(f"Saved -> {out2}")


if __name__ == "__main__":
    main()
