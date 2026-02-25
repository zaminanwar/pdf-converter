"""Conversion report — diagnostics and statistics from a conversion run."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LowConfidenceItem:
    """A heading flagged as low-confidence during classification."""

    block_id: str
    text: str
    level: int
    page: Optional[int]
    confidence: float
    reason: Optional[str]


@dataclass
class ConversionReport:
    """Summary of a PDF-to-Word conversion run."""

    # Source info
    source_file: str = ""
    page_count: int = 0

    # Timing
    parse_time_seconds: float = 0.0
    generate_time_seconds: float = 0.0
    total_time_seconds: float = 0.0

    # Block counts
    heading_count: int = 0
    paragraph_count: int = 0
    table_count: int = 0
    figure_count: int = 0
    list_count: int = 0

    # Heading level distribution: {level: count}
    headings_by_level: dict[int, int] = field(default_factory=dict)

    # Confidence diagnostics
    low_confidence_threshold: float = 0.7
    low_confidence_items: list[LowConfidenceItem] = field(default_factory=list)

    # Warnings collected during conversion
    warnings: list[str] = field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self._to_dict(), indent=indent)

    def _to_dict(self) -> dict:
        """Convert to a plain dict for JSON serialization."""
        return {
            "source_file": self.source_file,
            "page_count": self.page_count,
            "timing": {
                "parse_seconds": round(self.parse_time_seconds, 3),
                "generate_seconds": round(self.generate_time_seconds, 3),
                "total_seconds": round(self.total_time_seconds, 3),
            },
            "block_counts": {
                "headings": self.heading_count,
                "paragraphs": self.paragraph_count,
                "tables": self.table_count,
                "figures": self.figure_count,
                "lists": self.list_count,
            },
            "headings_by_level": {
                str(k): v for k, v in sorted(self.headings_by_level.items())
            },
            "low_confidence_items": [
                {
                    "block_id": item.block_id,
                    "text": item.text[:80],
                    "level": item.level,
                    "page": item.page,
                    "confidence": round(item.confidence, 2),
                    "reason": item.reason,
                }
                for item in self.low_confidence_items
            ],
            "warnings": self.warnings,
        }

    @classmethod
    def from_ir(
        cls, ir: "DocumentIR", low_confidence_threshold: float = 0.7
    ) -> ConversionReport:
        """Build a report by walking an IR tree."""
        report = cls(
            source_file=ir.metadata.source_file,
            page_count=ir.metadata.page_count,
            low_confidence_threshold=low_confidence_threshold,
        )
        _walk_blocks(ir.body, report)
        return report


def _walk_blocks(blocks: list, report: ConversionReport) -> None:
    """Recursively walk IR blocks to populate report counters."""
    from pdf_converter.ir.schema import (
        FigureBlock,
        HeadingBlock,
        ListBlock,
        ParagraphBlock,
        TableBlock,
    )

    for block in blocks:
        if isinstance(block, HeadingBlock):
            report.heading_count += 1
            report.headings_by_level[block.level] = (
                report.headings_by_level.get(block.level, 0) + 1
            )
            if block.confidence < report.low_confidence_threshold:
                report.low_confidence_items.append(
                    LowConfidenceItem(
                        block_id=block.id,
                        text=block.text,
                        level=block.level,
                        page=block.page,
                        confidence=block.confidence,
                        reason=block.classification_reason,
                    )
                )
            _walk_blocks(block.children, report)
        elif isinstance(block, ParagraphBlock):
            report.paragraph_count += 1
        elif isinstance(block, TableBlock):
            report.table_count += 1
        elif isinstance(block, FigureBlock):
            report.figure_count += 1
        elif isinstance(block, ListBlock):
            report.list_count += 1
