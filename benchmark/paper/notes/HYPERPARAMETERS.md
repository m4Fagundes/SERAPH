# Hyperparameter Reference — Nuclei Segmentation Benchmark (oral epithelium H&E)

Literature/official-docs review of the best hyperparameters for the three benchmarked
models, mapped to the actual tunable knobs in the SERAPH adapters. Use case: RGB H&E
ROIs ~250×450 px, ~28–30 nuclei/ROI, nucleus-only, equivalent diameter ~33 px
(median area ~840 px²) — which corresponds to **40× / 0.25 µm/px**.

> Legend: **[OFFICIAL]** = stated in paper/docs/source. **[HEURISTIC]** = grounded
> recommendation derived for this task, must be validated empirically (not an official optimum).

---

## 1. Cellpose-SAM (`cpsam`, Cellpose v4)

Adapter knobs: `diameter`, `flow_threshold`, `cellprob_threshold` (CellposeAdapter.segment).

| Param | Official default | Direction of effect | Recommended | Sweep range |
|---|---|---|---|---|
| `diameter` | `None` | rescales to 30 px ref; cpsam is size-invariant (trained 7.5–120 px, mean 30) | `None` or `30` (nuclei ≈33 px ≈ training mean) | `{None, 30}` |
| `flow_threshold` | `0.4` | **higher → MORE masks** | `0.4` | `{0.3, 0.4, 0.5, 0.7}` |
| `cellprob_threshold` | `0.0` | **lower → MORE masks** | `0.0` (try negative for dense epithelium) | `{-1.0, -0.5, 0.0, 0.5, 1.0}` |
| channels | n/a | cpsam is channel-invariant, trained on 3-ch H&E; **do not set channels** | feed RGB as-is | — |
| `normalize` | `True` (1st/99th pct) | — | default | — |

- **[OFFICIAL]** cpsam is a single generalist model (no separate v4 nuclei model); training set included Cellpose-Nuclei + TissueNet + H&E. `diameter` is optional.
- **[OFFICIAL]** Higher `flow_threshold` → more ROIs; lower `cellprob_threshold` → more ROIs.
- **[HEURISTIC]** Dense touching epithelium → slightly lower `cellprob_threshold` (more seeds) + moderate `flow_threshold` (avoid merges).
- No official recommendation to invert H&E or to stain-normalize (community lore).

Sources: cellpose.readthedocs.io/en/latest/settings.html · MouseLand/cellpose · Cellpose-SAM bioRxiv 2025 (10.1101/2025.04.28.651001v1).

---

## 2. CellViT-SAM-H (PanNuke)

Adapter knobs: `magnification` (→ `object_size`, `k_size`); watershed thresholds are **hard-coded** (need a code fork to sweep); optional nucleus-type filter (currently keeps all types).

