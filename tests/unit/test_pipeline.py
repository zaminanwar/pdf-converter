"""Tests for pipeline orchestrator and CLI.

These tests use hand-crafted IR (no Docling needed) to test the
generate and from-ir workflows, plus CLI argument parsing.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from pdf_converter.cli import main
from pdf_converter.config import Config
from pdf_converter.exceptions import ParseError
from pdf_converter.ir.schema import (
    DocumentIR,
    DocumentMetadata,
    HeadingBlock,
    ParagraphBlock,
)
from pdf_converter.pipeline import Pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_ir() -> DocumentIR:
    return DocumentIR(
        metadata=DocumentMetadata(title="Test"),
        body=[
            HeadingBlock(level=1, text="Title", children=[
                ParagraphBlock(text="Body text."),
            ]),
        ],
    )


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------

class TestPipelineGenerate:
    def test_generate_from_ir(self, tmp_path):
        pipeline = Pipeline()
        ir = _simple_ir()
        out = tmp_path / "output.docx"
        result = pipeline.generate(ir, out)
        assert result == out
        assert out.exists()

    def test_save_and_load_ir(self, tmp_path):
        pipeline = Pipeline()
        ir = _simple_ir()

        ir_path = tmp_path / "doc.ir.json"
        pipeline.save_ir(ir, ir_path)
        assert ir_path.exists()

        # Regenerate from saved IR
        out = tmp_path / "from_ir.docx"
        result = pipeline.from_ir(ir_path, out)
        assert result == out
        assert out.exists()

    def test_from_ir_missing_file(self, tmp_path):
        pipeline = Pipeline()
        with pytest.raises(ParseError, match="not found"):
            pipeline.from_ir(tmp_path / "nonexistent.json", tmp_path / "out.docx")

    def test_save_ir_roundtrip_content(self, tmp_path):
        """Verify IR content survives save/load cycle."""
        pipeline = Pipeline()
        ir = _simple_ir()

        ir_path = tmp_path / "test.ir.json"
        pipeline.save_ir(ir, ir_path)

        loaded = DocumentIR.from_json(ir_path.read_text())
        assert loaded.metadata.title == "Test"
        assert loaded.body[0].text == "Title"
        assert loaded.body[0].children[0].text == "Body text."


class TestPipelineConvert:
    @patch("pdf_converter.pipeline.create_parser")
    def test_convert_full_pipeline(self, mock_factory, tmp_path):
        """Test full convert with a mocked parser."""
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _simple_ir()
        mock_factory.return_value = mock_parser

        pipeline = Pipeline()
        pdf = tmp_path / "input.pdf"
        pdf.write_bytes(b"%PDF-fake")
        out = tmp_path / "output.docx"

        result = pipeline.convert(pdf, out)
        assert result == out
        assert out.exists()
        mock_parser.parse.assert_called_once_with(pdf)

    @patch("pdf_converter.pipeline.create_parser")
    def test_convert_with_save_ir(self, mock_factory, tmp_path):
        """Test convert with --save-ir saves the IR file."""
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _simple_ir()
        mock_factory.return_value = mock_parser

        pipeline = Pipeline()
        pdf = tmp_path / "input.pdf"
        pdf.write_bytes(b"%PDF-fake")
        out = tmp_path / "output.docx"

        pipeline.convert(pdf, out, save_ir=True)
        assert out.exists()
        assert (tmp_path / "output.ir.json").exists()


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestCLI:
    def test_cli_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "PDF to Word converter" in result.output

    def test_cli_convert_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["convert", "--help"])
        assert result.exit_code == 0
        assert "Convert a PDF" in result.output

    def test_cli_inspect_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["inspect", "--help"])
        assert result.exit_code == 0
        assert "Parse a PDF" in result.output

    def test_cli_from_ir_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["from-ir", "--help"])
        assert result.exit_code == 0
        assert "Generate a Word document" in result.output

    def test_cli_from_ir(self, tmp_path):
        """Test the from-ir command with a real IR file."""
        ir = _simple_ir()
        ir_path = tmp_path / "test.ir.json"
        ir_path.write_text(ir.to_json())

        out = tmp_path / "result.docx"
        runner = CliRunner()
        result = runner.invoke(main, ["from-ir", str(ir_path), str(out)])
        assert result.exit_code == 0
        assert "Generated" in result.output
        assert out.exists()

    @patch("pdf_converter.pipeline.create_parser")
    def test_cli_convert(self, mock_factory, tmp_path):
        """Test convert command with mocked parser."""
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _simple_ir()
        mock_factory.return_value = mock_parser

        pdf = tmp_path / "input.pdf"
        pdf.write_bytes(b"%PDF-fake")
        out = tmp_path / "output.docx"

        runner = CliRunner()
        result = runner.invoke(main, ["convert", str(pdf), str(out)])
        assert result.exit_code == 0
        assert "Generated" in result.output

    def test_cli_convert_missing_pdf(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["convert", str(tmp_path / "nope.pdf")])
        assert result.exit_code != 0

    def test_cli_verbose(self):
        runner = CliRunner()
        result = runner.invoke(main, ["-v", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Pipeline report tests
# ---------------------------------------------------------------------------

class TestPipelineReport:
    @patch("pdf_converter.pipeline.create_parser")
    def test_convert_produces_report(self, mock_factory, tmp_path):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _simple_ir()
        mock_factory.return_value = mock_parser

        pipeline = Pipeline()
        pdf = tmp_path / "input.pdf"
        pdf.write_bytes(b"%PDF-fake")
        out = tmp_path / "output.docx"

        pipeline.convert(pdf, out)
        assert pipeline.last_report is not None
        assert pipeline.last_report.heading_count == 1
        assert pipeline.last_report.paragraph_count == 1
        assert pipeline.last_report.total_time_seconds > 0

    @patch("pdf_converter.pipeline.create_parser")
    def test_convert_saves_report(self, mock_factory, tmp_path):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _simple_ir()
        mock_factory.return_value = mock_parser

        pipeline = Pipeline()
        pdf = tmp_path / "input.pdf"
        pdf.write_bytes(b"%PDF-fake")
        out = tmp_path / "output.docx"

        pipeline.convert(pdf, out, save_report=True)
        report_file = tmp_path / "output.report.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text())
        assert "block_counts" in data
        assert data["block_counts"]["headings"] == 1

    @patch("pdf_converter.pipeline.create_parser")
    def test_convert_saves_report_custom_path(self, mock_factory, tmp_path):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _simple_ir()
        mock_factory.return_value = mock_parser

        pipeline = Pipeline()
        pdf = tmp_path / "input.pdf"
        pdf.write_bytes(b"%PDF-fake")
        out = tmp_path / "output.docx"
        custom_report = tmp_path / "custom.json"

        pipeline.convert(pdf, out, save_report=True, report_path=custom_report)
        assert custom_report.exists()


# ---------------------------------------------------------------------------
# CLI report tests
# ---------------------------------------------------------------------------

class TestCLIReport:
    @patch("pdf_converter.pipeline.create_parser")
    def test_cli_convert_with_report(self, mock_factory, tmp_path):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = _simple_ir()
        mock_factory.return_value = mock_parser

        pdf = tmp_path / "input.pdf"
        pdf.write_bytes(b"%PDF-fake")
        out = tmp_path / "output.docx"

        runner = CliRunner()
        result = runner.invoke(main, [
            "convert", str(pdf), str(out), "--report",
        ])
        assert result.exit_code == 0
        assert "headings" in result.output
        assert (tmp_path / "output.report.json").exists()

    def test_cli_convert_help_shows_report_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, ["convert", "--help"])
        assert "--report" in result.output
        assert "--mark-low-confidence" in result.output
