"""Shared helper: dump PER-IMAGE metric units alongside the pooled CSVs.

The sweep scripts already compute a per-image quantity inside their inner loop
(pixel/boundary TP/FN/FP, or per-image F1/Dice/BR). They only keep the pooled
aggregate. Statistical significance (bootstrap CIs, paired tests) needs the
per-image units, so each sweep also records one row per (model, threshold, image)
and saves it at the end. This adds ZERO model inference -- it only persists
numbers that are already being computed.

Design goal: patching a sweep should be a ONE-LINE change per model loop. The
PerImg recorder numbers images automatically in iteration order (the SAME order
for every model, since they all loop over the same `data`), so callers do not
have to thread an image index through their loops:

    peri = PerImg()
    for p in PROBS:
        for img, A in data:
            a, b, c = pix(A, B); tp += a; fn += b; fp += c
            peri.counts("Cellpose", p, a, b, c)      # <-- the only added line
    ...
    peri.save(OUT)                                    # writes <stem>_perimg.csv

Two schemas, auto-detected downstream by significance.py:
  * counts (pixel / boundary, POOLED metrics):  model, threshold, img, tp, fn, fp
  * values (seeded study, MACRO metrics):       method, threshold, img, f1, dice, br
"""
from __future__ import annotations
from pathlib import Path
from collections import Counter
import csv


class PerImg:
    """Accumulate per-image rows; auto-number images per (entity, threshold)."""

    def __init__(self):
        self.rows = []
        self._n = Counter()

    def _next(self, key):
        i = self._n[key]
        self._n[key] += 1
        return i

    def counts(self, model, threshold, tp, fn, fp, img=None):
        """Record one pooled-metric unit (pixel or boundary TP/FN/FP)."""
        if img is None:
            img = self._next(("c", model, threshold))
        self.rows.append(dict(model=model, threshold=threshold, img=img,
                              tp=int(tp), fn=int(fn), fp=int(fp)))

    def values(self, method, threshold, f1, dice, br, img=None):
        """Record one macro-metric unit (per-image F1/Dice/BR)."""
        if img is None:
            img = self._next(("v", method, threshold))
        self.rows.append(dict(method=method, threshold=threshold, img=img,
                              f1=f1, dice=dice, br=br))

    def save(self, out_csv):
        return save_perimg(self.rows, out_csv)


def save_perimg(rows, out_csv):
    """Write rows (list of dict) to <stem>_perimg.csv next to out_csv.

    Uses the stdlib csv writer so this never depends on pandas being importable.
    Column order follows the first row's keys.
    """
    rows = list(rows)
    out_csv = Path(out_csv)
    dst = out_csv.with_name(out_csv.stem + "_perimg.csv")
    if not rows:
        print(f"[perimg] WARNING: no rows to save for {dst}")
        return dst
    cols = list(rows[0].keys())
    with open(dst, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"[perimg] saved -> {dst} ({len(rows)} rows, cols={cols})", flush=True)
    return dst
