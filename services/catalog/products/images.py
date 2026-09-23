"""Turn an uploaded original into WebP renditions. Pure functions, no I/O."""

import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

#: Rendition name -> longest side in pixels.
SIZES: dict[str, int] = {"thumb": 200, "medium": 600, "large": 1200}
ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 50_000_000
WEBP_QUALITY = 82


class InvalidImageError(ValueError):
    """The bytes are not an image we accept."""


def _open(data: bytes) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = Image.open(io.BytesIO(data))
            if probe.format not in ACCEPTED_FORMATS:
                raise InvalidImageError(f"unsupported format {probe.format}")
            if probe.width * probe.height > MAX_PIXELS:
                raise InvalidImageError("image is too large")
            probe.verify()
            image = Image.open(io.BytesIO(data))
            image.load()
    except InvalidImageError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise InvalidImageError("not a valid image") from exc
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImageError("image is too large") from exc
    return image


def render_webp(data: bytes) -> dict[str, bytes]:
    """WebP bytes per rendition, scaled down by the longest side and never upscaled."""
    image = ImageOps.exif_transpose(_open(data))
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    image = image.convert("RGBA" if has_alpha else "RGB")

    renditions: dict[str, bytes] = {}
    for name, side in SIZES.items():
        copy = image.copy()
        copy.thumbnail((side, side), Image.Resampling.LANCZOS)  # keeps ratio, only shrinks
        buffer = io.BytesIO()
        copy.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=4)
        renditions[name] = buffer.getvalue()
    return renditions
