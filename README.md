# PDF Converter

A two-stage PDF-to-Word converter for importing customer requirements documents into Siemens Polarion ALM.

## Architecture

```
PDF  →  Docling Parser  →  Document IR (JSON)  →  Word Generator  →  .docx
```

- **Stage 1 (Parser):** Uses IBM Docling for structure-preserving PDF parsing. Extracts headings, paragraphs, tables, figures, and lists into a tree-structured intermediate representation.
- **Stage 2 (Generator):** Converts the IR into a Polarion-ready Word document with proper heading hierarchy, list numbering, table formatting, and embedded images.

The IR can be saved as a JSON checkpoint between stages for debugging or downstream processing.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

pip install -e ".[dev]"
```

> **Siemens network note:** The SSL fix for Zscaler proxy runs automatically on import. Place your decoded Zscaler root certificate at `~/zscaler-root-new.pem` and the tool will create a combined CA bundle on first run.

## Usage

```bash
# Full conversion: PDF → Word
pdf-converter convert input.pdf output.docx

# Save IR checkpoint alongside output
pdf-converter convert input.pdf output.docx --save-ir

# Save conversion report (heading counts, confidence diagnostics)
pdf-converter convert input.pdf output.docx --report

# Highlight low-confidence headings in the output
pdf-converter convert input.pdf output.docx --mark-low-confidence

# Parse PDF to IR JSON only (for debugging)
pdf-converter inspect input.pdf

# Generate Word from a saved IR JSON file
pdf-converter from-ir output.ir.json output.docx

# Use a custom config file
pdf-converter --config config/no-ocr.yaml convert input.pdf output.docx

# Verbose logging
pdf-converter -v convert input.pdf output.docx
```

## Testing

```bash
pytest tests/unit -v              # Unit tests (no PDF parsing needed)
pytest -v                         # All tests (requires Docling)
pytest -m "not integration"       # Skip integration tests
```

## Project Structure

```
src/pdf_converter/
    cli.py                   # Click CLI (convert, inspect, from-ir)
    config.py                # YAML-backed configuration
    pipeline.py              # Pipeline orchestrator
    exceptions.py            # Exception hierarchy
    _ssl_fix.py              # Zscaler SSL + Windows symlink workarounds
    ir/
        schema.py            # Pydantic IR models (tree-structured headings)
        report.py            # Conversion diagnostics / statistics
    generators/
        word_generator.py    # IR → .docx renderer
        styles.py            # Word style + numbering management
        table_builder.py     # Table rendering with merged cells
        image_handler.py     # Image sizing, embedding, fallbacks
    parsers/
        base.py              # Abstract parser base class
        docling_parser.py    # Docling-based PDF parser
        factory.py           # Parser factory
config/
    default.yaml             # Default Docling configuration
    no-ocr.yaml              # Configuration with OCR disabled
tests/unit/                  # 207 unit tests
```
