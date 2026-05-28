import csv
import json
import logging
import os
from PIL import Image, ImageDraw

from app.domain.selection import rect_to_cells, draw_exclusion_rects
from app.infrastructure.io import save_image_tile
from app.infrastructure.tile_xml import write_tile_xml, build_tile_descriptor

logger = logging.getLogger(__name__)

class ExportService:
    def _get_export_filename(self, image_name, row, col, format_ext):
        base = os.path.splitext(image_name)[0]
        return f"{base}_row{row}_col{col}{format_ext}"

    def save_selected_cells(self, session, output_dir, format_ext, progress_callback=None):
        """Saves selected regions, one file per slice group."""
        if not session or not output_dir: return 0

        count = 0
        total = len(session.tiles)
        base = os.path.splitext(session.name)[0]
        for i, tile in enumerate(session.tiles):
            # Bounding box of this slice
            bx1, by1, bx2, by2 = tile.bounding_box

            w, h = bx2 - bx1, by2 - by1
            if w <= 0 or h <= 0:
                continue
                
            # Always use RGBA internally so we can apply polygon mask
            out_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

            for (rx1, ry1, rx2, ry2) in tile.rects:
                crop = session.pyramid.get_region_fullres(rx1, ry1, rx2 - rx1, ry2 - ry1)
                crop = crop.convert("RGBA")
                out_img.paste(crop, (rx1 - bx1, ry1 - by1))

            # By default, a mask is fully opaque (255) meaning keep all pixels
            mask = Image.new("L", (w, h), 255)
            poly = tile.polygon
            
            # Apply freehand polygon mask if this is a brush slice
            if poly and len(poly) >= 3:
                # If there's a polygon, invert mask to fully transparent (0) then paint the polygon opaque (255)
                mask.paste(0, (0, 0, w, h))
                draw = ImageDraw.Draw(mask)
                local_pts = [(x - bx1, y - by1) for (x, y) in poly]
                draw.polygon(local_pts, fill=255)
                
            # Apply exclusion strokes (eraser brush holes) regardless of polygon
            exclusions = tile.exclusions
            if exclusions:
                draw = ImageDraw.Draw(mask)
                draw_exclusion_rects(draw, exclusions, bx1, by1, 1.0)

            # Apply per-pixel mask (individual pixels toggled in the Pixel Editor)
            pixel_mask = tile.pixel_mask
            if pixel_mask:
                draw = ImageDraw.Draw(mask)
                for (px, py) in pixel_mask:
                    lx, ly = px - bx1, py - by1
                    if 0 <= lx < w and 0 <= ly < h:
                        draw.point((lx, ly), fill=0)
            
            # Apply the mask to the alpha channel to create transparency
            out_img.putalpha(mask)

            # Tight crop to the polygon boundaries so we don't output full grid squares
            if poly and len(poly) >= 3:
                l_x1 = min(p[0] - bx1 for p in poly)
                l_y1 = min(p[1] - by1 for p in poly)
                l_x2 = max(p[0] - bx1 for p in poly)
                l_y2 = max(p[1] - by1 for p in poly)
                out_img = out_img.crop((int(l_x1), int(l_y1), int(l_x2), int(l_y2)))

            # Flatten to white background for non-transparent output formats like JPEG
            if format_ext not in ('.png', '.webp', '.tiff', '.tif'):
                bg = Image.new("RGB", (w, h), (255, 255, 255))
                # Paste the cutout image on top of the solid white background using its alpha channel as the paste mask
                bg.paste(out_img, mask=out_img.split()[3])
                out_img = bg

            filename = f"{base}_slice{i + 1}{format_ext}"
            full_path = os.path.join(output_dir, filename)
            if save_image_tile(out_img, full_path, format_ext):
                count += 1
                # Write companion XML tile descriptor
                try:
                    descriptor = build_tile_descriptor(session, i, output_dir)
                    xml_path = os.path.join(
                        output_dir, f"{base}_slice{i + 1}_tile.xml"
                    )
                    write_tile_xml(xml_path, descriptor)
                except Exception as xml_exc:
                    logger.warning("Could not write tile XML for slice %d: %s", i, xml_exc)
            if progress_callback:
                progress_callback(i + 1, total)
        return count

    def slice_all(self, session, output_dir, format_ext, progress_callback=None):
        """Slices the entire image into grid tiles."""
        if not session or not output_dir: return 0
        
        cols = (session.real_width + session.grid_w - 1) // session.grid_w
        rows = (session.real_height + session.grid_h - 1) // session.grid_h
        total = cols * rows
        
        count = 0
        for row in range(rows):
            for col in range(cols):
                x1 = col * session.grid_w
                y1 = row * session.grid_h
                x2 = min(x1 + session.grid_w, session.real_width)
                y2 = min(y1 + session.grid_h, session.real_height)
                
                filename = self._get_export_filename(session.name, row, col, format_ext)
                full_path = os.path.join(output_dir, filename)
                
                # Use pyramid for streaming full-res crop (no full image in RAM)
                tile = session.pyramid.get_region_fullres(x1, y1, x2 - x1, y2 - y1)
                if save_image_tile(tile, full_path, format_ext):
                    count += 1
                if progress_callback:
                    progress_callback(count, total)
        return count

    def export_metadata(self, session, output_dir):
        """Export tile metadata as CSV and JSON alongside the tiles."""
        base = os.path.splitext(session.name)[0]
        rows = []

        for i, tile in enumerate(session.tiles):
            bx1, by1, bx2, by2 = tile.bounding_box
            w_px, h_px = bx2 - bx1, by2 - by1
            if w_px <= 0 or h_px <= 0:
                continue

            meta = tile.metadata
            mpp_str = meta.get("microns_per_pixel", "")
            try:
                mpp = float(mpp_str) if mpp_str else None
            except (ValueError, TypeError):
                mpp = None

            phys_w = f"{w_px * mpp:.1f} µm" if mpp else ""
            phys_h = f"{h_px * mpp:.1f} µm" if mpp else ""

            rows.append({
                "index": i + 1,
                "name": meta.get("name", f"Tile {i+1}"),
                "x1": bx1, "y1": by1, "x2": bx2, "y2": by2,
                "width_px": w_px, "height_px": h_px,
                "microns_per_pixel": mpp_str,
                "physical_width": phys_w,
                "physical_height": phys_h,
                "description": meta.get("description", ""),
                "source": session.name,
            })

        # CSV
        csv_path = os.path.join(output_dir, f"{base}_metadata.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

        # JSON
        json_path = os.path.join(output_dir, f"{base}_metadata.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)

    def export_nuclei_from_slice(self, session, tile_idx, output_dir, format_ext=".png", selected_layer="All Segmentations"):
        """
        Extracts and exports all nuclei inside a specific slice as individual image files,
        organized in a folder named after the slice's name.
        """
        from app.application.nuclei_extraction_service import NucleiExtractionService
        
        extractor = NucleiExtractionService()
        nuclei_data = extractor.extract_nuclei_from_tile(session, tile_idx, selected_layer)
        
        if not nuclei_data:
            return 0
            
        tile = session.tiles[tile_idx]
        slice_name = tile.metadata.get("name", f"slice{tile_idx + 1}")
        
        # Clean up slice_name to avoid invalid characters in folder names
        safe_slice_name = "".join(c for c in slice_name if c.isalnum() or c in " _-()").strip()
        if not safe_slice_name:
            safe_slice_name = f"slice{tile_idx + 1}"
            
        # Handle duplicates: ex. INV, INV(1), INV(2)
        target_dir = os.path.join(output_dir, safe_slice_name)
        counter = 1
        while os.path.exists(target_dir):
            target_dir = os.path.join(output_dir, f"{safe_slice_name}({counter})")
            counter += 1
            
        os.makedirs(target_dir, exist_ok=True)
        
        count = 0
        base = os.path.splitext(session.name)[0]
        for img, meta in nuclei_data:
            nucleus_id = meta["nucleus_id"]
            
            # Use format_ext or default to .png to support transparency
            if format_ext not in ('.png', '.webp', '.tiff', '.tif'):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                # Paste the cutout image on top of the solid white background 
                bg.paste(img, mask=img.split()[3])
                img = bg
                
            filename = f"nucleus_{nucleus_id}{format_ext}"
            full_path = os.path.join(target_dir, filename)
            
            if save_image_tile(img, full_path, format_ext):
                count += 1
                
        return count

    def export_probability_maps(
        self,
        session,
        output_dir,
        selected_layer="All Segmentations",
        tile_indices=None,
        progress_callback=None,
    ):
        """
        Export raw probability maps captured during segmentation as float32 TIFFs.

        This intentionally does not fall back to polygon-derived binary masks:
        if a layer does not carry a raw ``probability_map`` value, it is skipped.
        """
        if not session or not output_dir:
            return 0

        os.makedirs(output_dir, exist_ok=True)

        if tile_indices is None:
            tile_indices = range(len(session.tiles))

        tile_indices = list(tile_indices)
        total = len(tile_indices)
        count = 0
        base = os.path.splitext(session.name)[0]
        safe_layer = self._safe_filename(selected_layer)

        for progress_idx, tile_idx in enumerate(tile_indices, start=1):
            if tile_idx is None or tile_idx < 0 or tile_idx >= len(session.tiles):
                continue

            tile = session.tiles[tile_idx]
            bx1, by1, bx2, by2 = tile.bounding_box
            width, height = bx2 - bx1, by2 - by1
            if width <= 0 or height <= 0:
                continue

            real_prob = self._collect_real_probability_map(tile, selected_layer)
            logger.info(
                "export_probability_maps tile %d: real_prob=%s stats=%s",
                tile_idx,
                None if real_prob is None else real_prob.shape,
                None if real_prob is None else self._probability_map_stats(real_prob),
            )

            if real_prob is not None:
                filename = f"{base}_slice{tile_idx + 1}_{safe_layer}_raw_probability_map.tiff"
                full_path = os.path.join(output_dir, filename)
                try:
                    Image.fromarray(real_prob, mode="F").save(
                        full_path, format="TIFF", compression="raw"
                    )
                    count += 1
                except Exception as exc:
                    logger.error("Error saving probability map '%s': %s", full_path, exc)

            if progress_callback:
                progress_callback(progress_idx, total)

        return count

    @staticmethod
    def _collect_layer_polygons(tile, selected_layer):
        polygons = []
        for layer in tile.segmentation_layers:
            if selected_layer != "All Segmentations" and layer.get("name") != selected_layer:
                continue
            for polygon in layer.get("polygons", []):
                if polygon and len(polygon) >= 3:
                    polygons.append(polygon)
        return polygons

    @staticmethod
    def _collect_real_probability_map(tile, selected_layer):
        """Return a float32 H×W array merged from any layers that carry a real probability map.

        When multiple layers qualify (All Segmentations mode), their maps are combined
        via pixel-wise maximum so the result reflects the highest confidence from any model.
        Returns None if no layer has a real probability map.
        """
        import numpy as np
        canvas = None
        for layer in tile.segmentation_layers:
            if selected_layer != "All Segmentations" and layer.get("name") != selected_layer:
                continue
            pm = layer.get("probability_map")
            if pm is None:
                continue
            arr = np.asarray(pm, dtype=np.float32)
            if canvas is None:
                canvas = arr.copy()
            elif arr.shape == canvas.shape:
                np.maximum(canvas, arr, out=canvas)
        return canvas

    @staticmethod
    def _probability_map_stats(prob_map):
        import numpy as np

        arr = np.asarray(prob_map, dtype=np.float32)
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return "empty/non-finite"
        q = np.quantile(finite, [0.01, 0.5, 0.99])
        near_binary = float(np.mean((finite <= 1e-6) | (finite >= 1.0 - 1e-6))) * 100.0
        return (
            f"min={float(finite.min()):.6f}, p01={float(q[0]):.6f}, "
            f"p50={float(q[1]):.6f}, p99={float(q[2]):.6f}, "
            f"max={float(finite.max()):.6f}, near_binary={near_binary:.2f}%"
        )

    @staticmethod
    def _safe_filename(value):
        value = str(value or "unknown")
        safe = "".join(c for c in value if c.isalnum() or c in " _-()").strip()
        return safe.replace(" ", "_") or "unknown"

    def export_nuclei_to_h5(self, session, output_filepath, selected_layer="All Segmentations", patient_label=0, progress_callback=None):
        """
        Exports all nuclei to HDF5.

        Schema (confirmed with Shifat):
          images         (N,300,300,3) uint8
          masks          (N,300,300)   uint8
          patient_ids    (N,)          int32   — numeric from filename
          patient_labels (N,)          str     — 'LR' or 'HR'
          slide_ids      (N,)          str     — filename without extension
          roi_ids        (N,)          int32   — unique sequential ID per nucleus
          roi_labels     (N,)          str     — ROI name ('INV', 'M', 'N', ...)
          pixel_size_um  (1,)          float64
          roi_dimension  (N,4)         float64 — cx, cy, w, h in global pixels

        Fast path  — allocates all pixel arrays in RAM, writes in one shot.
        Stream path — automatic fallback when RAM is insufficient (~1 MB constant).
        """
        import re
        import h5py
        import numpy as np
        from app.application.nuclei_extraction_service import NucleiExtractionService

        base_name = os.path.splitext(session.name)[0]
        m = re.search(r'\d+', base_name)
        patient_id    = int(m.group()) if m else 0
        slide_id_str  = base_name
        patient_lbl_str = 'HR' if patient_label == 1 else 'LR'

        # Count total nuclei without pixel extraction (cheap).
        # Apply the image-edge filter here so the pre-allocated HDF5 dataset
        # size is accurate: nuclei cut by the image border are excluded.
        _img_w = session.real_width
        _img_h = session.real_height
        N = 0
        for tile in session.tiles:
            for layer in tile.segmentation_layers:
                if selected_layer != "All Segmentations" and layer.get("name") != selected_layer:
                    continue
                for p in layer.get("polygons", []):
                    if not p or len(p) < 3:
                        continue
                    px_min = min(v[0] for v in p)
                    py_min = min(v[1] for v in p)
                    px_max = max(v[0] for v in p)
                    py_max = max(v[1] for v in p)
                    if px_min <= 0 or py_min <= 0 or px_max >= _img_w - 1 or py_max >= _img_h - 1:
                        continue
                    N += 1

        if N == 0:
            return 0

        CANVAS = 300

        mpp = 1.0
        mpp_str = getattr(session, "microns_per_pixel", "") or (
            session.tiles[0].metadata.get("microns_per_pixel", "") if session.tiles else ""
        )
        try:
            mpp = float(mpp_str) if mpp_str else 1.0
        except (ValueError, TypeError):
            mpp = 1.0

        str_dt    = h5py.string_dtype()
        extractor = NucleiExtractionService()

        def _process_nucleus(img):
            w, h = img.size
            if w > CANVAS or h > CANVAS:
                ratio = min(CANVAS / w, CANVAS / h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
                w, h = img.size
            ox, oy = (CANVAS - w) // 2, (CANVAS - h) // 2
            padded_img = Image.new("RGB", (CANVAS, CANVAS), (0, 0, 0))
            padded_img.paste(img, (ox, oy), mask=img.split()[3])
            padded_msk = Image.new("L", (CANVAS, CANVAS), 0)
            padded_msk.paste(img.split()[3], (ox, oy))
            return np.array(padded_img), np.array(padded_msk)

        # ── Probe RAM ────────────────────────────────────────────────────────
        try:
            images    = np.zeros((N, CANVAS, CANVAS, 3), dtype=np.uint8)
            masks     = np.zeros((N, CANVAS, CANVAS),    dtype=np.uint8)
            fast_path = True
        except MemoryError:
            fast_path = False
            logger.warning("RAM insuficiente para %d núcleos — usando modo streaming.", N)

        # ── FAST PATH ────────────────────────────────────────────────────────
        if fast_path:
            patient_ids  = np.full((N,), patient_id, dtype=np.int32)
            roi_ids      = np.zeros((N,), dtype=np.int32)
            roi_dim      = np.zeros((N, 4), dtype=np.float64)
            pat_lbl_arr  = np.array([patient_lbl_str] * N, dtype=object)
            slide_id_arr = np.array([slide_id_str]    * N, dtype=object)
            roi_lbl_arr  = np.array([""] * N, dtype=object)

            idx = 0
            for tile_idx in range(len(session.tiles)):
                for img, meta in extractor.extract_nuclei_from_tile(session, tile_idx, selected_layer):
                    images[idx], masks[idx] = _process_nucleus(img)

                    gx1, gy1, gx2, gy2 = meta["global_bbox"]
                    rw, rh = gx2 - gx1, gy2 - gy1
                    roi_dim[idx] = [gx1 + rw / 2.0, gy1 + rh / 2.0, rw, rh]
                    roi_ids[idx]     = meta["tile_intersection"]
                    roi_lbl_arr[idx] = meta.get("roi_name", "")

                    idx += 1
                    if progress_callback:
                        progress_callback(idx, N)

            # Trim to actual count — quality filters may reject nuclei that the
            # polygon pre-count included, leaving trailing zeros/empties otherwise.
            images       = images[:idx]
            masks        = masks[:idx]
            patient_ids  = patient_ids[:idx]
            pat_lbl_arr  = pat_lbl_arr[:idx]
            slide_id_arr = slide_id_arr[:idx]
            roi_ids      = roi_ids[:idx]
            roi_lbl_arr  = roi_lbl_arr[:idx]
            roi_dim      = roi_dim[:idx]

            with h5py.File(output_filepath, 'w') as f:
                f.create_dataset('images',         data=images,
                                 chunks=(1, CANVAS, CANVAS, 3),
                                 compression='gzip', compression_opts=4)
                f.create_dataset('masks',          data=masks,
                                 chunks=(1, CANVAS, CANVAS),
                                 compression='gzip', compression_opts=4)
                f.create_dataset('patient_ids',    data=patient_ids)
                f.create_dataset('patient_labels', data=pat_lbl_arr,  dtype=str_dt)
                f.create_dataset('slide_ids',      data=slide_id_arr, dtype=str_dt)
                f.create_dataset('roi_ids',        data=roi_ids)
                f.create_dataset('roi_labels',     data=roi_lbl_arr,  dtype=str_dt)
                f.create_dataset('pixel_size_um',  data=np.array([mpp], dtype=np.float64))
                f.create_dataset('roi_dimension',  data=roi_dim)

        # ── STREAM PATH ──────────────────────────────────────────────────────
        else:
            buf_img  = np.zeros((CANVAS, CANVAS, 3), dtype=np.uint8)
            buf_mask = np.zeros((CANVAS, CANVAS),    dtype=np.uint8)

            with h5py.File(output_filepath, 'w') as f:
                # maxshape=(None,...) allows resize after the loop to trim trailing rows.
                ds_img  = f.create_dataset('images',  shape=(N, CANVAS, CANVAS, 3), dtype=np.uint8,
                                           chunks=(1, CANVAS, CANVAS, 3),
                                           maxshape=(None, CANVAS, CANVAS, 3),
                                           compression='gzip', compression_opts=4)
                ds_msk  = f.create_dataset('masks',   shape=(N, CANVAS, CANVAS),    dtype=np.uint8,
                                           chunks=(1, CANVAS, CANVAS),
                                           maxshape=(None, CANVAS, CANVAS),
                                           compression='gzip', compression_opts=4)
                ds_pid  = f.create_dataset('patient_ids',    shape=(N,), dtype=np.int32,  maxshape=(None,))
                ds_plbl = f.create_dataset('patient_labels', shape=(N,), dtype=str_dt,    maxshape=(None,))
                ds_sid  = f.create_dataset('slide_ids',      shape=(N,), dtype=str_dt,    maxshape=(None,))
                ds_rid  = f.create_dataset('roi_ids',        shape=(N,), dtype=np.int32,  maxshape=(None,))
                ds_rlbl = f.create_dataset('roi_labels',     shape=(N,), dtype=str_dt,    maxshape=(None,))
                ds_rdim = f.create_dataset('roi_dimension',  shape=(N, 4), dtype=np.float64, maxshape=(None, 4))
                f.create_dataset('pixel_size_um', data=np.array([mpp], dtype=np.float64))

                idx = 0
                for tile_idx in range(len(session.tiles)):
                    for img, meta in extractor.extract_nuclei_from_tile(session, tile_idx, selected_layer):
                        buf_img[:], buf_mask[:] = _process_nucleus(img)
                        ds_img[idx] = buf_img
                        ds_msk[idx] = buf_mask

                        gx1, gy1, gx2, gy2 = meta["global_bbox"]
                        rw, rh = gx2 - gx1, gy2 - gy1
                        ds_rdim[idx] = [gx1 + rw / 2.0, gy1 + rh / 2.0, rw, rh]

                        ds_pid[idx]  = patient_id
                        ds_plbl[idx] = patient_lbl_str
                        ds_sid[idx]  = slide_id_str
                        ds_rid[idx]  = meta["tile_intersection"]
                        ds_rlbl[idx] = meta.get("roi_name", "")

                        idx += 1
                        if progress_callback:
                            progress_callback(idx, N)

                # Trim datasets to exact count if quality filters rejected any nuclei.
                if idx < N:
                    for ds in (ds_img, ds_msk, ds_pid, ds_plbl, ds_sid, ds_rid, ds_rlbl):
                        ds.resize((idx,) + ds.shape[1:])
                    ds_rdim.resize((idx, 4))

        return idx
