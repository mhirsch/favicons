"""Generate common favicon formats from a single source image."""

# Standard Library
import json as _json
import asyncio
import struct
from types import TracebackType
from typing import (
    Any,
    Type,
    Tuple,
    Union,
    Callable,
    Optional,
    Coroutine,
    Generator,
    Collection,
)
from pathlib import Path

# Third Party
import pyvips

# Project
from favicons._util import svg_to_png, validate_path, generate_icon_types
from favicons._types import Color, FaviconProperties
from favicons._constants import HTML_LINK, SUPPORTED_FORMATS
from favicons._exceptions import FaviconNotSupportedError

LoosePath = Union[Path, str]
LooseColor = Union[Collection[int], str]


class Favicons:
    """Generate common favicon formats from a single source image."""

    def __init__(
        self,
        source: LoosePath,
        output_directory: LoosePath,
        background_color: LooseColor = "#000000",
        transparent: bool = True,
        base_url: str = "/",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize Favicons class."""
        self._validated = False
        self._output_directory = output_directory
        self._formats = tuple(generate_icon_types())
        self.transparent = transparent
        self.base_url = base_url
        self.background_color: Color = Color(background_color)
        self.generate: Union[Callable, Coroutine] = self.sgenerate
        self.completed: int = 0
        self._temp_source: Optional[Path] = None
        self._svg_input = False

        if isinstance(source, str):
            source = Path(source)

        self._source = source
        self._check_source_format()

    def __del__(self) -> None:
        """Clean up temporary files on destruction."""
        self._close_temp_source()

    def _validate(self) -> None:
        """Validate source and output paths."""
        self.source = validate_path(self._source)
        self.output_directory = validate_path(self._output_directory, create=True)

        if self.source.suffix.lower() not in SUPPORTED_FORMATS:
            raise FaviconNotSupportedError(self.source)

        self._validated = True

    def __enter__(self) -> "Favicons":
        """Enter Favicons context."""
        self._validate()
        self.generate = self.sgenerate
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        """Exit Favicons context."""
        self._close_temp_source()

    async def __aenter__(self) -> "Favicons":
        """Enter Favicons async context."""
        self._validate()
        self.generate = self.agenerate
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        """Exit Favicons async context."""
        self._close_temp_source()

    def _close_temp_source(self) -> None:
        """Close temporary file if it exists."""
        if self._svg_input and self._source.exists():
            try:
                self._source.unlink()
            except OSError:
                pass

    def _check_source_format(self) -> None:
        """Convert source image to PNG if it's in SVG format."""
        if self._source.suffix.lower() == ".svg":
            self._svg_input = True
            # We convert to a temporary PNG because while vips can load SVG,
            # some systems may not have librsvg linked.
            self._source = svg_to_png(self._source)

    def _generate_single(self, format_properties: FaviconProperties) -> None:
        """Generate a single favicon using pyvips."""
        output_file = self.output_directory / str(format_properties)
        width, height = format_properties.dimensions

        # Handle background color and transparency
        # pyvips uses 0-255 scale
        alpha_val = 0 if self.transparent else 255
        bg_color = list(self.background_color.colors) + [alpha_val]

        # Resize the source image (maintaining aspect ratio)
        # 'force' is not used here because we want to center-pad inside target dims
        thumb = pyvips.Image.thumbnail(str(self.source), width, height=height)

        # Ensure thumbnail has an alpha channel and is explicitly in sRGB space
        if not thumb.hasalpha():
            thumb = thumb.addalpha()
        if thumb.interpretation != 'srgb':
            thumb = thumb.colourspace('srgb')

        # Create a background canvas and explicitly set its interpretation and format
        background = (pyvips.Image.black(width, height) + bg_color).cast(thumb.format).copy(interpretation='srgb')

        # Calculate centering offsets
        left = (width - thumb.width) // 2
        top = (height - thumb.height) // 2

        # Composite thumbnail over background
        final = background.composite2(thumb, 'over', x=left, y=top)

        # Save result.
        if output_file.suffix.lower() == ".ico":
            try:
                # Attempt to save directly (works if libvips has magicksave support)
                final.write_to_file(str(output_file))
            except pyvips.error.Error:
                # Fallback: Write as PNG into memory, then manually package into an ICO container format
                png_buffer = final.write_to_buffer(".png")

                # Windows ICO format requires dimensions 256 or larger to be mapped as 0
                ico_w = 0 if width >= 256 else width
                ico_h = 0 if height >= 256 else height

                # ICO Header: 0 (reserved), 1 (ICO type), 1 (number of images)
                header = struct.pack("<HHH", 0, 1, 1)

                # ICO Directory Entry: w, h, palette(0), reserved(0), planes(1), bpp(32), size, offset(22)
                directory = struct.pack("<BBBBHHII", ico_w, ico_h, 0, 0, 1, 32, len(png_buffer), 22)

                output_file.write_bytes(header + directory + png_buffer)
        else:
            final.write_to_file(str(output_file))

        self.completed += 1

    async def _agenerate_single(self, format_properties: FaviconProperties) -> None:
        """Awaitable version of _generate_single."""
        await asyncio.to_thread(self._generate_single, format_properties)

    def sgenerate(self) -> None:
        """Generate favicons synchronously."""
        if not self._validated:
            self._validate()

        for fmt in self._formats:
            self._generate_single(fmt)

    async def agenerate(self) -> None:
        """Generate favicons asynchronously."""
        if not self._validated:
            self._validate()

        await asyncio.gather(*(self._agenerate_single(fmt) for fmt in self._formats))

    def html_gen(self) -> Generator:
        """Get generator of HTML strings."""
        for fmt in self._formats:
            yield HTML_LINK.format(
                rel=fmt.rel,
                type=f"image/{fmt.image_fmt}",
                href=self.base_url + str(fmt),
            )

    def html(self) -> Tuple:
        """Get tuple of HTML strings."""
        return tuple(self.html_gen())

    def formats(self) -> Tuple:
        """Get image formats as list."""
        return tuple(f.dict() for f in self._formats)

    def json(self, *args: Any, **kwargs: Any) -> str:
        """Get image formats as JSON string."""
        return _json.dumps(self.formats(), *args, **kwargs)

    def filenames_gen(self, prefix: bool = False) -> Generator:
        """Get generator of favicon file names."""
        for fmt in self._formats:
            filename = str(fmt)
            if prefix:
                filename = self.base_url + filename
            yield filename

    def filenames(self, prefix: bool = False) -> Tuple:
        """Get tuple of favicon file names."""
        return tuple(self.filenames_gen(prefix=prefix))