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
                mask.paste(0, [0, 0, w, h])
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
