"""Tests for IR Pydantic models — round-trip serialization, validation, tree structure."""

import json

import pytest

from pdf_converter.ir import (
    DocumentIR,
    DocumentMetadata,
    FigureBlock,
    FurnitureItem,
    FurnitureType,
    HeadingBlock,
    ListBlock,
    ListItem,
    PageBreakBlock,
    ParagraphBlock,
    TableBlock,
    TableCell,
    TextRun,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_document() -> DocumentIR:
    """Build a realistic IR document for testing."""
    return DocumentIR(
        metadata=DocumentMetadata(
            source_file="requirements.pdf",
            source_hash="abc123",
            parser="docling",
            parser_version="2.70",
            page_count=5,
            title="System Requirements",
        ),
        body=[
            HeadingBlock(
                id="h1",
                level=1,
                text="1. Introduction",
                page=1,
                children=[
                    ParagraphBlock(
                        id="p1",
                        text="This document describes the requirements.",
                        page=1,
                        runs=[
                            TextRun(text="This document describes the "),
                            TextRun(text="requirements", bold=True),
                            TextRun(text="."),
                        ],
                    ),
                    HeadingBlock(
                        id="h2",
                        level=2,
                        text="1.1 Scope",
                        page=1,
                        children=[
                            ListBlock(
                                id="l1",
                                style="unordered",
                                page=1,
                                items=[
                                    ListItem(text="Item A"),
                                    ListItem(
                                        text="Item B",
                                        children=[
                                            ListItem(text="Sub-item B1"),
                                            ListItem(text="Sub-item B2"),
                                        ],
                                    ),
                                ],
                            ),
                            TableBlock(
                                id="t1",
                                page=2,
                                num_rows=2,
                                num_cols=2,
                                cells=[
                                    TableCell(row=0, col=0, text="Header 1"),
                                    TableCell(row=0, col=1, text="Header 2"),
                                    TableCell(row=1, col=0, text="Value 1"),
                                    TableCell(row=1, col=1, text="Value 2"),
                                ],
                            ),
                            FigureBlock(
                                id="f1",
                                page=2,
                                image_path="requirements_images/fig_001.png",
                                caption="Architecture overview",
                            ),
                        ],
                    ),
                ],
            ),
            PageBreakBlock(id="pb1", page=3),
            HeadingBlock(
                id="h3",
                level=1,
                text="2. Functional Requirements",
                page=3,
                children=[
                    ParagraphBlock(id="p2", text="TBD", page=3),
                ],
            ),
        ],
        furniture=[
            FurnitureItem(
                type=FurnitureType.HEADER,
                text="ACME Corp — Confidential",
                pages=[1, 2, 3, 4, 5],
            ),
            FurnitureItem(
                type=FurnitureType.FOOTER,
                text="Page {n}",
                pages=[1, 2, 3, 4, 5],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Round-trip serialization
# ---------------------------------------------------------------------------

class TestIRSerialization:
    def test_round_trip_json(self):
        """DocumentIR → JSON → DocumentIR preserves all data."""
        doc = _sample_document()
        json_str = doc.to_json()
        restored = DocumentIR.from_json(json_str)

        assert restored.metadata.source_file == "requirements.pdf"
        assert restored.metadata.page_count == 5
        assert len(restored.body) == 3  # 2 headings + 1 page break
        assert len(restored.furniture) == 2

    def test_json_is_valid(self):
        """to_json() produces valid JSON."""
        doc = _sample_document()
        data = json.loads(doc.to_json())
        assert isinstance(data, dict)
        assert "metadata" in data
        assert "body" in data
        assert "furniture" in data

    def test_round_trip_preserves_tree_structure(self):
        """Heading children survive serialization."""
        doc = _sample_document()
        restored = DocumentIR.from_json(doc.to_json())

        h1 = restored.body[0]
        assert h1.type == "heading"
        assert h1.level == 1
        assert len(h1.children) == 2  # paragraph + heading

        h2 = h1.children[1]
        assert h2.type == "heading"
        assert h2.level == 2
        assert len(h2.children) == 3  # list + table + figure

    def test_round_trip_preserves_runs(self):
        """TextRuns with formatting survive serialization."""
        doc = _sample_document()
        restored = DocumentIR.from_json(doc.to_json())

        p1 = restored.body[0].children[0]
        assert p1.type == "paragraph"
        assert len(p1.runs) == 3
        assert p1.runs[1].bold is True
        assert p1.runs[1].text == "requirements"

    def test_round_trip_preserves_nested_list(self):
        """Nested list items survive serialization."""
        doc = _sample_document()
        restored = DocumentIR.from_json(doc.to_json())

        list_block = restored.body[0].children[1].children[0]
        assert list_block.type == "list"
        assert len(list_block.items) == 2
        assert len(list_block.items[1].children) == 2
        assert list_block.items[1].children[0].text == "Sub-item B1"

    def test_round_trip_preserves_table(self):
        """Table cells survive serialization."""
        doc = _sample_document()
        restored = DocumentIR.from_json(doc.to_json())

        table = restored.body[0].children[1].children[1]
        assert table.type == "table"
        assert table.num_rows == 2
        assert table.num_cols == 2
        assert len(table.cells) == 4
        assert table.cells[0].text == "Header 1"

    def test_round_trip_preserves_furniture(self):
        """Furniture items survive serialization."""
        doc = _sample_document()
        restored = DocumentIR.from_json(doc.to_json())

        assert restored.furniture[0].type == FurnitureType.HEADER
        assert restored.furniture[0].text == "ACME Corp — Confidential"
        assert restored.furniture[1].type == FurnitureType.FOOTER


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestIRValidation:
    def test_heading_level_range(self):
        """Heading level must be 1-9."""
        with pytest.raises(Exception):
            HeadingBlock(level=0, text="Bad")
        with pytest.raises(Exception):
            HeadingBlock(level=10, text="Bad")

    def test_heading_level_valid(self):
        h = HeadingBlock(level=1, text="OK")
        assert h.level == 1
        h9 = HeadingBlock(level=9, text="Deep")
        assert h9.level == 9

    def test_table_cell_span_defaults(self):
        """Table cells default to 1x1 span."""
        cell = TableCell(row=0, col=0)
        assert cell.row_span == 1
        assert cell.col_span == 1

    def test_text_run_defaults(self):
        """TextRun defaults to no formatting."""
        run = TextRun(text="hello")
        assert run.bold is False
        assert run.italic is False
        assert run.highlight is None

    def test_empty_document(self):
        """An empty DocumentIR is valid."""
        doc = DocumentIR()
        assert doc.metadata.source_file == ""
        assert doc.body == []
        assert doc.furniture == []

        # Round-trip
        restored = DocumentIR.from_json(doc.to_json())
        assert restored.body == []


# ---------------------------------------------------------------------------
# Block type discrimination
# ---------------------------------------------------------------------------

class TestBlockDiscrimination:
    def test_discriminator_paragraph(self):
        doc = DocumentIR(body=[ParagraphBlock(text="hello")])
        restored = DocumentIR.from_json(doc.to_json())
        assert restored.body[0].type == "paragraph"

    def test_discriminator_list(self):
        doc = DocumentIR(body=[ListBlock(items=[ListItem(text="a")])])
        restored = DocumentIR.from_json(doc.to_json())
        assert restored.body[0].type == "list"

    def test_discriminator_table(self):
        doc = DocumentIR(body=[TableBlock(num_rows=1, num_cols=1)])
        restored = DocumentIR.from_json(doc.to_json())
        assert restored.body[0].type == "table"

    def test_discriminator_figure(self):
        doc = DocumentIR(body=[FigureBlock(caption="test")])
        restored = DocumentIR.from_json(doc.to_json())
        assert restored.body[0].type == "figure"

    def test_discriminator_page_break(self):
        doc = DocumentIR(body=[PageBreakBlock()])
        restored = DocumentIR.from_json(doc.to_json())
        assert restored.body[0].type == "page_break"

    def test_discriminator_heading(self):
        doc = DocumentIR(body=[HeadingBlock(level=1, text="H1")])
        restored = DocumentIR.from_json(doc.to_json())
        assert restored.body[0].type == "heading"


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------

class TestIDGeneration:
    def test_auto_id(self):
        """Blocks get auto-generated IDs."""
        p = ParagraphBlock(text="hello")
        assert len(p.id) == 12

    def test_unique_ids(self):
        """Each block gets a different auto-ID."""
        blocks = [ParagraphBlock(text="x") for _ in range(100)]
        ids = {b.id for b in blocks}
        assert len(ids) == 100

    def test_explicit_id(self):
        """Explicit IDs are preserved."""
        p = ParagraphBlock(id="custom-id", text="hello")
        assert p.id == "custom-id"


# ---------------------------------------------------------------------------
# ListBlock marker_format
# ---------------------------------------------------------------------------

class TestListBlockMarkerFormat:
    def test_marker_format_default_none(self):
        lb = ListBlock(style="ordered", items=[ListItem(text="a")])
        assert lb.marker_format is None

    def test_marker_format_lower_letter(self):
        lb = ListBlock(style="ordered", marker_format="lowerLetter", items=[ListItem(text="a")])
        assert lb.marker_format == "lowerLetter"

    def test_marker_format_round_trip(self):
        """marker_format survives JSON serialization."""
        doc = DocumentIR(body=[
            ListBlock(
                style="ordered",
                marker_format="lowerLetter",
                items=[ListItem(text="item a")],
            ),
        ])
        restored = DocumentIR.from_json(doc.to_json())
        assert restored.body[0].marker_format == "lowerLetter"

    def test_marker_format_none_round_trip(self):
        """marker_format=None survives JSON serialization."""
        doc = DocumentIR(body=[
            ListBlock(style="ordered", items=[ListItem(text="item 1")]),
        ])
        restored = DocumentIR.from_json(doc.to_json())
        assert restored.body[0].marker_format is None


# ---------------------------------------------------------------------------
# Heading confidence fields
# ---------------------------------------------------------------------------

class TestHeadingConfidence:
    def test_default_confidence(self):
        """HeadingBlock defaults to confidence=1.0 and reason=None."""
        h = HeadingBlock(level=1, text="Title")
        assert h.confidence == 1.0
        assert h.classification_reason is None

    def test_explicit_confidence(self):
        h = HeadingBlock(
            level=1, text="Title", confidence=0.75,
            classification_reason="docling_label:section_header",
        )
        assert h.confidence == 0.75
        assert h.classification_reason == "docling_label:section_header"

    def test_confidence_range_rejects_above_one(self):
        with pytest.raises(Exception):
            HeadingBlock(level=1, text="Bad", confidence=1.5)

    def test_confidence_range_rejects_negative(self):
        with pytest.raises(Exception):
            HeadingBlock(level=1, text="Bad", confidence=-0.1)

    def test_confidence_round_trip(self):
        """confidence and classification_reason survive JSON serialization."""
        doc = DocumentIR(body=[
            HeadingBlock(
                level=1, text="H1", confidence=0.65,
                classification_reason="promoted:multi_level_3_parts",
            ),
        ])
        restored = DocumentIR.from_json(doc.to_json())
        assert restored.body[0].confidence == 0.65
        assert restored.body[0].classification_reason == "promoted:multi_level_3_parts"

    def test_confidence_default_round_trip(self):
        """Default confidence=1.0 and reason=None survive round-trip."""
        doc = DocumentIR(body=[HeadingBlock(level=1, text="H1")])
        restored = DocumentIR.from_json(doc.to_json())
        assert restored.body[0].confidence == 1.0
        assert restored.body[0].classification_reason is None
