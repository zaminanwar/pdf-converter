"""Abstract base class for PDF parsers."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

from pdf_converter.config import Config
from pdf_converter.ir.schema import DocumentIR


class BasePdfParser(ABC):
    """Base class that all PDF parser implementations must extend."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config.default()

    @abstractmethod
    def parse(self, pdf_path: Path) -> DocumentIR:
        """Parse a PDF file and return its IR representation.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            A DocumentIR representing the parsed document.

        Raises:
            ParseError: If parsing fails.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the parser engine name (e.g. 'docling', 'marker')."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Return the parser version string."""

    @staticmethod
    def file_hash(path: Path) -> str:
        """Compute SHA-256 hash of a file for IR metadata."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
