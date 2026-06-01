# Benchmark — Research Log & Findings

Living document tracking the comparative analysis of three nuclei-segmentation methods
(**Cellpose-SAM**, **CellViT-SAM-H**, **PathoSAM ViT-L**) on oral-epithelium H&E.
Organized as *research question → evidence → conclusion* for article writing.

Last updated: 2026-06-01

---

## 0. Experimental setup

- **Task:** instance segmentation of cell nuclei in H&E histopathology (oral epithelium).
- **Ground truth (GT):** `oral_epithelium_db/annotations/instance/{class}/{roi}.png` — the
  dataset's reference instance annotation (per the activation-pack README: *"Copy of dataset
  (annotations + original TIFFs)"*). 8-bit PNG, lossless, max instance id observed = 49
  (so 8-bit is sufficient, no overflow). **`per_cell_strict/` is NOT the GT** — it is derived
  from Cellpose flow + a strict saliency filter (`cp_flow_source`, saliency_threshold 0.3),
  so using it as GT would be circular (Cellpose-vs-Cellpose).
- **Predictions:** SERAPH GUI export ("Export Instance Masks") → uint32 TIFF + NPY + manifest.
  Run analysed: `run1`, class `severe`, 114 ROIs (~250×450 px each).
- **GT coverage:** 50 of 114 severe ROIs are annotated (64 ROIs have no GT PNG).
- **Evaluation:** `run_exported_vs_db_gt.py` (maps each prediction to its GT PNG by
  `slice_name`, reuses `matching.match` + `metrics.compute_metrics`). Default IoU@0.5.
- **Nucleus geometry:** GT median area ~840 px², equivalent diameter ~33 px → corresponds to
  **40× / 0.25 µm/px**.

---

## 1. Headline result — who scores best on this GT?

**50 severe ROIs, IoU@0.5 (mean per ROI):**

| Model | Precision | Recall | **F1** | mean IoU | mean Dice | Boundary IoU | HD95 | ASD |
|---|---|---|---|---|---|---|---|---|
| **Cellpose** | 0.787 | 0.678 | **0.701** | 0.756 | 0.857 | 0.168 | 5.98 | 1.98 |
| **CellViT-SAM** | 0.545 | 0.730 | **0.618** | 0.751 | 0.853 | 0.192 | 5.95 | 1.93 |
| **PathoSAM** | 0.510 | 0.698 | **0.581** | 0.740 | 0.846 | 0.179 | 6.10 | 1.97 |

Micro-averaged F1: Cellpose **0.732**, CellViT 0.635, PathoSAM 0.610.

**Conclusion:** Against this GT, **Cellpose has the highest F1**, driven by far higher
precision (fewer false positives). CellViT/PathoSAM have higher recall but ~2× the FP.

---

## 2. Research questions answered

### Q1 — Do the models differ in delineation quality (contour accuracy)?
**Evidence:** On matched (TP) nuclei, mean IoU ≈ 0.74–0.76 and mean Dice ≈ 0.85–0.86 for all
three; boundary IoU and surface distances (HD95 ~6 px, ASD ~2 px) are nearly identical.
**Conclusion:** **No.** Delineation quality is statistically comparable across the three.
The differences live entirely in *detection* (how many / which nuclei), not in contour
precision. (Contradicts the initial visual impression that CellViT/PathoSAM delineate better.)

### Q2 — Why do CellViT/PathoSAM score lower despite being "newer/better"?
**Evidence (detection counts):** instances/ROI — GT 28.3, Cellpose 25.5, CellViT 38.7,
PathoSAM 38.9 (CellViT/PathoSAM ≈ +37% over GT).
**FP autopsy (where the errors fall):**

| Model | matched | orphan (on GT-empty region) | near-miss (IoU<0.5) | GT split (≥2 preds) |
|---|---|---|---|---|
| Cellpose | 78% | 15% | 8% | 1% |
| CellViT-SAM | 55% | **27%** | 18% | 5% |
| PathoSAM | 53% | **28%** | 19% | 5% |

**Conclusion:** The lower score is **not** a delineation failure. ~27–28% of CellViT/PathoSAM
detections land where the GT has no annotation (orphans), and ~18% are near-misses (mask
slightly smaller/offset). Over-splitting is minor (5%).

