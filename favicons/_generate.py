"""Generate common favicon formats from a single source image."""

# Standard Library
import json as _json
import math
import asyncio
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
from PIL import Image as PILImage
from PIL import ImageOps

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

        if isinstance(source, str):
            source = Path(source)

        self._source = source

        self._check_source_format()

    def _validate(self) -> None:

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
        pass

    async def __aenter__(self) -> "Favicons":
        """Enter Favicons context."""
        self._validate()
        self.generate = self.agenerate
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        """Exit Favicons context."""
        self._close_temp_source()
        pass

    def _close_temp_source(self) -> None:
        """Close temporary file if it exists."""
        if self._temp_source is not None:
            try:
                self._temp_source.unlink()
            except FileNotFoundError:
                pass

    def _check_source_format(self) -> None:
        """Convert source image to PNG if it's in SVG format."""
        if self._source.suffix == ".svg":
            self._source = svg_to_png(self._source)

    def _generate_single(self, format_properties: FaviconProperties) -> None:
        with PILImage.open(self.source) as src:
            output_file = self.output_directory / str(format_properties)
            # If transparency is enabled, add alpha channel to color.
            bg: Tuple[int, ...] = self.background_color.colors + ((255,),(0,))[self.transparent]

            # Composite source image on top of background color.
            src = PILImage.alpha_composite(PILImage.new("RGBA", src.size, bg), src.convert("RGBA"))

            # Resize source image without changing aspect ratio, and pad with bg color.
            src = ImageOps.pad(src, size=format_properties.dimensions, color=bg)

            # Save new file.
            src.save(output_file, format_properties.image_fmt)

            self.completed += 1

    async def _agenerate_single(self, format_properties: FaviconProperties) -> None:
        """Awaitable version of _generate_single."""

        return self._generate_single(format_properties)

    def sgenerate(self) -> None:
        """Generate favicons."""
        if not self._validated:
            self._validate()

        for fmt in self._formats:
            self._generate_single(fmt)

    async def agenerate(self) -> None:
        """Generate favicons."""
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
