"""Pool the severe + healthy threshold sweeps into one dataset (100 ROIs) and
recompute precision/recall/F1 per model at every threshold 0.1-0.9.

Reads pr_sweep_severe.csv + pr_sweep_healthy.csv (micro tp/fp/fn per model/threshold),
sums them, recomputes metrics, saves pr_sweep_pooled.csv and a 2D PR plot.

Run:  python -m benchmark.evaluationMethod.pool_sweep
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = Path("benchmark/results")
COLORS = {"Cellpose": "#1f77b4", "CellViT-SAM": "#2ca02c", "PathoSAM": "#ff7f0e"}
XLIM, YLIM = (0.30, 0.88), (0.45, 0.90)


def iso_f1(ax):
    r = np.linspace(XLIM[0], XLIM[1], 300)
    for f in (0.4, 0.5, 0.6, 0.7, 0.8):
        p = (f * r) / (2 * r - f)
        p[(p <= 0) | (p > 1)] = np.nan
        ax.plot(r, p, color="lightgray", lw=0.8, ls="--", zorder=0)
        vis = np.where(np.isfinite(p) & (p >= YLIM[0]) & (p <= YLIM[1]))[0]
        if len(vis):
            ax.annotate(f"F1={f:g}", (r[vis[-1]], p[vis[-1]]), color="gray", fontsize=7, va="center")


def main():
    sev = pd.read_csv(R / "pr_sweep_severe.csv")
    hea = pd.read_csv(R / "pr_sweep_healthy.csv")
    both = pd.concat([sev, hea], ignore_index=True)
    g = both.groupby(["model", "threshold"], as_index=False)[["tp", "fp", "fn"]].sum()
    g["precision"] = (g.tp / (g.tp + g.fp)).round(4)
    g["recall"] = (g.tp / (g.tp + g.fn)).round(4)
    g["f1"] = (2 * g.tp / (2 * g.tp + g.fp + g.fn)).round(4)
    g.to_csv(R / "pr_sweep_pooled.csv", index=False)

    print("=== Sweep POOLED (severe+healthy, 100 ROIs) — best F1 per model ===")
    for m, sub in g.groupby("model"):
        b = sub.loc[sub.f1.idxmax()]
        print(f"  {m:12} bestF1={b.f1:.3f} @ thr={b.threshold}  (prec={b.precision:.3f}, rec={b.recall:.3f})")
    print()
    for m in ["Cellpose", "CellViT-SAM", "PathoSAM"]:
        sub = g[g.model == m].sort_values("threshold")
        print(f"--- {m} ---")
        print(sub[["threshold", "precision", "recall", "f1"]].round(3).to_string(index=False))

    # plot
    fig, ax = plt.subplots(figsize=(9, 8))
    iso_f1(ax)
    for m, sub in g.groupby("model"):
        sub = sub.sort_values("threshold")
        x, y, f1, th = sub.recall.values, sub.precision.values, sub.f1.values, sub.threshold.values
        c = COLORS.get(m, "#555")
        ax.plot(x, y, "-o", color=c, label=m, markersize=5, lw=1.6, zorder=3)
        for xi, yi, ti in zip(x, y, th):
            ax.annotate(f"{ti:g}", (xi, yi), fontsize=5.5, color=c, xytext=(3, 3),
                        textcoords="offset points")
        bi = f1.argmax()
        ax.scatter([x[bi]], [y[bi]], color=c, marker="*", s=240, edgecolors="k", linewidths=0.7, zorder=5)
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_xlim(*XLIM); ax.set_ylim(*YLIM); ax.grid(True, alpha=0.25); ax.legend(loc="lower left")
    ax.set_title("Sweep de limiar — dataset unico (100 ROIs)  [pontos rotulados = limiar; ★=melhor F1]")
    out = R / "pr_2d_pooled.png"
    fig.savefig(out, dpi=170, bbox_inches="tight")
    print(f"\nSaved -> {R/'pr_sweep_pooled.csv'} and {out}")


if __name__ == "__main__":
    main()
