"""Click CLI for the PDF converter.

Commands:
    convert   — Full PDF → .docx conversion
    inspect   — Parse PDF to IR JSON (for debugging)
    from-ir   — Generate .docx from a saved IR JSON file
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from pdf_converter.config import Config
from pdf_converter.exceptions import PdfConverterError
from pdf_converter.pipeline import Pipeline


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging.")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to a YAML configuration file.",
)
@click.pass_context
def main(ctx: click.Context, verbose: bool, config_path: Path | None) -> None:
    """PDF to Word converter for Polarion ALM import."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    config = Config.load(config_path)
    if verbose:
        config.verbose = True

    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["pipeline"] = Pipeline(config)


@main.command()
@click.argument("input_pdf", type=click.Path(exists=True, path_type=Path))
@click.argument("output_docx", type=click.Path(path_type=Path), required=False)
@click.option("--save-ir", is_flag=True, help="Save IR JSON checkpoint alongside output.")
@click.option(
    "--ir-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom path for the IR JSON file.",
)
@click.option("--report", is_flag=True, help="Save conversion report JSON alongside output.")
@click.option(
    "--report-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom path for the report JSON file.",
)
@click.option(
    "--mark-low-confidence",
    is_flag=True,
    help="Highlight low-confidence headings in the output document.",
)
@click.pass_context
def convert(
    ctx: click.Context,
    input_pdf: Path,
    output_docx: Path | None,
    save_ir: bool,
    ir_path: Path | None,
    report: bool,
    report_path: Path | None,
    mark_low_confidence: bool,
) -> None:
    """Convert a PDF to a Polarion-ready Word document."""
    pipeline: Pipeline = ctx.obj["pipeline"]

    if mark_low_confidence:
        pipeline.config.style.mark_low_confidence = True

    if output_docx is None:
        output_docx = input_pdf.with_suffix(".docx")

    try:
        result = pipeline.convert(
            input_pdf,
            output_docx,
            save_ir=save_ir,
            ir_path=ir_path,
            save_report=report,
            report_path=report_path,
        )
        click.echo(f"Generated: {result}")

        if report and pipeline.last_report:
            rpt = pipeline.last_report
            low = len(rpt.low_confidence_items)
            click.echo(
                f"Report: {rpt.heading_count} headings, "
                f"{rpt.table_count} tables, {rpt.figure_count} figures, "
                f"{low} low-confidence items"
            )
    except PdfConverterError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@main.command()
@click.argument("input_pdf", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def inspect(ctx: click.Context, input_pdf: Path) -> None:
    """Parse a PDF and output its IR as JSON (for debugging)."""
    pipeline: Pipeline = ctx.obj["pipeline"]

    try:
        json_str = pipeline.inspect(input_pdf)
        click.echo(json_str)
    except PdfConverterError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@main.command("from-ir")
@click.argument("ir_json", type=click.Path(exists=True, path_type=Path))
@click.argument("output_docx", type=click.Path(path_type=Path))
@click.pass_context
def from_ir(ctx: click.Context, ir_json: Path, output_docx: Path) -> None:
    """Generate a Word document from a saved IR JSON file."""
    pipeline: Pipeline = ctx.obj["pipeline"]

    try:
        result = pipeline.from_ir(ir_json, output_docx)
        click.echo(f"Generated: {result}")
    except PdfConverterError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