### Q3 — "The model fragments one cell into micro-regions" — true?
**Evidence:** GT cells receiving ≥2 prediction centroids: Cellpose 1%, CellViT 7%, PathoSAM 8%.
Mean predictions per GT cell ≈ 1.0. GT-cell **area coverage** by predictions: Cellpose 62%,
CellViT 72%, PathoSAM 67%.
**Conclusion:** Fragmentation is **real but minor (7–8%)**. The dominant effect is that
prediction masks are **smaller than the GT cells** (cover only ~67–72% of GT area) → drives
the near-miss bucket. "Doesn't fill the whole cell" ✓ confirmed; "splits into many cells"
mostly not.

### Q4 — Is it the model or the GT/database? (the central question)
**Evidence:** Visual overlay (GT outline vs CellViT outline on H&E) shows: (a) red model
contours sit just inside green GT contours (the ~70% coverage), and (b) clear dark, compact
nuclei on the right are detected by CellViT (red) with **no GT** — the GT annotates the pale
elongated epithelial nuclei and skips the dark compact ones.
**Conclusion (provisional):** The ranking is largely an **evaluation-protocol effect**: the GT
appears to annotate a *subset* of nuclei (epithelial-type), so CellViT/PathoSAM — generic
nucleus detectors — are penalized for detecting real nuclei the GT omits. *Still to confirm
quantitatively (see Open Questions Q-A vs Q-B).* The user's domain inspection states the GT is
correct and nucleus-only; if so, the orphans would instead be genuine model false positives.

### Q5 — Without GT, do the methods agree? (oral cancer base, `runNoGT`, 1×1000×1000)
**Evidence:** counts — Cellpose 289, CellViT 318, PathoSAM 331 (within ~15%). Pairwise
agreement (IoU@0.5 mutual confirmation) 95–98%, matched-pair IoU 0.79–0.89. 96% of Cellpose
nuclei confirmed by **both** others; 0% seen only by Cellpose.
Proportion vs Cellpose: severe 1.52/1.53× → noGT 1.10/1.15× (methods much closer here).
**Conclusion:** Where there is no annotation bias, **the three methods strongly converge.**
This is strong evidence that CellViT/PathoSAM are **not mis-configured/broken** — the severe
gap is driven by the GT, not by model failure. (Caveat: n=1 image; needs more slices.)

### Q6 — Is PNG a lossy/bad format for masks?
**Evidence:** PNG is lossless (DEFLATE), not JPEG-like. GT is 8-bit grayscale, max id 49 < 255
→ no overflow. Predictions are stored as uint32 NPY (benchmark reads NPY) → fully lossless.
**Conclusion:** PNG was safe here. The only risk is 8-bit's 255-instance cap — relevant for
dense tissue (e.g. the oral-cancer image had 289–331 instances; a 16-bit/NPY GT would be
required there). Recommend NPY or 16/32-bit TIFF for any future dense GT.

### Q7 — Are the default hyperparameters appropriate? (literature review → HYPERPARAMETERS.md)
**Evidence:** Official docs/papers reviewed. Cellpose-SAM defaults near-optimal (nuclei ≈ 30 px
training mean). CellViT-SAM-H trained at 40×/0.25 µm/px → x40 + magnification=40 (current
setting) is **correct**; magnification is *not* the bug. PathoSAM tiling exists only to avoid
SAM's 1024 px down-resize → unnecessary/harmful for sub-tile ROIs.
**Conclusion:** Most defaults are already right. The clear actionable: **disable PathoSAM
tiling for small ROIs** (see Q8). Type-filtering CellViT is an *oracle* that biases detection
metrics — report unfiltered as primary.

### Q8 — Does disabling PathoSAM tiling help? (experiment, all 50 ROIs vs GT, micro-averaged)
**Evidence (full 50 ROIs, 1425 GT nuclei):**

| Metric | Tiled (384/64, current) | Untiled (is_tiled=False) | Δ |
|---|---|---|---|
| Predictions | 1946 | 1856 | −90 |
| False positives | 921 | **803** | **−118 (−13%)** |
| True positives | 1025 | 1053 | +28 |
| Precision | 0.527 | 0.567 | +0.041 |
| Recall | 0.724 | 0.744 | +0.020 |
| **F1 (micro)** | 0.610 | **0.644** | **+0.034** |

(8-ROI pilot showed the same direction: F1 0.624 → 0.663.) Sanity check: the tiled micro-F1
(0.610) reproduces the original `run1` PathoSAM result, validating the test harness.

