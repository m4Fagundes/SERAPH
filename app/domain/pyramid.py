"""
On-demand image region reader for ultra-large images (200k×200k+).

Two backends:
  - pyvips: for standard formats (TIFF, PNG, JPEG, BMP, WebP).
    Uses lazy random-access — only the requested pixels are decoded.
  - OpenSlide: for whole-slide formats (.ndpi, .svs, .mrxs, etc.).
    Uses the built-in multi-resolution pyramid already inside the file.

NO pre-build step is needed. Images open instantly regardless of size.
"""

import os
import math
from PIL import Image

# Disable PIL decompression bomb limit for ultra-large images
Image.MAX_IMAGE_PIXELS = None

try:
    import pyvips
except Exception:
    pyvips = None

try:
    import openslide
except Exception:
    openslide = None

# File extensions handled by OpenSlide
OPENSLIDE_EXTENSIONS = {
    '.ndpi', '.svs', '.mrxs', '.vms', '.vmu', '.scn',
    '.bif', '.svslide',
}


class ImagePyramid:
    """On-demand image reader with 3-tier zoom quality.

    Opens instantly — no pyramid build step.  Reads only the pixels
    needed for each viewport frame.

    Quality tiers:
      zoom < 50%   → Lossy:    read from a smaller resolution level
                                (OpenSlide built-in level, or pyvips shrink)
      50% ≤ zoom < 94% → Lossless: crop from original, resize via
                                    pyvips/Lanczos to screen size
      zoom ≥ 94%   → Full-res: pixel-perfect original data
    """

    TIER_LOSSLESS = 0.50   # below this → lossy (lower-res level)
    TIER_FULLRES  = 0.94   # above this → pixel-perfect original

    def __init__(self, image_path: str):
        """Open an image lazily — no pixel data loaded into RAM."""
        self._pil_image_fallback = None

        self.image_path = os.path.abspath(image_path)
        ext = os.path.splitext(self.image_path)[1].lower()

        self._is_openslide = ext in OPENSLIDE_EXTENSIONS
        self._openslide = None
        self._vips_image = None
        self._os_levels = []     # [(w, h, downsample), ...] for OpenSlide
        self._os_level_count = 0

        if self._is_openslide:
            if openslide is None:
                raise ImportError(
                    f"{ext} files require openslide-python. "
                    "Install with: pip install openslide-bin openslide-python"
                )
            self._openslide = openslide.OpenSlide(self.image_path)
            self.image_width, self.image_height = self._openslide.dimensions
            self.bands = 3

            # Cache the level info from the slide
            self._os_level_count = self._openslide.level_count
            for i in range(self._os_level_count):
                w, h = self._openslide.level_dimensions[i]
                ds = self._openslide.level_downsamples[i]
                self._os_levels.append((w, h, ds))

            # Also try pyvips for potential use
            try:
                self._vips_image = pyvips.Image.new_from_file(
                    self.image_path, access="random"
                )
            except Exception:
                pass
        else:
            if pyvips is not None:
                self._vips_image = pyvips.Image.new_from_file(
                    self.image_path, access="random"
                )
                self.image_width = self._vips_image.width
                self.image_height = self._vips_image.height
                self.bands = self._vips_image.bands
            else:
                self._pil_image_fallback = Image.open(self.image_path)
                self.image_width = self._pil_image_fallback.width
                self.image_height = self._pil_image_fallback.height
                self.bands = len(self._pil_image_fallback.getbands())

        # Always ready — no build step needed
        self.is_ready = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tile(self, col: int, row: int, zoom: float, tile_size: int = 256):
        """Return a single square tile of dimension `tile_size` at the given grid coordinates.
        This provides the backend for OpenSeadragon-style progressive deep zooming.
        """
        # Calculate full-res coordinates for this tile
        cam_x = (col * tile_size) / zoom
        cam_y = (row * tile_size) / zoom
        
        # Out of bounds check
        from PIL import Image
        if cam_x >= self.image_width or cam_y >= self.image_height:
             return Image.new("RGB", (tile_size, tile_size), (20, 20, 20))
             
        try:
            if zoom >= self.TIER_FULLRES:
                return self._viewport_fullres(cam_x, cam_y, tile_size, tile_size, zoom)
            elif zoom >= self.TIER_LOSSLESS:
                return self._viewport_lossless(cam_x, cam_y, tile_size, tile_size, zoom)
            else:
                return self._viewport_lossy(cam_x, cam_y, tile_size, tile_size, zoom)
        except Exception:
            return Image.new("RGB", (tile_size, tile_size), (20, 20, 20))

    def get_viewport(self, cam_x, cam_y, vp_w, vp_h, zoom):
        """Return a PIL Image for the current viewport.

        Args:
            cam_x, cam_y: top-left in full-res image coords.
            vp_w, vp_h:   viewport size in screen pixels.
            zoom:          zoom factor (1.0 = 100%).
        """
        if vp_w < 1 or vp_h < 1:
            return Image.new("RGB", (max(1, vp_w), max(1, vp_h)), (20, 20, 20))

        try:
            if zoom >= self.TIER_FULLRES:
                return self._viewport_fullres(cam_x, cam_y, vp_w, vp_h, zoom)
            elif zoom >= self.TIER_LOSSLESS:
                return self._viewport_lossless(cam_x, cam_y, vp_w, vp_h, zoom)
            else:
                return self._viewport_lossy(cam_x, cam_y, vp_w, vp_h, zoom)
        except Exception:
            return Image.new("RGB", (vp_w, vp_h), (20, 20, 20))

    def get_region_fullres(self, x, y, w, h):
        """Crop a full-resolution region (for export). Streaming, low RAM."""
        x, y = max(0, int(x)), max(0, int(y))
        w = min(int(w), self.image_width - x)
        h = min(int(h), self.image_height - y)
        if w <= 0 or h <= 0:
            return Image.new("RGB", (1, 1))

        return self._read_region(x, y, w, h)

    def get_thumbnail(self, max_size=256):
        """Small thumbnail for sidebar. Very fast."""
        if self._openslide is not None:
            return self._openslide.get_thumbnail(
                (max_size, max_size)
            ).convert("RGB")
        elif self._vips_image is not None:
            thumb = self._vips_image.thumbnail_image(
                max_size, height=max_size, size="down"
            )
            return self._vips_to_pil(thumb)
        elif self._pil_image_fallback is not None:
            thumb = self._pil_image_fallback.copy()
            thumb.thumbnail((max_size, max_size))
            return thumb.convert("RGB")
        return Image.new("RGB", (max_size, max_size), (20, 20, 20))

    def unload(self) -> None:
        """Release all file handles and pixel buffers.

        Frees RAM / file descriptors when this image is not the active
        session.  Dimensions are preserved so the session still knows
        its real_width / real_height without re-opening the file.
        After calling this, get_viewport() will raise AttributeError —
        call the owning ImageSession.reload() before rendering again.
        """
        if self._openslide is not None:
            try:
                self._openslide.close()
            except Exception:
                pass
            self._openslide = None

        self._vips_image = None
        self._pil_image_fallback = None
        self.is_ready = False

    # ------------------------------------------------------------------
    # Tier 3: zoom ≥ 94% — pixel-perfect
    # ------------------------------------------------------------------

    def _viewport_fullres(self, cam_x, cam_y, vp_w, vp_h, zoom):
        result = Image.new("RGB", (vp_w, vp_h), (20, 20, 20))

        vr = cam_x + vp_w / zoom
        vb = cam_y + vp_h / zoom

        cl = max(0, int(cam_x))
        ct = max(0, int(cam_y))
        cr = min(self.image_width, int(math.ceil(vr)))
        cb = min(self.image_height, int(math.ceil(vb)))
        if cr <= cl or cb <= ct:
            return result

        crop = self._read_region(cl, ct, cr - cl, cb - ct)

        sw = max(1, int(round((cr - cl) * zoom)))
        sh = max(1, int(round((cb - ct) * zoom)))
        if sw != crop.width or sh != crop.height:
            resample = Image.Resampling.NEAREST if zoom > 2.0 else Image.Resampling.LANCZOS
            crop = crop.resize((sw, sh), resample)

        result.paste(crop, (int(round((cl - cam_x) * zoom)),
                            int(round((ct - cam_y) * zoom))))
        return result

    # ------------------------------------------------------------------
    # Tier 2: 50–94% — lossless crop + resize
    # ------------------------------------------------------------------

    def _viewport_lossless(self, cam_x, cam_y, vp_w, vp_h, zoom):
        result = Image.new("RGB", (vp_w, vp_h), (20, 20, 20))

        vr = cam_x + vp_w / zoom
        vb = cam_y + vp_h / zoom

        cl = max(0, int(cam_x))
        ct = max(0, int(cam_y))
        cr = min(self.image_width, int(math.ceil(vr)))
        cb = min(self.image_height, int(math.ceil(vb)))
        if cr <= cl or cb <= ct:
            return result

        cw, ch = cr - cl, cb - ct
        sw = max(1, int(round(cw * zoom)))
        sh = max(1, int(round(ch * zoom)))

        # For slides (NDPI etc.), always use OpenSlide — pyvips reads the
        # TIFF wrapper incorrectly and returns black pixels.
        # For standard images, use pyvips resize pipeline for efficiency.
        if self._is_openslide and self._openslide is not None:
            crop = self._openslide.read_region((cl, ct), 0, (cw, ch)).convert("RGB")
            if sw < crop.width or sh < crop.height:
                crop = crop.resize((sw, sh), Image.Resampling.LANCZOS)
        elif self._vips_image is not None:
            region = self._vips_image.crop(cl, ct, cw, ch)
            if sw < cw or sh < ch:
                region = region.resize(
                    sw / cw, vscale=sh / ch, kernel="lanczos3"
                )
            crop = self._vips_to_pil(region)
        elif self._pil_image_fallback is not None:
            region = self._pil_image_fallback.crop((cl, ct, cl + cw, ct + ch))
            if sw < cw or sh < ch:
                region = region.resize((sw, sh), Image.Resampling.LANCZOS)
            crop = region.convert("RGB")
        else:
            crop = Image.new("RGB", (sw, sh), (20, 20, 20))

        if crop.width != sw or crop.height != sh:
            crop = crop.resize((sw, sh), Image.Resampling.LANCZOS)

        result.paste(crop, (int(round((cl - cam_x) * zoom)),
                            int(round((ct - cam_y) * zoom))))
        return result

    # ------------------------------------------------------------------
    # Tier 1: zoom < 50% — read from lower-resolution level
    # ------------------------------------------------------------------

    def _viewport_lossy(self, cam_x, cam_y, vp_w, vp_h, zoom):
        """Read from a lower-resolution level for speed."""
        result = Image.new("RGB", (vp_w, vp_h), (20, 20, 20))

        vr = cam_x + vp_w / zoom
        vb = cam_y + vp_h / zoom

        if self._is_openslide and self._openslide is not None:
            return self._viewport_lossy_openslide(
                cam_x, cam_y, vp_w, vp_h, zoom, vr, vb, result
            )
        else:
            return self._viewport_lossy_fallback(
                cam_x, cam_y, vp_w, vp_h, zoom, vr, vb, result
            )

    def _viewport_lossy_openslide(self, cam_x, cam_y, vp_w, vp_h,
                                   zoom, vr, vb, result):
        """Use OpenSlide's built-in pyramid levels."""
        # Pick the best level: largest downsample that is ≤ 1/zoom
        target_ds = 1.0 / zoom
        best_level = 0
        for i, (lw, lh, ds) in enumerate(self._os_levels):
            if ds <= target_ds * 1.2:
                best_level = i

        lw, lh, ds = self._os_levels[best_level]

        # Region in level-0 coordinates (top-left)
        cl = max(0, int(cam_x))
        ct = max(0, int(cam_y))
        cr = min(self.image_width, int(math.ceil(vr)))
        cb = min(self.image_height, int(math.ceil(vb)))
        if cr <= cl or cb <= ct:
            return result

        # Size to read at this level
        read_w = max(1, int(math.ceil((cr - cl) / ds)))
        read_h = max(1, int(math.ceil((cb - ct) / ds)))

        # Clamp to level dimensions
        read_w = min(read_w, lw)
        read_h = min(read_h, lh)

        tile = self._openslide.read_region((cl, ct), best_level, (read_w, read_h))
        tile = tile.convert("RGB")

        # Scale to screen size
        sw = max(1, int(round((cr - cl) * zoom)))
        sh = max(1, int(round((cb - ct) * zoom)))
        if tile.width != sw or tile.height != sh:
            tile = tile.resize((sw, sh), Image.Resampling.BILINEAR)

        result.paste(tile, (int(round((cl - cam_x) * zoom)),
                            int(round((ct - cam_y) * zoom))))
        return result

    def _viewport_lossy_fallback(self, cam_x, cam_y, vp_w, vp_h,
                              zoom, vr, vb, result):
        """Use pyvips or PIL for lower zoom levels."""
        cl = max(0, int(cam_x))
        ct = max(0, int(cam_y))
        cr = min(self.image_width, int(math.ceil(vr)))
        cb = min(self.image_height, int(math.ceil(vb)))
        if cr <= cl or cb <= ct:
            return result

        cw, ch = cr - cl, cb - ct
        sw = max(1, int(round(cw * zoom)))
        sh = max(1, int(round(ch * zoom)))

        if self._vips_image is not None:
            factor = max(1, int(1.0 / zoom))
            if factor > 1:
                reduced = self._vips_image.reduce(factor, factor)
            else:
                reduced = self._vips_image

            rl = max(0, int(cl / factor))
            rt = max(0, int(ct / factor))
            rr = min(reduced.width, int(math.ceil(cr / factor)))
            rb = min(reduced.height, int(math.ceil(cb / factor)))

            if rr <= rl or rb <= rt:
                return result

            region = reduced.crop(rl, rt, rr - rl, rb - rt)
            if region.width != sw or region.height != sh:
                region = region.resize(
                    sw / region.width,
                    vscale=sh / region.height,
                    kernel="lanczos3"
                )
            crop = self._vips_to_pil(region)
        elif getattr(self, '_pil_image_fallback', None) is not None:
            region = self._pil_image_fallback.crop((cl, ct, cr, cb))
            if region.width != sw or region.height != sh:
                region = region.resize((sw, sh), Image.Resampling.LANCZOS)
            crop = region.convert("RGB")
        else:
            return result

        result.paste(crop, (int(round((cl - cam_x) * zoom)),
                            int(round((ct - cam_y) * zoom))))
        return result

    # ------------------------------------------------------------------
    # Region reading helpers
    # ------------------------------------------------------------------

    def _read_region(self, x, y, w, h):
        """Read a region as PIL Image.

        For slide formats: always use OpenSlide (pyvips reads wrong layer).
        For standard images: use pyvips.
        """
        if self._is_openslide and self._openslide is not None:
            return self._openslide.read_region(
                (x, y), 0, (w, h)
            ).convert("RGB")
        elif self._vips_image is not None:
            region = self._vips_image.crop(x, y, w, h)
            return self._vips_to_pil(region)
        elif getattr(self, '_pil_image_fallback', None) is not None:
            region = self._pil_image_fallback.crop((x, y, x + w, y + h))
            return region.convert("RGB")
        return Image.new("RGB", (w, h))

    @staticmethod
    def _vips_to_pil(vips_image):
        """Convert a pyvips Image to PIL Image efficiently."""
        if vips_image.bands == 1:
            mode = "L"
        elif vips_image.bands == 3:
            mode = "RGB"
        elif vips_image.bands == 4:
            mode = "RGBA"
        else:
            vips_image = vips_image.colourspace("srgb")
            mode = "RGB"

        if vips_image.format != "uchar":
            vips_image = vips_image.cast("uchar")

        data = vips_image.write_to_memory()
        return Image.frombytes(mode, (vips_image.width, vips_image.height), data)
