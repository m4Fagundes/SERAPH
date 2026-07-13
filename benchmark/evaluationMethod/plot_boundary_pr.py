"""Boundary Precision x Boundary Recall line curve (lab iftEvalBR, r=2) for 4 models.
Same style as the pixel PR plot: iso-F1 lines + best-BF point labeled.

Usage: python plot_boundary_pr.py <boundary_csv> <out_png> "<base label>"
CSV columns: model, threshold, boundary_recall, boundary_precision, boundary_f
"""
import sys
import numpy as np, pandas as pd, matplotlib.pyplot as plt

csv, out, base = sys.argv[1], sys.argv[2], sys.argv[3]
df = pd.read_csv(csv)

STYLES = {
    "Cellpose":    dict(color="#1f77b4", marker="o", label="Cellpose"),
    "CellViT-SAM": dict(color="#2ca02c", marker="^", label="CellViT-SAM"),
    "PathoSAM":    dict(color="#ff7f0e", marker="D", label="PathoSAM"),
    "InstanSeg":   dict(color="#9467bd", marker="s", label="InstanSeg"),
}

fig, ax = plt.subplots(figsize=(8, 7))

# iso-F1 (iso-BF) contours: p = f*r / (2r - f)
for f in [0.2, 0.4, 0.6, 0.8]:
    r = np.linspace(f / 2 + 1e-3, 1, 200)
    p = f * r / (2 * r - f)
    ax.plot(r, p, color="gray", ls="--", lw=0.8, alpha=0.5)
    ax.annotate(f"BF={f:.1f}", xy=(1, p[-1]), xytext=(1.005, p[-1]),
                fontsize=8, color="gray", va="center")

for m, st in STYLES.items():
    d = df[df.model == m].sort_values("threshold")
    if d.empty:
        continue
    rec, prec = d.boundary_recall.values, d.boundary_precision.values
    ax.plot(rec, prec, color=st["color"], marker=st["marker"], ls="-",
            linewidth=2, markersize=6, label=st["label"])
    bf = d.boundary_f.values
    bi = int(np.nanargmax(bf))
    ax.scatter([rec[bi]], [prec[bi]], s=170, facecolors="none",
               edgecolors=st["color"], linewidths=2.4, zorder=5)
    ax.annotate(f"BF={bf[bi]:.3f}", xy=(rec[bi], prec[bi]),
                xytext=(rec[bi] + 0.012, prec[bi] + 0.012),
                fontsize=9, fontweight="bold", color=st["color"], zorder=6)

ax.set_xlabel("Boundary Recall (BR)"); ax.set_ylabel("Boundary Precision (BP)")
ax.set_title(f"Curva Boundary Precision x Recall (lab iftEvalBR, r=2)\n{base}", fontsize=12)
ax.set_xlim(0, 1); ax.set_ylim(0, 1)
ax.grid(alpha=0.3); ax.legend(loc="lower left")

fig.tight_layout(); fig.savefig(out, dpi=130); print(f"Saved -> {out}")