**Conclusion:** Disabling tiling improves PathoSAM on every axis simultaneously (more TP **and**
fewer FP), F1 +0.034 with no threshold change — confirming the tiling-on-small-ROI artifact is
real and material. **However, untiled PathoSAM (0.644) still trails Cellpose (0.732 micro)** —
the orphan/GT-subset effect (Q4) dominates and is not fixed by tiling.

---

### Q9 — Boundary Recall / mean Dice — does the ranking change? (50 ROIs, IoU@0.5)
**Evidence:**

| Model | mean Dice | Boundary Recall | Boundary Precision | Boundary F |
|---|---|---|---|---|
| **CellViT-SAM** | 0.853 | **0.612** | 0.557 | **0.578** |
| **Cellpose** | 0.857 | 0.533 | **0.605** | 0.552 |
| **PathoSAM** | 0.846 | 0.559 | 0.528 | 0.535 |

Boundary metrics are class-agnostic (combined boundary maps, 2 px tolerance, no matching).
**Conclusion:** **The ranking flips with the metric.** Mean Dice is tied (~0.85, per-nucleus
contour equal — consistent with Q1). On **Boundary Recall and Boundary F, CellViT wins**
(first metrics where it beats Cellpose); Cellpose wins **Boundary Precision** (fewer spurious
edges). Honest caveat: BR rewards detection completeness — CellViT's BR lead largely reflects
its higher detection recall (it covers more GT edges by detecting more nuclei), not better
per-nucleus contour fidelity (Dice is tied). Report BR alongside BP + boundary-F; BR alone is
misleading under over-segmentation. **Takeaway for the paper:** there is no single winner —
the preferred method depends on whether the application weights precision (Cellpose) or
boundary/detection completeness (CellViT).

### Q12 — Precision-Recall threshold sweep: how tunable is each model? (50 ROIs severe)
**Setup:** each model swept over its own detection-confidence knob (scales differ):
Cellpose `cellprob_threshold` ∈ [−2,2]; CellViT foreground-prob threshold ∈ [0.1,0.9];
PathoSAM AIS `foreground_threshold` ∈ [0.1,0.9]. Network forward runs once per ROI; only the
threshold-dependent postprocessing repeats. Tool: `threshold_sweep.py` → `pr_sweep_severe.csv`
+ `.png`. Plumbing added: CellViT now passes foreground *probability* (not argmax), postprocessor
`fg_threshold` settable (0.5 = old behaviour, no regression); Cellpose native.

**Best F1 per model (and the threshold that achieves it):**
| Model | best F1 | @ threshold | precision | recall | range of recall over sweep |
|---|---|---|---|---|---|
| **Cellpose** | **0.745** | cellprob −0.5 | 0.780 | 0.713 | 0.35 – 0.71 (wide) |
| PathoSAM | 0.647 | fg 0.4 | 0.568 | 0.753 | 0.66 – 0.77 (narrow) |
| CellViT-SAM | 0.629 | fg 0.1 | 0.538 | 0.756 | 0.751 – 0.756 (flat) |

**Conclusions:**
1. **Tunability differs sharply.** Cellpose's `cellprob` is a wide, well-behaved knob (recall
   0.35→0.71). **CellViT is fully saturated** — F1 ≈ 0.628 at every threshold (binary head is
   near-0/1, nothing to threshold). PathoSAM has only a narrow usable range.
2. **Tuning does NOT change the ranking.** At each model's *own best* threshold:
   Cellpose 0.745 > PathoSAM 0.647 > CellViT 0.629 — same order as the defaults. You cannot
   tune CellViT/PathoSAM to beat Cellpose on this GT.
3. **Cellpose's PR curve dominates**: in the overlapping recall region (~0.66–0.71) its
   precision (0.78–0.80) is far above CellViT/PathoSAM (~0.54–0.57). No curve crossing.
4. Cellpose's own best (cellprob −0.5, F1 0.745) beats its default (0.0, F1 0.728) — a small,
   honest tuning gain. Its curve is non-monotonic at the low end (cellprob −2 recall drops to
   0.61) because over-inclusion merges adjacent nuclei.

