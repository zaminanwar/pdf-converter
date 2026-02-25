"""Parser factory — selects a parser implementation based on config."""

from __future__ import annotations

from pdf_converter.config import Config
from pdf_converter.exceptions import ConfigError
from pdf_converter.parsers.base import BasePdfParser


def create_parser(config: Config | None = None) -> BasePdfParser:
    """Create a parser instance based on config.

    Args:
        config: Converter configuration. Uses default if None.

    Returns:
        A BasePdfParser implementation.

    Raises:
        ConfigError: If the configured engine is unknown.
    """
    config = config or Config.default()
    engine = config.parser.engine.lower()

    if engine == "docling":
        from pdf_converter.parsers.docling_parser import DoclingParser

        return DoclingParser(config)
    else:
        raise ConfigError(
            f"Unknown parser engine: '{engine}'. Available: docling"
        )
