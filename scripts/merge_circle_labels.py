"""Transplant circle (ROI) context labels into existing SERAPH ``.lab`` projects.

Background
----------
A pathologist drew a circular Region Of Interest ("ROI") over slides that were
*already* fully segmented in older projects. Every region inside that circle has
to gain a contextual label (``INV`` -> ``INV_C1``, ``ST`` -> ``ST_C1`` ...), so
we can later compare what is *inside* the circle versus *outside*. Re-segmenting
in a fresh project produced a second copy of those inner regions, which would
duplicate the dataset if naively joined.

This tool avoids the duplication entirely. Instead of merging two segmentation
copies, it merges only the *labels*: it reads the new "circle" JSON (which
carries the ROI annotation), lets the existing JSON reader assign the
``<class>_C<n>`` labels, and then **renames the matching tile that already
exists in the old ``.lab``** — matched by identical polygon geometry. The
segmentation (the nuclei) is never touched; only the tile's name changes.

Rules (as requested):
  * A region inside the circle  -> its existing tile is renamed to ``<class>_C<n>``.
  * A region that does not match any existing tile -> ignored (reported).
  * The ``ROI`` circle itself     -> NEVER added as a tile/tag; it is only a
    geometric demarcation used to decide inside/outside.

The ``.lab`` is plain JSON (a list of session items, each with ``tiles``; every
tile has ``metadata.name``, ``polygon`` and ``rects``), so we edit it directly
without loading any image.

Usage
-----
Batch a whole folder (pairs ``NN_*.json`` with ``NN.lab`` by leading number)::

    python scripts/merge_circle_labels.py \
        --lab-dir  "E:/HR/ProjectFiles/LABFile/HRV1" \
        --json-dir "E:/HR/ProjectFiles/JSON/HR_Circle"

Single pair::

    python scripts/merge_circle_labels.py --lab "E:/.../11.lab" \
        --json "E:/.../11_HR JSON circle.json"

By default the result is written next to the original as ``NN_circle.lab`` (the
original is left untouched, and the relative image paths stay valid because the
output lives in the same folder). Use ``--in-place`` to overwrite, or
``--dry-run`` to only report what would change.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
import tempfile
from pathlib import Path

# Make the repository root importable so ``app.*`` resolves when run directly.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.infrastructure.tile_json import read_json_features  # noqa: E402

logger = logging.getLogger("merge_circle_labels")

# Matches the circle-context suffix produced by tile_json._label_regions_inside_roi,
# e.g. "INV_C1", "ST_C12". The capture group is unused; we only need the test.
_CIRCLE_SUFFIX_RE = re.compile(r"_C\d+$")
# Leading slide number in a filename: "11_HR JSON circle.json" -> 11, "03.lab" -> 3.
_LEADING_NUM_RE = re.compile(r"\s*0*(\d+)")


# ── Geometry helpers ────────────────────────────────────────────────────────
def _bbox_key(points) -> tuple[int, int, int, int]:
    """Integer bounding box using the SAME formula as the JSON/tile importers
    (``int(min)`` / ``ceil(max)``), so identical source coordinates yield an
    identical key on both sides."""
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return (
        int(min(xs)),
        int(min(ys)),
        int(math.ceil(max(xs))),
        int(math.ceil(max(ys))),
    )


def _norm_poly(points) -> tuple:
    """Rounded point tuple for exact tie-breaking between bbox collisions."""
    return tuple((int(round(float(p[0]))), int(round(float(p[1])))) for p in points)


def _rects_to_poly(rects):
    if not rects:
        return None
    x1 = min(r[0] for r in rects)
    y1 = min(r[1] for r in rects)
    x2 = max(r[2] for r in rects)
    y2 = max(r[3] for r in rects)
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


# ── Core logic ──────────────────────────────────────────────────────────────
def circle_labeled_regions(json_path) -> list[dict]:
    """Read a circle JSON and return one dict per region the importer placed
    inside a ``ROI`` (i.e. whose name gained ``_C<n>``).

    Each dict carries ``name`` (the ``<class>_C<n>`` label), ``polygon`` and
    ``rects``. The ``ROI`` container itself is excluded — it is only a
    demarcation, never a tag.
    """
    descriptors = read_json_features(str(json_path))
    regions: list[dict] = []
    for desc in descriptors:
        sl = desc.get("slice", {})
        name = (sl.get("name") or "").strip()
        polygon = sl.get("polygon")
        if not polygon:
            continue
        if name.lower() == "roi":
            continue  # the circle itself is never a tag
        if not _CIRCLE_SUFFIX_RE.search(name):
            continue  # outside every circle -> leave untouched
        regions.append({"name": name, "polygon": polygon, "rects": sl.get("rects")})
    return regions


def _build_tile_index(lab_data):
    """Return ``(exact, flat)`` where ``exact`` maps a tile's bbox key to a list
    of ``(item, tile)`` pairs, and ``flat`` is a list of ``(item, key)`` used to
    find the nearest existing tile (for attributing a newly-added region to the
    right session)."""
    exact: dict[tuple, list[tuple[dict, dict]]] = {}
    flat: list[tuple[dict, tuple]] = []
    for item in lab_data:
        for tile in item.get("tiles", []):
            pts = tile.get("polygon") or _rects_to_poly(tile.get("rects"))
            if not pts:
                continue
            key = _bbox_key(pts)
            exact.setdefault(key, []).append((item, tile))
            flat.append((item, key))
    return exact, flat


def _pick_tile(candidates: list[tuple[dict, dict]], polygon):
    """Choose the ``(item, tile)`` matching ``polygon`` among bbox collisions."""
    if len(candidates) == 1:
        return candidates[0]
    want = _norm_poly(polygon)
    hits = [(it, t) for (it, t) in candidates
            if t.get("polygon") and _norm_poly(t["polygon"]) == want]
    if len(hits) == 1:
        return hits[0]
    return None  # ambiguous — refuse to guess


def _region_to_tile(region: dict) -> dict:
    """Build a fresh .lab tile dict (region outline only, no segmentation) for a
    new inside-circle region. Mirrors ``Tile.serialize()`` so the app loads it."""
    polygon = region["polygon"]
    rects = region.get("rects") or [list(_bbox_key(polygon))]
    label = region["name"]
    return {
        "rects": [list(r) for r in rects],
        "polygon": [[float(x), float(y)] for x, y in polygon],
        "exclusions": [],
        "pixel_mask": [],
        "color": "#00FFFF",
        "metadata": {
            "name": label,
            "description": f"New inside-circle region '{label}' (added from circle JSON)",
            "comment": "",
            "microns_per_pixel": "",
        },
        "segmentation_layers": [],
    }


def _nearest_item(flat, key):
    """Session item holding the existing tile nearest to ``key`` (by bbox center)."""
    if not flat:
        return None
    cx, cy = (key[0] + key[2]) / 2, (key[1] + key[3]) / 2
    best_item, best_d = None, None
    for item, k in flat:
        d = ((k[0] + k[2]) / 2 - cx) ** 2 + ((k[1] + k[3]) / 2 - cy) ** 2
        if best_d is None or d < best_d:
            best_item, best_d = item, d
    return best_item


def merge_labels_into_lab(lab_data, regions) -> dict:
    """Apply circle-context labels to ``lab_data`` in place.

    * Region matches an existing tile -> rename that tile to ``<class>_C<n>``.
    * Region matches nothing (a NEW region the pathologist drew inside the
      circle) -> append it as a new region tile carrying the same label
      (segmentation is not in the circle JSON, so the new tile has no nuclei).

    Returns a stats dict: renamed / already / added / ambiguous (+ samples).
    """
    exact, flat = _build_tile_index(lab_data)
    stats = {"renamed": 0, "already": 0, "added": 0, "ambiguous": 0, "samples": []}

    for region in regions:
        label, polygon = region["name"], region["polygon"]
        key = _bbox_key(polygon)
        candidates = exact.get(key, [])

        if candidates:
            picked = _pick_tile(candidates, polygon)
            if picked is None:
                stats["ambiguous"] += 1
                continue
            _item, tile = picked
            meta = tile.setdefault("metadata", {})
            current = (meta.get("name") or "").strip()
            if current == label:
                stats["already"] += 1
                continue
            meta["name"] = label
            meta["description"] = f"Circle-labeled region '{label}' (was '{current}')"
            stats["renamed"] += 1
            if len(stats["samples"]) < 8:
                stats["samples"].append(f"{current or '<empty>'} -> {label}")
            continue

        # No match -> new region drawn inside the circle: add it as a new tile.
        target_item = _nearest_item(flat, key) or (lab_data[0] if lab_data else None)
        if target_item is None:
            stats["ambiguous"] += 1  # nowhere to put it (empty project)
            continue
        new_tile = _region_to_tile(region)
        target_item.setdefault("tiles", []).append(new_tile)
        # Keep the index live so a duplicate region in the same run is seen.
        exact.setdefault(key, []).append((target_item, new_tile))
        flat.append((target_item, key))
        stats["added"] += 1
        if len(stats["samples"]) < 8:
            stats["samples"].append(f"+new {label}")

    return stats


# ── File / batch orchestration ──────────────────────────────────────────────
def _leading_number(name: str) -> int | None:
    m = _LEADING_NUM_RE.match(os.path.basename(name))
    return int(m.group(1)) if m else None


def process_pair(lab_path: Path, json_path: Path, *, suffix: str, in_place: bool,
                 dry_run: bool, indent) -> dict:
    logger.info("Reading circle JSON: %s", json_path.name)
    regions = circle_labeled_regions(json_path)
    logger.info("  %d inside-circle region(s) to apply.", len(regions))

    logger.info("Loading .lab (%.1f MB): %s",
                lab_path.stat().st_size / 1e6, lab_path.name)
    with open(lab_path, "r", encoding="utf-8") as fh:
        lab_data = json.load(fh)

    stats = merge_labels_into_lab(lab_data, regions)
    logger.info("  renamed=%d added=%d already=%d ambiguous=%d",
                stats["renamed"], stats["added"], stats["already"], stats["ambiguous"])
    if stats["samples"]:
        logger.info("  e.g. %s", "; ".join(stats["samples"]))

    if dry_run:
        logger.info("  [dry-run] not writing.")
        return stats
    if stats["renamed"] == 0 and stats["added"] == 0:
        logger.info("  nothing to write (0 changes).")
        return stats

    out_path = lab_path if in_place else lab_path.with_name(f"{lab_path.stem}{suffix}.lab")
    # Write to a temp file in the same directory, then atomically replace.
    fd, tmp = tempfile.mkstemp(dir=str(out_path.parent), suffix=".lab.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(lab_data, fh, indent=indent)
        os.replace(tmp, out_path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    logger.info("  wrote -> %s", out_path)
    return stats


def _pair_dirs(lab_dir: Path, json_dir: Path) -> list[tuple[Path, Path]]:
    labs = {}
    for p in lab_dir.glob("*.lab"):
        n = _leading_number(p.stem)
        if n is not None:
            labs[n] = p
    jsons = {}
    for p in json_dir.glob("*.json"):
        n = _leading_number(p.name)
        if n is not None:
            jsons[n] = p

    pairs: list[tuple[Path, Path]] = []
    for n in sorted(jsons):
        if n in labs:
            pairs.append((labs[n], jsons[n]))
        else:
            logger.warning("JSON #%d (%s) has no matching .lab — skipped.", n, jsons[n].name)
    for n in sorted(labs):
        if n not in jsons:
            logger.warning(".lab #%d (%s) has no matching JSON — skipped.", n, labs[n].name)
    return pairs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply circle (ROI) context labels to SERAPH .lab projects.")
    ap.add_argument("--lab", help="Single .lab file.")
    ap.add_argument("--json", help="Single circle JSON file.")
    ap.add_argument("--lab-dir", help="Folder of .lab files (batch mode).")
    ap.add_argument("--json-dir", help="Folder of circle JSON files (batch mode).")
    ap.add_argument("--suffix", default="_circle",
                    help="Suffix for output .lab when not in-place (default: _circle).")
    ap.add_argument("--in-place", action="store_true", help="Overwrite the original .lab.")
    ap.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
    ap.add_argument("--indent", type=int, default=None,
                    help="JSON indent for output (default: compact — smaller/faster for big files).")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.lab_dir or args.json_dir:
        if not (args.lab_dir and args.json_dir):
            ap.error("--lab-dir and --json-dir must be used together.")
        pairs = _pair_dirs(Path(args.lab_dir), Path(args.json_dir))
        if not pairs:
            logger.error("No matching .lab/JSON pairs found.")
            return 1
    elif args.lab and args.json:
        pairs = [(Path(args.lab), Path(args.json))]
    else:
        ap.error("provide either --lab-dir + --json-dir, or --lab + --json.")
        return 2

    totals = {"renamed": 0, "added": 0, "already": 0, "ambiguous": 0}
    logger.info("Processing %d pair(s)%s\n", len(pairs), "  [DRY-RUN]" if args.dry_run else "")
    for lab_path, json_path in pairs:
        logger.info("── #%s ──", _leading_number(lab_path.stem))
        try:
            stats = process_pair(lab_path, json_path, suffix=args.suffix,
                                  in_place=args.in_place, dry_run=args.dry_run,
                                  indent=args.indent)
        except Exception as exc:  # keep the batch going
            logger.error("  FAILED %s: %s", lab_path.name, exc)
            continue
        for k in totals:
            totals[k] += stats.get(k, 0)
        logger.info("")

    logger.info("Done. renamed=%d added=%d already=%d ambiguous=%d",
                totals["renamed"], totals["added"], totals["already"], totals["ambiguous"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