**Healthy sweep (50 ROIs) — same pattern:** best F1 Cellpose **0.830** @ cellprob −0.5
(rec 0.48→0.81, wide), PathoSAM 0.672 @ fg 0.5 (narrow), CellViT 0.612 @ fg 0.7 (flat /
saturated, recall fixed ~0.83). **Ranking unchanged at best thresholds on both tissues**
(Cellpose > PathoSAM > CellViT). Notably **cellprob −0.5 is Cellpose's optimum on BOTH tissues**
— a reproducible tuning result. Files: `pr_sweep_healthy.csv` + `.png`.

**Why CellViT can't be thresholded — confirmed it's not a pipeline bug:**
- *By design:* official CellViT `calculate_instance_map` feeds the binary channel through
  `torch.argmax` (cellvit.py:372) → hard 0/1; the `blb_raw >= 0.5` in `__proc_np_hv`
  (post_proc_cellvit.py:179) is a no-op on that 0/1 map. No tunable foreground threshold exists
  in the reference implementation.
- *By measurement* (`measure_cellvit_saturation.py`, 562k pixels): the softmax foreground map is
  **99.58% saturated** — 74.2% < 0.1, 25.4% > 0.9, only **0.42% in the 0.1–0.9 band**. Sweeping
  the foreground threshold touches <0.5% of pixels → detection unchanged. Histogram:
  `cellvit_prob_histogram.png`.
- *Nuance:* CellViT's instance separation comes from the **continuous HV map** (+ hard-coded
  watershed marker threshold 0.4) and `object_size`, NOT the near-binary foreground map. A real
  CellViT PR curve needs a **per-instance confidence ranking** (e.g. mean logit margin) or
  sweeping the watershed/object-size knobs — not the foreground probability.

NOTE: Cellpose sweep axis converted from cellprob logit to probability 0.1–0.9 via
cellprob=logit(p) (`rerun_cellpose_prob.py`); precision/recall identical, only axis relabelled.
Best Cellpose F1 0.744 @ p=0.4 (severe). Supporting literature in the References section.

### Q11 — Does the result hold on the other tissue (healthy)?
**Evidence — Healthy (50 ROIs, IoU@0.5):**

| Model | Precision | Recall | F1 | F1 micro | Dice | Boundary F | inst/ROI |
|---|---|---|---|---|---|---|---|
| **Cellpose** | 0.864 | 0.797 | **0.825** | **0.821** | 0.893 | **0.711** | 24.4 |
| CellViT-SAM | 0.501 | 0.826 | 0.605 | 0.619 | 0.894 | 0.653 | 43.4 |
| PathoSAM | 0.492 | 0.798 | 0.595 | 0.613 | 0.888 | 0.610 | 42.2 |

GT ~26 nuclei/ROI. Common nuclei (all 3) = 892 (69% of GT): CellViT best IoU 0.822 / Dice
0.899 / per-nucleus winner 39% (Cellpose 36%, PathoSAM 25%).

**Severe vs Healthy (F1):** Cellpose 0.70 → **0.83** (+0.12); CellViT 0.62 → 0.61 (~0);
PathoSAM 0.58 → 0.60 (~0). Precision: Cellpose 0.79→0.86; CellViT 0.55→0.50; PathoSAM 0.51→0.49.

**Conclusion:**
1. **Ranking is identical on both tissues** (Cellpose > CellViT > PathoSAM in F1) → robust result.
2. On healthy, **Cellpose's lead widens** (F1 +0.12) while CellViT/PathoSAM are flat — likely
   because healthy epithelium has more uniform, separated nuclei that match Cellpose's
   conservative detection, while CellViT/PathoSAM keep over-detecting (43/ROI vs GT 26,
   precision ~0.50).
3. **Over-detection is structural**: ~+65% over GT in both tissues.
4. CellViT still has the best common-nucleus delineation on healthy, but the margin is
   **smaller** than on severe (39% vs 36% wins, vs 45% vs 26% on severe).

### Q10 — On the nuclei ALL THREE detected, who delineates best? (detection-controlled)
**Evidence:** Restricting to GT nuclei matched (IoU≥0.5) by Cellpose AND CellViT AND PathoSAM
— **820 nuclei = 58% of GT** — and scoring each model's matched mask vs GT:

| Model | mean IoU | mean Dice | per-nucleus best-IoU wins |
|---|---|---|---|
| **CellViT-SAM** | **0.781** | **0.873** | **372 (45%)** |
| PathoSAM | 0.767 | 0.865 | 233 (28%) |
| Cellpose | 0.764 | 0.862 | 215 (26%) |

