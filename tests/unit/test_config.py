"""Tests for Config loading and defaults."""

import pytest

from pdf_converter.config import Config, ImageConfig, ParserConfig, StyleConfig
from pdf_converter.exceptions import ConfigError


class TestConfigDefaults:
    def test_default_config(self):
        cfg = Config.default()
        assert cfg.verbose is False
        assert cfg.style.heading_prefix == "Heading"
        assert cfg.style.body_style == "Normal"
        assert cfg.image.max_width_inches == 6.0
        assert cfg.parser.engine == "docling"

    def test_load_none_returns_default(self):
        cfg = Config.load(None)
        assert cfg.verbose is False
        assert cfg.parser.engine == "docling"


class TestConfigFromYAML:
    def test_full_yaml(self):
        yaml_text = """\
verbose: true
style:
  heading_prefix: "H"
  body_style: "Body Text"
image:
  max_width_inches: 5.0
  placeholder_text: "[Missing]"
parser:
  engine: marker
  ocr_enabled: false
"""
        cfg = Config.from_yaml_string(yaml_text)
        assert cfg.verbose is True
        assert cfg.style.heading_prefix == "H"
        assert cfg.style.body_style == "Body Text"
        assert cfg.image.max_width_inches == 5.0
        assert cfg.image.placeholder_text == "[Missing]"
        assert cfg.parser.engine == "marker"
        assert cfg.parser.ocr_enabled is False

    def test_partial_yaml_uses_defaults(self):
        yaml_text = """\
style:
  heading_prefix: "Custom"
"""
        cfg = Config.from_yaml_string(yaml_text)
        assert cfg.style.heading_prefix == "Custom"
        # Defaults for everything else
        assert cfg.style.body_style == "Normal"
        assert cfg.image.max_width_inches == 6.0
        assert cfg.parser.engine == "docling"
        assert cfg.verbose is False

    def test_empty_yaml(self):
        cfg = Config.from_yaml_string("")
        assert cfg.verbose is False
        assert cfg.style.heading_prefix == "Heading"

    def test_invalid_yaml_raises(self):
        with pytest.raises(ConfigError):
            Config.from_yaml_string("{{invalid yaml::")

    def test_unknown_keys_ignored(self):
        yaml_text = """\
style:
  heading_prefix: "H"
  unknown_key: "ignored"
parser:
  engine: docling
  future_setting: true
"""
        cfg = Config.from_yaml_string(yaml_text)
        assert cfg.style.heading_prefix == "H"
        assert cfg.parser.engine == "docling"


class TestConfigFromFile:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            Config.from_yaml(tmp_path / "nonexistent.yaml")

    def test_load_from_file(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("verbose: true\nparser:\n  engine: marker\n")
        cfg = Config.from_yaml(config_file)
        assert cfg.verbose is True
        assert cfg.parser.engine == "marker"
