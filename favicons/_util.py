"""Common utility functions used throughout Favicons."""

# Standard Library
from typing import Union, Mapping, Generator
from pathlib import Path
from tempfile import mkstemp

# Project
from favicons._types import Color, FaviconProperties
from favicons._constants import ICON_TYPES
from favicons._exceptions import FaviconsError, FaviconNotFoundError


def validate_path(path: Union[Path, str], must_exist: bool = True, create: bool = False) -> Path:
    """Validate a path and ensure it's a Path object."""

    if isinstance(path, str):
        try:
            path = Path(path)
        except TypeError as err:
            raise FaviconsError("{path} is not a valid path.", path=path) from err

    if create:
        if path.is_dir() and not path.exists():
            path.mkdir(parents=True)
        elif not path.is_dir() and not path.parent.exists():
            path.parent.mkdir(parents=True)

    if must_exist and not path.exists():
        raise FaviconNotFoundError(path)

    return path


def generate_icon_types() -> Generator[FaviconProperties, None, None]:
    """Get icon type objects."""
    for icon_type in ICON_TYPES:
        if isinstance(icon_type, Mapping):
            yield FaviconProperties(**icon_type)


def svg_to_png(svg_path: Path) -> Path:
    """Convert an SVG vector to a PNG file."""
    import io
    # Third Party
    from cairosvg import svg2png
    from PIL import Image as PILImage

    _, png_path = mkstemp(suffix=".png")

    png = Path(png_path)

    png.write_bytes(svg2png(svg_path.read_bytes()))

    return png
