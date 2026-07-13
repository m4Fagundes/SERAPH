"""Plot F1/Dice/BR vs threshold for Cellpose, NuClick, iDISF on the full 100 oral ROIs."""
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from pathlib import Path

R = Path("benchmark/results")
df = pd.read_csv(R / "study_3metrics_full.csv")
ST = {"Cellpose": dict(color="#000000", marker="D", ls="--"),
      "NuClick":  dict(color="#1f77b4", marker="o", ls="-"),
      "iDISF":    dict(color="#d62728", marker="s", ls="-")}

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
for ax, (col, t) in zip(axes, [("f1", "Instance F1 (IoU@0.5)"),
                                ("dice", "Dice (matched nuclei)"),
                                ("br", "Boundary Recall (r=2)")]):
    for m, st in ST.items():
        d = df[df.method == m].sort_values("threshold")
        ax.plot(d.threshold, d[col], **st, lw=2, ms=6, label=m)
        i = int(np.nanargmax(d[col].values))
        ax.scatter([d.threshold.values[i]], [d[col].values[i]], s=150,
                   facecolors="none", edgecolors=st["color"], linewidths=2, zorder=5)
    ax.set_xlabel("threshold"); ax.set_ylim(0, 1); ax.grid(alpha=0.3)
    ax.set_title(t); ax.legend(loc="lower center", fontsize=9)
fig.suptitle("iDISF vs NuClick vs Cellpose - Oral (100 ROIs)\n"
             "iDISF/NuClick seeded by Cellpose centroids; iDISF tuned (it=4,c1=0.5,c2=0.6); circle=best",
             fontsize=12)
fig.tight_layout()
out = R / "study_3metrics_full.png"
fig.savefig(out, dpi=120, bbox_inches="tight")
print("Saved ->", out)
