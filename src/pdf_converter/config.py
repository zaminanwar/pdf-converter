"""YAML-backed configuration for the PDF converter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from pdf_converter.exceptions import ConfigError


@dataclass
class StyleConfig:
    """Word document style mappings."""

    heading_prefix: str = "Heading"  # e.g. "Heading 1", "Heading 2"
    body_style: str = "Normal"
    list_bullet_style: str = "List Bullet"
    list_number_style: str = "List Number"
    caption_style: str = "Caption"
    table_style: str = "Table Grid"
    mark_low_confidence: bool = False
    low_confidence_threshold: float = 0.7
    low_confidence_highlight: str = "yellow"


@dataclass
class ImageConfig:
    """Image handling settings."""

    max_width_inches: float = 6.0
    max_height_inches: float = 8.0
    placeholder_text: str = "[Image not available]"
    extract_dir_suffix: str = "_images"


@dataclass
class ParserConfig:
    """Parser selection and options."""

    engine: str = "docling"
    ocr_enabled: bool = True


@dataclass
class Config:
    """Top-level converter configuration."""

    style: StyleConfig = field(default_factory=StyleConfig)
    image: ImageConfig = field(default_factory=ImageConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    verbose: bool = False

    @classmethod
    def from_yaml(cls, path: Path) -> Config:
        """Load configuration from a YAML file."""
        try:
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text) or {}
        except FileNotFoundError:
            raise ConfigError(f"Config file not found: {path}")
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {path}: {exc}")

        return cls._from_dict(data)

    @classmethod
    def from_yaml_string(cls, text: str) -> Config:
        """Load configuration from a YAML string."""
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML: {exc}")
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> Config:
        style_data = data.get("style", {})
        image_data = data.get("image", {})
        parser_data = data.get("parser", {})

        return cls(
            style=StyleConfig(**{k: v for k, v in style_data.items() if k in StyleConfig.__dataclass_fields__}),
            image=ImageConfig(**{k: v for k, v in image_data.items() if k in ImageConfig.__dataclass_fields__}),
            parser=ParserConfig(**{k: v for k, v in parser_data.items() if k in ParserConfig.__dataclass_fields__}),
            verbose=data.get("verbose", False),
        )

    @classmethod
    def default(cls) -> Config:
        """Return the default configuration."""
        return cls()

    @classmethod
    def load(cls, path: Optional[Path] = None) -> Config:
        """Load config from path, or return defaults if path is None."""
        if path is None:
            return cls.default()
        return cls.from_yaml(path)