**Conclusion:** With detection neutralized, **CellViT-SAM has the best delineation** — highest
IoU and Dice, and the per-nucleus winner ~45% of the time (≈2× the others). The overall Dice
(Q1) looked tied because detection differences washed out the signal; controlling for that
reveals CellViT draws the best contour on commonly-detected nuclei. This **supports the visual
impression** that CellViT/PathoSAM delineate better — it was masked by their detection penalty
(orphans, Q4). Margin is small (ΔIoU ≈ +0.017 over Cellpose) but consistent across all three
measures. (Tool: `common_nuclei_analysis.py`.)

---

### Q13 — Ensemble Cellpose + PathoSAM (consensus vs union, both tissues)
**Setup:** combine the already-exported masks (no re-run). Consensus = nuclei both models detect
(IoU≥0.5); Union = nuclei either detects. Micro-averaged vs GT. Tool: `ensemble_study.py` →
`ensemble_cellpose_pathosam.csv`.

| Method | Severe P / R / F1 | Healthy P / R / F1 |
|---|---|---|
| Cellpose | 0.776 / 0.693 / **0.732** | 0.848 / 0.797 / **0.821** |
| PathoSAM | 0.531 / 0.730 / 0.615 | 0.495 / 0.804 / 0.613 |
| **Consensus** | **0.783** / 0.624 / 0.695 | **0.871** / 0.720 / 0.789 |
| **Union** | 0.551 / **0.776** / 0.645 | 0.515 / **0.858** / 0.643 |

**Conclusion:** Consensus yields the **highest precision** of any method (0.78 / 0.87 — above
Cellpose alone), Union the **highest recall** (0.78 / 0.86), but **neither beats Cellpose on F1**
(0.732 / 0.821). Combining does not fix the structural over-detection (PathoSAM's extra
detections still count as FP in the union; requiring agreement drops recall in the consensus).
Practical takeaway: the ensemble gives two tunable extremes — Consensus for max precision,
Union for max recall — while Cellpose alone remains the best balanced (F1) choice.

## 3. Methodological decisions (for the Methods section)

- **Fair comparison via per-model tuning is legitimate** (not p-hacking) *as long as* each
  model is tuned symmetrically and selection uses a **separate tuning split**, with final
  metrics on a **held-out test fold** (k-fold CV recommended, n=50 is small). Tuning and
  reporting on the same ROIs overfits the *hyperparameter selection* (worse for models with
  more knobs) — the networks themselves are frozen and do not memorize.
- **Optimization target:** Panoptic Quality (PQ) recommended as primary; report F1/IoU/Dice.
- **Type-filtering caution:** filtering CellViT to a single nucleus type before a detection
  metric removes cross-class FP as an oracle → report class-agnostic as primary; any type
  policy ({5} or {1,5}) reported explicitly as an ablation.
- **Statistics:** paired Wilcoxon across ROIs + confidence intervals (means alone insufficient).

---

## 4. Tooling / artifacts produced

- `run_exported_vs_db_gt.py` — evaluate SERAPH export vs dataset PNG GT.
- `gt_to_tile_xml.py` — convert GT instance PNG → SERAPH-importable tile XML (`gt-pathology` layer).
- `test_pathosam_tiling.py` — tiled vs untiled PathoSAM experiment.
- `HYPERPARAMETERS.md` — literature/official hyperparameter reference per model.
- Bug fixes in `app/application/import_service.py` (uncommitted): (1) name-authoritative tile
  matching (fixes all imports merging into the first tile); (2) coordinate re-basing of
  imported polygons onto the matched tile's WSI origin (fixes GT misalignment when slices are
  laid out across a canvas via Import-Slice-Images-Folder).

---

## 5. Open questions / next steps

- **Q-A vs Q-B (resolve Q4):** are the orphans real unannotated nuclei (GT is a subtype subset)
  or genuine model false positives? Resolve via CellViT `type_map` analysis and/or manual
  classification of a sample of orphans (ideally pathologist-reviewed).
- Confirm Q8 (PathoSAM untiled) on all 50 ROIs.
- Implement adapter plumbing: PathoSAM auto-tiling toggle + expose AIS thresholds; CellViT
  expose object_size/k_size.
- Build cross-validated hyperparameter sweep harness (PQ objective, held-out test).
- Add PQ + mAP + paired statistics to the evaluation.
- Stratify analysis healthy vs severe.

---

## References

