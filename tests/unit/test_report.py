"""Tests for ConversionReport — block counting, low-confidence detection, serialization."""

import json

import pytest

from pdf_converter.ir.report import ConversionReport, LowConfidenceItem
from pdf_converter.ir.schema import (
    DocumentIR,
    DocumentMetadata,
    FigureBlock,
    HeadingBlock,
    ListBlock,
    ListItem,
    ParagraphBlock,
    TableBlock,
    TableCell,
)


class TestConversionReportFromIR:
    def test_counts_all_block_types(self):
        ir = DocumentIR(
            metadata=DocumentMetadata(source_file="test.pdf", page_count=5),
            body=[
                HeadingBlock(level=1, text="H1", children=[
                    ParagraphBlock(text="P1"),
                    ParagraphBlock(text="P2"),
                    HeadingBlock(level=2, text="H2", children=[
                        TableBlock(num_rows=2, num_cols=2, cells=[
                            TableCell(row=0, col=0, text="A"),
                        ]),
                    ]),
                ]),
                FigureBlock(caption="Fig1"),
                ListBlock(items=[ListItem(text="item1")]),
            ],
        )
        report = ConversionReport.from_ir(ir)
        assert report.heading_count == 2
        assert report.paragraph_count == 2
        assert report.table_count == 1
        assert report.figure_count == 1
        assert report.list_count == 1
        assert report.source_file == "test.pdf"
        assert report.page_count == 5

    def test_headings_by_level(self):
        ir = DocumentIR(body=[
            HeadingBlock(level=1, text="H1"),
            HeadingBlock(level=2, text="H2a"),
            HeadingBlock(level=2, text="H2b"),
            HeadingBlock(level=3, text="H3"),
        ])
        report = ConversionReport.from_ir(ir)
        assert report.headings_by_level == {1: 1, 2: 2, 3: 1}

    def test_low_confidence_detection(self):
        ir = DocumentIR(body=[
            HeadingBlock(level=1, text="Good heading", confidence=0.95),
            HeadingBlock(level=2, text="Iffy heading", confidence=0.50,
                         classification_reason="inherited"),
            HeadingBlock(level=3, text="Borderline", confidence=0.70),
        ])
        report = ConversionReport.from_ir(ir)
        # Default threshold is 0.7, so only 0.50 is below it (0.70 is not < 0.70)
        assert len(report.low_confidence_items) == 1
        assert report.low_confidence_items[0].text == "Iffy heading"
        assert report.low_confidence_items[0].confidence == 0.50
        assert report.low_confidence_items[0].reason == "inherited"

    def test_custom_threshold(self):
        ir = DocumentIR(body=[
            HeadingBlock(level=1, text="H1", confidence=0.80),
        ])
        report = ConversionReport.from_ir(ir, low_confidence_threshold=0.90)
        assert len(report.low_confidence_items) == 1  # 0.80 < 0.90

    def test_low_confidence_in_nested_children(self):
        ir = DocumentIR(body=[
            HeadingBlock(level=1, text="Parent", confidence=0.95, children=[
                HeadingBlock(level=2, text="Low child", confidence=0.40,
                             classification_reason="test"),
            ]),
        ])
        report = ConversionReport.from_ir(ir)
        assert len(report.low_confidence_items) == 1
        assert report.low_confidence_items[0].text == "Low child"

    def test_empty_document(self):
        ir = DocumentIR()
        report = ConversionReport.from_ir(ir)
        assert report.heading_count == 0
        assert report.paragraph_count == 0
        assert report.low_confidence_items == []
        assert report.headings_by_level == {}


class TestConversionReportSerialization:
    def test_to_json_valid(self):
        report = ConversionReport(
            source_file="test.pdf",
            heading_count=3,
            parse_time_seconds=1.234,
        )
        j = report.to_json()
        data = json.loads(j)
        assert data["source_file"] == "test.pdf"
        assert data["block_counts"]["headings"] == 3
        assert data["timing"]["parse_seconds"] == 1.234

    def test_to_json_with_low_confidence_items(self):
        report = ConversionReport(
            low_confidence_items=[
                LowConfidenceItem(
                    block_id="abc123",
                    text="Some heading",
                    level=2,
                    page=3,
                    confidence=0.45,
                    reason="inherited",
                ),
            ],
        )
        data = json.loads(report.to_json())
        items = data["low_confidence_items"]
        assert len(items) == 1
        assert items[0]["block_id"] == "abc123"
        assert items[0]["confidence"] == 0.45

    def test_to_json_truncates_long_text(self):
        long_text = "A" * 200
        report = ConversionReport(
            low_confidence_items=[
                LowConfidenceItem(
                    block_id="x", text=long_text, level=1,
                    page=None, confidence=0.5, reason=None,
                ),
            ],
        )
        data = json.loads(report.to_json())
        assert len(data["low_confidence_items"][0]["text"]) == 80

    def test_empty_report_json(self):
        report = ConversionReport()
        data = json.loads(report.to_json())
        assert data["block_counts"]["headings"] == 0
        assert data["low_confidence_items"] == []
        assert data["warnings"] == []
