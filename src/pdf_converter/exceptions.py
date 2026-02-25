"""Exception hierarchy for the PDF converter."""


class PdfConverterError(Exception):
    """Base exception for all pdf-converter errors."""


class ParseError(PdfConverterError):
    """Raised when PDF parsing fails."""


class GenerationError(PdfConverterError):
    """Raised when Word document generation fails."""


class ConfigError(PdfConverterError):
    """Raised when configuration is invalid or missing."""


class ImageError(GenerationError):
    """Raised when an image cannot be loaded or embedded."""