| Param | Official default | Recommended (this task) | Sweep range |
|---|---|---|---|
| Model / checkpoint | — | **CellViT-SAM-H-x40** (already in use) | x40 primary, x20 ablation only |
| `magnification` | 40 | **40** ✓ (33 px nuclei = 0.25 µm/px = 40×) | {40}; {20} as ablation (expect worse, see Issue #55) |
| `object_size` (min nucleus px) | 10 (@40×) | 10 | `{6, 8, 10, 14, 20}` |
| `k_size` (Sobel) | 21 (@40×) | 21 | `{15, 19, 21, 25}` (odd) |
| foreground thr (`blb>=0.5`) | 0.5 | hard-coded | {0.4–0.6} only if forking `__proc_np_hv` |
| marker thr (`overall>=0.4`) | 0.4 | hard-coded | {0.3–0.5} only if forking |
| Type policy | keep all | **report all-types as PRIMARY** | also report {1,5} and {5} as ablations |

- **[OFFICIAL]** Trained on PanNuke @ 40× / 0.25 µm/px, 256 px patches. Inference: 1024 px patches, 64 px overlap. `--magnification` controls rescale + kernel sizes only (does not resample content). Wrong effective MPP degrades the HoVer watershed split.
- **[OFFICIAL]** Your 33 px nuclei ≈ 32–40 px expected at 0.25 µm/px → **x40 / mag=40 is the correct regime. Magnification is NOT the bug.**
- **[OFFICIAL]** No detection-confidence or type-probability cutoff is exposed; every detected instance is kept with an argmax type. No official tissue-specific type filtering.
- **[HEURISTIC] Type-filter caution (important for paper validity):** filtering CellViT to epithelial (type 5) before a **detection** metric is an *oracle* — it silently removes cross-class false positives and **inflates** the score. Report unfiltered (class-agnostic) as primary. Also, in **dysplastic** oral epithelium CellViT may label true epithelial nuclei as **Neoplastic (type 1)** → filtering to {5} alone can DROP true positives and deflate recall. If filtering at all, use {1,5} and report it explicitly.
- For sub-1024 ROIs: pad, never upscale (upscaling shifts effective MPP away from 0.25).

Sources: arXiv:2306.15350 · Medical Image Analysis 2024 (S1361841524000689) · TIO-IKIM/CellViT post_proc_cellvit.py & cell_detection.py · Issue #55 (20× scale bug).

---

## 3. Patho-SAM (`vit_l_histopathology`, micro-sam AIS)

Adapter knobs: `model_type`, `tile_shape`, `halo`, `is_tiled`; AIS `generate()` thresholds are **currently not passed** (uses library defaults) — plumbing needed to tune.

| AIS param | Official default | Direction of effect | Recommended | Sweep range |
|---|---|---|---|---|
| `boundary_distance_threshold` | 0.5 | **lower → more/smaller (splits touching)** — highest-leverage knob | 0.5 → lower for dense nuclei | `0.3–0.6` step 0.05 |
| `center_distance_threshold` | 0.5 | lower → more seeds | 0.5 | `0.3–0.6` step 0.05 |
| `foreground_threshold` | 0.5 | higher → smaller masks, drops dim nuclei | 0.5 | `0.4–0.6` step 0.05 |
| `distance_smoothing` | 1.6 | higher → fewer seeds (less over-seg) | 1.6 | `1.0–2.0` step 0.2 |
| `min_size` | 0 | higher → drops debris | **~25** (floor ≪ 850 px nucleus) | `{0, 15, 25, 50}` |
| `model_type` | vit_b (CLI) / **vit_l recommended** | — | **vit_l_histopathology** ✓ | vit_b vs vit_l (vs vit_h) |
| `segmentation_mode` | ais | — | **ais** ✓ | ais vs apg (if supported) |

- **[OFFICIAL]** AIS > AMG; ViT-L is the accuracy recommendation (your choice ✓). Trained at 512 px patches, halo 64.
- **[OFFICIAL]** Tiling exists to avoid SAM's 1024 px down-resize. A 250×450 ROI is far below 1024 → tiling's purpose does not apply.
- **[HEURISTIC] Highest-value actionable change: set `is_tiled=False` for sub-tile ROIs** (drop `tile_shape`/`halo` in that path). Tiling a 250×450 image with a 384 tile + halo is pure downside and can split nuclei on an artificial seam — a likely source of spurious detections.
- **[OFFICIAL]** No fixed nucleus thresholds published; authors grid-search the boundary threshold for over/under-seg tradeoff.

Sources: computational-cell-analytics/micro-sam instance_segmentation.py & automatic_segmentation.py · micro-sam docs · Patho-SAM arXiv:2502.00408v2 · micro-sam Nature Methods 2025 · patho-sam repo.

---

## Actionable summary (priority order)

1. **PathoSAM: `is_tiled=False` for sub-tile ROIs** + add `min_size≈25` + sweep `boundary_distance_threshold`. (Requires plumbing AIS thresholds through the adapter — currently not exposed.)
2. **CellViT: defaults are already correct for 40×** — main levers are `object_size`/`k_size`; watershed thresholds need a code fork to tune. Do NOT type-filter for the primary detection metric.
3. **Cellpose: defaults already near-optimal** (nuclei ≈ training mean) — sweep `cellprob_threshold` (negative for dense) and `flow_threshold`.

### Plumbing needed before a sweep
- CellposeAdapter: already exposes diameter/flow/cellprob. ✓
- PathoSAMAdapter: expose AIS thresholds + `is_tiled` toggle (currently hard-set).
- CellViTAdapter: expose `object_size`/`k_size` (currently derived from magnification only); watershed thresholds require forking `post_proc_cellvit.__proc_np_hv`.

### Methodological guardrail
Tune each model on a **tuning split / cross-validation fold**, freeze the best config, then
report on a **held-out test fold**. Tuning and reporting on the same ROIs overfits the
hyperparameter selection (worse for models with more knobs). Optimize a stated metric
(recommended: Panoptic Quality, plus F1/IoU/Dice reported).
