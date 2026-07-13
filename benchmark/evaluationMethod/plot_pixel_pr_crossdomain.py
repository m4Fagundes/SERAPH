"""Single cross-domain figure: pixel PR (V1) for the 3 bases side by side,
each with iso-F1 level curves + best-F1 marker. Cellpose uses no-flow data
when available (falls back to the filtered sweep otherwise).

Output: benchmark/results/pr_pixel_crossdomain.png
"""
from pathlib import Path
import numpy as np, pandas as pd, matplotlib.pyplot as plt

R = Path("benchmark/results")

# (panel title, base pixel CSV, cellpose no-flow CSV or None, noflow column names)
BASES = [
    ("Oral epithelium (H&E)", "pixel_pr_sweep_both.csv",
     "cellpose_noflow_sweep.csv", ("pix_prec", "pix_rec")),
    ("NuInsSeg (H&E, 665)", "pixel_pr_sweep_nuinsseg_stride1.csv",
     "cellpose_noflow_pixel_nuinsseg.csv", ("v1_prec", "v1_rec")),
    ("CryoNuSeg (frozen H&E)", "pixel_pr_sweep_cryonuseg.csv",
     None, None),  # Cellpose already flow=0 in this CSV
    ("IHC (immunohistochemistry)", "pixel_pr_sweep_ihc.csv",
     "cellpose_noflow_pixel_ihc.csv", ("v1_prec", "v1_rec")),
]
STYLES = {
    "Cellpose":    dict(color="#1f77b4", marker="o"),
    "CellViT-SAM": dict(color="#2ca02c", marker="^"),
    "PathoSAM":    dict(color="#ff7f0e", marker="D"),
    "InstanSeg":   dict(color="#9467bd", marker="s"),
}


def load_base(pixel_csv, noflow_csv, cols):
    df = pd.read_csv(R / pixel_csv)
    if noflow_csv is None:
        return df[["model", "threshold", "v1_prec", "v1_rec"]], True  # already no-flow
    nf = R / noflow_csv
    used_noflow = False
    if nf.exists():
        n = pd.read_csv(nf)
        if "flow_threshold" in n.columns:
            n = n[n.flow_threshold == 0.0]
        cp = pd.DataFrame({"model": "Cellpose", "threshold": n["threshold"].values,
                           "v1_prec": n[cols[0]].values, "v1_rec": n[cols[1]].values})
        df = pd.concat([df[df.model != "Cellpose"][["model", "threshold", "v1_prec", "v1_rec"]], cp],
                       ignore_index=True)
        used_noflow = True
    return df, used_noflow


def draw_iso_f1(ax):
    for f in [0.2, 0.4, 0.6, 0.8]:
        r = np.linspace(f / 2 + 1e-3, 1, 200)
        p = f * r / (2 * r - f)
        ax.plot(r, p, color="gray", ls="--", lw=0.8, alpha=0.5)
        ax.annotate(f"{f:.1f}", xy=(0.995, p[-1]), fontsize=7, color="gray", va="center")


fig, axes2d = plt.subplots(2, 2, figsize=(12, 10))
axes = axes2d.ravel()
for ax, (title, pcsv, ncsv, cols) in zip(axes, BASES):
    df, nf = load_base(pcsv, ncsv, cols)
    draw_iso_f1(ax)
    for m, st in STYLES.items():
        d = df[df.model == m].sort_values("threshold")
        if d.empty:
            continue
        rec, prec = d.v1_rec.values, d.v1_prec.values
        ax.plot(rec, prec, color=st["color"], marker=st["marker"], ls="-",
                lw=2, ms=5, label=m)
        f1 = 2 * prec * rec / np.clip(prec + rec, 1e-9, None)
        bi = int(np.nanargmax(f1))
        ax.scatter([rec[bi]], [prec[bi]], s=150, facecolors="none",
                   edgecolors=st["color"], linewidths=2.2, zorder=5)
        ax.annotate(f"{f1[bi]:.3f}", xy=(rec[bi], prec[bi]),
                    xytext=(rec[bi] + 0.01, prec[bi] + 0.012), fontsize=8,
                    fontweight="bold", color=st["color"])
    tag = "" if nf else "  [Cellpose w/ filter]"
    ax.set_title(title + tag, fontsize=11)
    ax.set_xlabel("Recall (pixel)"); ax.set_ylabel("Precision (pixel)")
    ax.set_xlim(0.4, 1); ax.set_ylim(0.4, 1)
    ax.grid(alpha=0.3)
axes[0].legend(loc="lower left", fontsize=9)
fig.suptitle("Foreground pixel-wise Precision-Recall across domains - iso-F1 level curves dashed; "
             "circle = best F1", fontsize=12)
fig.tight_layout()
out = R / "pr_pixel_crossdomain.png"
fig.savefig(out, dpi=140); print(f"Saved -> {out}")
