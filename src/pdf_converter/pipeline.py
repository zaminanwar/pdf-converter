"""Pipeline orchestrator: parse → (optional IR save) → generate.

Coordinates the two-stage conversion process and provides
convenience methods for partial workflows (parse-only, generate-from-IR).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from pdf_converter.config import Config
from pdf_converter.exceptions import GenerationError, ParseError
from pdf_converter.generators.word_generator import WordGenerator
from pdf_converter.ir.report import ConversionReport
from pdf_converter.ir.schema import DocumentIR
from pdf_converter.parsers.factory import create_parser

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates PDF → IR → Word conversion."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config.default()
        self.last_report: ConversionReport | None = None

    def convert(
        self,
        pdf_path: Path,
        output_path: Path,
        save_ir: bool = False,
        ir_path: Path | None = None,
        save_report: bool = False,
        report_path: Path | None = None,
    ) -> Path:
        """Full pipeline: PDF → IR → .docx.

        Args:
            pdf_path: Input PDF file.
            output_path: Output .docx file.
            save_ir: Whether to save the IR as a JSON checkpoint.
            ir_path: Custom path for IR JSON. Defaults to {output_stem}.ir.json.
            save_report: Whether to save a conversion report JSON.
            report_path: Custom path for report JSON. Defaults to {output_stem}.report.json.

        Returns:
            Path to the generated .docx file.
        """
        pdf_path = Path(pdf_path)
        output_path = Path(output_path)

        # Stage 1: Parse
        t0 = time.monotonic()
        ir = self.parse(pdf_path)
        t1 = time.monotonic()

        # Optional: save IR checkpoint
        if save_ir:
            if ir_path is None:
                ir_path = output_path.with_suffix(".ir.json")
            self.save_ir(ir, ir_path)

        # Stage 2: Generate
        t2 = time.monotonic()
        result = self.generate(ir, output_path, base_dir=pdf_path.parent)
        t3 = time.monotonic()

        # Build report
        report = ConversionReport.from_ir(ir)
        report.parse_time_seconds = t1 - t0
        report.generate_time_seconds = t3 - t2
        report.total_time_seconds = t3 - t0
        self.last_report = report

        # Optional: save report
        if save_report:
            if report_path is None:
                report_path = output_path.with_suffix(".report.json")
            report_path.write_text(report.to_json(), encoding="utf-8")
            logger.info("Saved report to %s", report_path)

        return result

    def parse(self, pdf_path: Path) -> DocumentIR:
        """Stage 1: Parse a PDF to IR.

        Args:
            pdf_path: Input PDF file.

        Returns:
            The parsed DocumentIR.
        """
        pdf_path = Path(pdf_path)
        logger.info("Parsing %s", pdf_path)

        parser = create_parser(self.config)
        return parser.parse(pdf_path)

    def generate(
        self,
        ir: DocumentIR,
        output_path: Path,
        base_dir: Path | None = None,
    ) -> Path:
        """Stage 2: Generate .docx from IR.

        Args:
            ir: The document IR.
            output_path: Output .docx file path.
            base_dir: Base dir for resolving relative image paths.

        Returns:
            Path to the generated .docx file.
        """
        output_path = Path(output_path)
        logger.info("Generating %s", output_path)

        generator = WordGenerator(self.config)
        return generator.generate(ir, output_path, base_dir)

    def inspect(self, pdf_path: Path) -> str:
        """Parse PDF and return IR as formatted JSON string.

        Args:
            pdf_path: Input PDF file.

        Returns:
            JSON string of the IR.
        """
        ir = self.parse(pdf_path)
        return ir.to_json()

    def from_ir(
        self,
        ir_path: Path,
        output_path: Path,
    ) -> Path:
        """Generate .docx from a saved IR JSON file.

        Args:
            ir_path: Path to the IR JSON file.
            output_path: Output .docx file path.

        Returns:
            Path to the generated .docx file.
        """
        ir_path = Path(ir_path)
        output_path = Path(output_path)

        logger.info("Loading IR from %s", ir_path)
        try:
            json_str = ir_path.read_text(encoding="utf-8")
            ir = DocumentIR.from_json(json_str)
        except FileNotFoundError:
            raise ParseError(f"IR file not found: {ir_path}")
        except Exception as exc:
            raise ParseError(f"Failed to load IR from {ir_path}: {exc}") from exc

        return self.generate(ir, output_path, base_dir=ir_path.parent)

    @staticmethod
    def save_ir(ir: DocumentIR, path: Path) -> Path:
        """Save IR to a JSON file.

        Args:
            ir: The document IR to save.
            path: Output JSON file path.

        Returns:
            The path written to.
        """
        path = Path(path)
        logger.info("Saving IR to %s", path)
        path.write_text(ir.to_json(), encoding="utf-8")
        return path