Used to ground the CellViT saturation / threshold-inertness argument (Q12). Note: the CellViT
paper itself does **not** discuss saturation — that is our empirical measurement (99.58%); these
references support the *mechanism* and the *postprocessing design*.

- **Hörst et al. (2023)** — *CellViT: Vision Transformers for precise cell segmentation and
  classification.* The model under test. States the binary (NP) branch is trained with
  Focal-Tversky + Dice loss and that postprocessing follows HoVer-Net. arXiv:2306.15350 ·
  https://arxiv.org/abs/2306.15350 · code: https://github.com/TIO-IKIM/CellViT
- **Graham et al. (2019)** — *HoVer-Net: Simultaneous Segmentation and Classification of Nuclei
  in Multi-Tissue Histology Images*, Medical Image Analysis. Source of the postprocessing CellViT
  inherits: the NP branch separates nucleus-vs-background (the binarization), the HoVer branch
  splits touching nuclei via watershed. arXiv:1812.06499 · https://arxiv.org/abs/1812.06499 ·
  https://www.sciencedirect.com/science/article/abs/pii/S1361841519301045 ·
  code: https://github.com/vqdang/hover_net
- **Yeung et al. (2022)** — *Calibrating the Dice loss to handle neural network overconfidence for
  biomedical image segmentation*, J. Imaging Informatics in Medicine. Documents that soft-Dice
  losses produce **miscalibrated, highly overconfident** models — the mechanism behind the
  near-binary (saturated) CellViT foreground map. Proposes DSC++ (γ penalty on overconfidence).
  arXiv:2111.00528 · https://arxiv.org/abs/2111.00528 ·
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10039156/

**Argument chain for the paper:** CellViT binary branch uses Dice+Focal-Tversky (Hörst 2023) →
Dice losses are known to produce overconfident/saturated outputs (Yeung 2022) → binarization &
instance split follow HoVer-Net's argmax+watershed, not a tunable probability (Graham 2019) →
our measurement confirms 99.58% saturation on this dataset → the foreground threshold is inert,
so a fair PR curve for CellViT requires per-instance confidence ranking, not pixel thresholding.

- **2026-06-01** — Q15: InstanSeg grid search (56 configs). Best F1 0.641 @ seed=0.8/peak=7/
  mask=0.5 vs default 0.635 (+0.006, noise). seed_threshold the only strong knob (collapses at
  0.9); mask inert; peak minor. Tuned InstanSeg still 2nd, ranking unchanged.
- **2026-06-01** — Q14: InstanSeg (embedding-based, non-SAM) implemented as SERAPH adapter
  (`external/instanseg`, `instanseg_adapter.py`, registered in composition root + UI) and
  benchmarked: pooled F1 0.635 → 2nd place (above CellViT/PathoSAM, below Cellpose); more
  precise than the SAM models (~40% fewer FP) but most conservative (lowest recall).
- **2026-06-01** — Q13 ensemble (`ensemble_study.py`): Cellpose+PathoSAM consensus = highest
  precision (0.78/0.87), union = highest recall (0.78/0.86), but neither beats Cellpose F1
  (0.732/0.821). Ensemble gives tunable precision/recall extremes, not a better F1.

### Q14 — InstanSeg (non-SAM, embedding-based) added as 4th method
**Setup:** InstanSeg (`brightfield_nuclei`, pixel_size 0.25) integrated as a SERAPH adapter
(`instanseg_adapter.py`, repo in `external/instanseg`). Embedding-based — no foreground
threshold + watershed, so none of the CellViT-style binarization/saturation. Evaluated on the
pooled 100 ROIs (`run_instanseg.py` → `results_instanseg.csv`).

| Method | Precision | Recall | F1 | Dice | Boundary F | TP | FP | FN |
|---|---|---|---|---|---|---|---|---|
| Cellpose | 0.811 | 0.743 | **0.775** | 0.875 | 0.632 | 2005 | 466 | 695 |
| **InstanSeg** | 0.601 | 0.672 | **0.635** | 0.864 | 0.547 | 1824 | 1211 | 890 |
| CellViT-SAM | 0.521 | 0.787 | 0.627 | 0.874 | 0.616 | 2137 | 1967 | 577 |
| PathoSAM | 0.511 | 0.762 | 0.612 | 0.867 | 0.572 | 2069 | 1983 | 645 |

