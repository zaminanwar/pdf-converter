"""Pydantic models for the Document Intermediate Representation (IR).

The IR is a tree-structured JSON format where headings contain their children,
mirroring Polarion ALM's work item hierarchy. This is the central contract
between the parser and generator stages.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


def _make_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------


class TextRun(BaseModel):
    """A span of text with optional inline formatting."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    superscript: bool = False
    subscript: bool = False
    highlight: Optional[str] = None  # colour name — for Polarion field extraction


# ---------------------------------------------------------------------------
# List items (recursive for nesting)
# ---------------------------------------------------------------------------


class ListItem(BaseModel):
    """A single list entry, optionally containing nested sub-items."""

    text: str
    runs: list[TextRun] = Field(default_factory=list)
    children: list[ListItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Table cells
# ---------------------------------------------------------------------------


class TableCell(BaseModel):
    """One cell in a table, identified by row/col with optional spanning."""

    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    text: str = ""
    runs: list[TextRun] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Block types (discriminated union via `type` field)
# ---------------------------------------------------------------------------


class ParagraphBlock(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    id: str = Field(default_factory=_make_id)
    page: Optional[int] = None
    text: str = ""
    runs: list[TextRun] = Field(default_factory=list)


class ListBlock(BaseModel):
    type: Literal["list"] = "list"
    id: str = Field(default_factory=_make_id)
    page: Optional[int] = None
    style: Literal["ordered", "unordered"] = "unordered"
    marker_format: Optional[str] = None  # "decimal", "lowerLetter", "upperLetter", "lowerRoman", "upperRoman"
    items: list[ListItem] = Field(default_factory=list)


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    id: str = Field(default_factory=_make_id)
    page: Optional[int] = None
    num_rows: int = 0
    num_cols: int = 0
    cells: list[TableCell] = Field(default_factory=list)


class FigureBlock(BaseModel):
    type: Literal["figure"] = "figure"
    id: str = Field(default_factory=_make_id)
    page: Optional[int] = None
    image_path: Optional[str] = None
    image_base64: Optional[str] = None  # fallback for portability
    caption: str = ""
    width_inches: Optional[float] = None
    height_inches: Optional[float] = None


class PageBreakBlock(BaseModel):
    type: Literal["page_break"] = "page_break"
    id: str = Field(default_factory=_make_id)
    page: Optional[int] = None


# Forward-ref: HeadingBlock contains children which can be any block type
# including other HeadingBlocks (for nested headings).

ContentBlock = Annotated[
    Union[ParagraphBlock, ListBlock, TableBlock, FigureBlock, PageBreakBlock],
    Field(discriminator="type"),
]


class HeadingBlock(BaseModel):
    type: Literal["heading"] = "heading"
    id: str = Field(default_factory=_make_id)
    page: Optional[int] = None
    level: int = Field(ge=1, le=9)
    text: str = ""
    runs: list[TextRun] = Field(default_factory=list)
    children: list[IRBlock] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    classification_reason: Optional[str] = None


# The top-level discriminated union of all block types
IRBlock = Annotated[
    Union[
        HeadingBlock,
        ParagraphBlock,
        ListBlock,
        TableBlock,
        FigureBlock,
        PageBreakBlock,
    ],
    Field(discriminator="type"),
]

# Rebuild HeadingBlock now that IRBlock is defined (recursive reference)
HeadingBlock.model_rebuild()


# ---------------------------------------------------------------------------
# Furniture (headers / footers)
# ---------------------------------------------------------------------------


class FurnitureType(str, Enum):
    HEADER = "header"
    FOOTER = "footer"


class FurnitureItem(BaseModel):
    type: FurnitureType
    text: str = ""
    pages: list[int] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Document metadata
# ---------------------------------------------------------------------------


class DocumentMetadata(BaseModel):
    source_file: str = ""
    source_hash: str = ""
    parser: str = ""
    parser_version: str = ""
    page_count: int = 0
    title: str = ""


# ---------------------------------------------------------------------------
# Top-level IR document
# ---------------------------------------------------------------------------


class DocumentIR(BaseModel):
    """The complete intermediate representation of a parsed PDF document."""

    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    body: list[IRBlock] = Field(default_factory=list)
    furniture: list[FurnitureItem] = Field(default_factory=list)

    def to_json(self, **kwargs) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json(indent=2, **kwargs)

    @classmethod
    def from_json(cls, json_str: str) -> DocumentIR:
        """Deserialize from JSON string."""
        return cls.model_validate_json(json_str)