**Conclusion:** InstanSeg lands **2nd in F1** (0.635) — above both SAM models, below Cellpose.
It is markedly **more precise** than CellViT/PathoSAM (0.60 vs 0.52/0.51; ~40% fewer FP) but the
**most conservative** (lowest recall 0.672, highest FN). Dice tied (~0.86). Adds a genuinely
different detection profile (conservative, non-SAM, no binary-map saturation).

### Q15 — InstanSeg hyperparameter grid search (56 configs, pooled 100 ROIs)
**Setup:** `instanseg_gridsearch.py` swept seed_threshold {0.3–0.9} × peak_distance {3,5,7,10}
× mask_threshold {0.3,0.5}, optimizing micro-F1 (pixel_size 0.25, deterministic model).
Results: `instanseg_gridsearch.csv`.

**Best:** seed_threshold=0.8, peak_distance=7, mask_threshold=0.5 → **F1 0.641** (P 0.675, R 0.611).
Default ≈ F1 0.635. **Tuning gain = +0.006** (within noise).

| Knob | Effect (mean F1) |
|---|---|
| seed_threshold | 0.3→0.61, peak at 0.8→0.640, **collapses at 0.9→0.47** (too strict) |
| peak_distance | minor (3→0.600 … 10→0.609; higher = slightly more precise) |
| mask_threshold | inert (0.604 vs 0.603) |

**Conclusions:** (1) InstanSeg is near its ceiling at default — tuning adds essentially nothing
(+0.006 F1, noise-level), it only re-balances precision↔recall (seed=0.8 lifts precision to
0.675 at the cost of recall). (2) seed_threshold is the only strong knob; mask_threshold inert,
peak_distance minor. (3) **Even tuned, InstanSeg (0.641) stays 2nd** — above CellViT (0.627) and
PathoSAM (0.612), below Cellpose (0.775). Ranking is robust to tuning, consistent with Q12.

## Changelog
- **2026-06-01** — Initial consolidation: setup, headline results, Q1–Q8, methodology,
  tooling, open questions. PathoSAM tiling experiment added (Q8, 8-ROI pilot).
- **2026-06-01** — Q8 confirmed on all 50 ROIs (micro-averaged): untiled PathoSAM F1
  0.610 → 0.644 (−118 FP, +28 TP); still below Cellpose. Tiled result reproduces `run1`
  (harness validated).
- **2026-06-01** — Added Boundary Recall / Precision / F to `metrics.py` (class-agnostic,
  2 px tol). Q9: ranking flips by metric — CellViT wins Boundary Recall (0.612) & Boundary F
  (0.578); Cellpose wins Boundary Precision (0.605); mean Dice tied (~0.85).
- **2026-06-01** — Q10 (`common_nuclei_analysis.py`): on the 820 nuclei detected by all 3
  (58% of GT), CellViT-SAM has best delineation (IoU 0.781, Dice 0.873, per-nucleus winner
  45%). Detection-controlled comparison supports the "CellViT delineates better" impression.
- **2026-06-01** — Q11: healthy class evaluated (50 ROIs). Same ranking as severe
  (Cellpose>CellViT>PathoSAM). Cellpose F1 jumps 0.70→0.83 on healthy; CellViT/PathoSAM flat;
  over-detection structural (~+65%). Results in `results_healthy.csv`.
- **2026-06-01** — Q12 threshold sweep done on BOTH tissues (`threshold_sweep.py`,
  `pr_sweep_{severe,healthy}.csv/.png`). Tunability differs (Cellpose wide / PathoSAM narrow /
  CellViT saturated); ranking unchanged at best thresholds; cellprob −0.5 optimal for Cellpose
  on both. Plumbing: CellViT fg_threshold now tunable (prob-based, 0.5=no regression).
- **2026-06-01** — 3D PR-threshold plots (`plot_pr_3d.py` → `pr_3d_severe_healthy.png`,
  `pr_3d_combined.png`): axes recall×precision×threshold (Z normalized 0–1). Visualizes
  tunability — Cellpose sweeps a diagonal curve, CellViT is a near-vertical (saturated) line,
  PathoSAM a short segment. ★ marks best F1.
- **2026-06-01** — Built `benchmark_severe_healthy.lab` (`build_lab_project.py`): 50 severe +
  50 healthy ROIs, each with Cellpose/CellViT/PathoSAM + gt-pathology layers; polygons
  simplified (approxPolyDP ε=1) → 23 MB. Round-trips via load_project, 0 missing images.
