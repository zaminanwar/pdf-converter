"""Docling-based PDF parser implementation.

Uses IBM Docling (v2.70+) for structure-preserving PDF parsing.
The key algorithm is _build_heading_tree, which converts Docling's
flat document elements into a tree where headings contain their children.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pdf_converter.config import Config
from pdf_converter.exceptions import ParseError
from pdf_converter.ir.schema import (
    DocumentIR,
    DocumentMetadata,
    FigureBlock,
    FurnitureItem,
    FurnitureType,
    HeadingBlock,
    IRBlock,
    ListBlock,
    ListItem,
    PageBreakBlock,
    ParagraphBlock,
    TableBlock,
    TableCell,
    TextRun,
)
from pdf_converter.parsers.base import BasePdfParser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal data structure for accumulating list items before grouping
# ---------------------------------------------------------------------------

@dataclass
class _PendingListItem:
    """Temporary holder for a Docling list item before grouping."""
    text: str
    runs: list[TextRun] = field(default_factory=list)
    page: Optional[int] = None
    enumerated: bool = False
    marker: str = ""
    nesting_depth: int = 0


class DoclingParser(BasePdfParser):
    """PDF parser using IBM Docling for structure extraction."""

    def __init__(self, config: Config | None = None):
        super().__init__(config)
        self._docling_version: str | None = None

    @property
    def name(self) -> str:
        return "docling"

    @property
    def version(self) -> str:
        if self._docling_version is None:
            try:
                import importlib.metadata
                self._docling_version = importlib.metadata.version("docling")
            except Exception:
                self._docling_version = "unknown"
        return self._docling_version

    def parse(self, pdf_path: Path) -> DocumentIR:
        """Parse a PDF using Docling and return its IR.

        Args:
            pdf_path: Path to the input PDF file.

        Returns:
            DocumentIR with tree-structured body.

        Raises:
            ParseError: If Docling is not installed or parsing fails.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise ParseError(f"PDF file not found: {pdf_path}")

        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            raise ParseError(
                "Docling is not installed. Install with: pip install 'docling>=2.70'"
            )

        try:
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.base_models import InputFormat
            from docling.document_converter import PdfFormatOption

            pipeline_options = PdfPipelineOptions()
            if not self.config.parser.ocr_enabled:
                pipeline_options.do_ocr = False
            pipeline_options.generate_picture_images = True

            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options,
                    ),
                }
            )
            result = converter.convert(str(pdf_path))
            doc = result.document
        except Exception as exc:
            raise ParseError(f"Docling failed to parse {pdf_path}: {exc}") from exc

        return self._build_ir(doc, pdf_path)

    def _build_ir(self, doc, pdf_path: Path) -> DocumentIR:
        """Convert a Docling document object into our IR."""
        file_hash = self.file_hash(pdf_path)

        # Extract flat list of elements + furniture in a single pass
        elements, furniture, has_parts = self._extract_elements(doc, pdf_path)

        # Split headings that Docling merged with middle-dot separators
        elements = _split_compound_headings(elements)

        # Promote misclassified paragraphs with multi-level numbering
        elements = _promote_numbered_paragraphs(elements)

        # Promote list items with multi-level numbering to headings
        elements = _promote_numbered_list_items(elements)

        # Universal heading level assignment based on text content
        _resolve_heading_levels(elements, has_parts)

        # Group consecutive pending list items into ListBlocks
        elements = _group_list_items(elements)

        # Build tree structure where headings contain their children
        body = _build_heading_tree(elements)

        # Extract page count
        page_count = self._get_page_count(doc)

        # Extract title (first heading or document title)
        title = self._get_title(doc, body)

        metadata = DocumentMetadata(
            source_file=str(pdf_path.name),
            source_hash=file_hash,
            parser=self.name,
            parser_version=self.version,
            page_count=page_count,
            title=title,
        )

        return DocumentIR(metadata=metadata, body=body, furniture=furniture)

    def _extract_elements(
        self, doc, pdf_path: Path | None = None
    ) -> tuple[list, list[FurnitureItem], bool]:
        """Extract a flat list of IR blocks and furniture from a Docling document.

        Returns:
            Tuple of (elements, furniture, has_parts) where elements may contain
            _PendingListItem objects that need grouping, and has_parts indicates
            whether PART/CHAPTER structural markers were found.
        """
        elements: list = []
        furniture_map: dict[tuple[str, str], FurnitureItem] = {}
        has_parts = False

        try:
            from docling_core.types.doc import DocItemLabel
        except ImportError:
            raise ParseError(
                "docling-core is not installed. "
                "Install with: pip install 'docling-core>=2.0'"
            )

        for item, nesting_depth in doc.iterate_items():
            label = getattr(item, "label", None)
            page = self._get_page_number(item)
            text = self._get_text(item)

            # --- Furniture: collect in single pass, deduplicate by text ---
            if label == DocItemLabel.PAGE_HEADER and text.strip():
                key = (FurnitureType.HEADER, text.strip())
                if key in furniture_map:
                    if page and page not in furniture_map[key].pages:
                        furniture_map[key].pages.append(page)
                else:
                    furniture_map[key] = FurnitureItem(
                        type=FurnitureType.HEADER,
                        text=text.strip(),
                        pages=[page] if page else [],
                    )
                continue
            elif label == DocItemLabel.PAGE_FOOTER and text.strip():
                key = (FurnitureType.FOOTER, text.strip())
                if key in furniture_map:
                    if page and page not in furniture_map[key].pages:
                        furniture_map[key].pages.append(page)
                else:
                    furniture_map[key] = FurnitureItem(
                        type=FurnitureType.FOOTER,
                        text=text.strip(),
                        pages=[page] if page else [],
                    )
                continue

            # --- Content elements ---
            if label in (DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE):
                runs = self._extract_runs(item)
                # Placeholder level=2; resolved later by _resolve_heading_levels
                elements.append(
                    HeadingBlock(
                        level=2,
                        text=text,
                        page=page,
                        runs=runs,
                        confidence=0.85,
                        classification_reason=f"docling_label:{label.value}",
                    )
                )
                if _is_structural_marker(text):
                    has_parts = True
            elif label == DocItemLabel.LIST_ITEM:
                enumerated = getattr(item, "enumerated", False)
                marker = getattr(item, "marker", "")
                runs = self._extract_runs(item)
                elements.append(
                    _PendingListItem(
                        text=text,
                        runs=runs,
                        page=page,
                        enumerated=enumerated,
                        marker=str(marker) if marker else "",
                        nesting_depth=nesting_depth,
                    )
                )
            elif label == DocItemLabel.TABLE:
                table_block = self._convert_table(item, page, doc)
                if table_block:
                    elements.append(table_block)
            elif label == DocItemLabel.PICTURE:
                figure = self._convert_figure(item, doc, pdf_path, page)
                elements.append(figure)
            elif text.strip():
                runs = self._extract_runs(item)
                elements.append(
                    ParagraphBlock(text=text, page=page, runs=runs)
                )

        furniture = list(furniture_map.values())
        return elements, furniture, has_parts

    def _get_text(self, item) -> str:
        """Extract text content from a Docling item, normalizing whitespace."""
        if hasattr(item, "text"):
            return re.sub(r"[ \t]+", " ", item.text).strip()
        return ""

    def _get_page_number(self, item) -> Optional[int]:
        """Extract page number from a Docling item's provenance."""
        try:
            prov = getattr(item, "prov", None)
            if prov and len(prov) > 0:
                return prov[0].page_no
        except (AttributeError, IndexError):
            pass
        return None

    def _extract_runs(self, item) -> list[TextRun]:
        """Extract formatted text runs from a Docling item.

        Reads item.children or item.formatting to build TextRun objects
        with bold/italic/underline/strikethrough/superscript/subscript.
        """
        runs: list[TextRun] = []

        # Try children with formatting (Docling v2 structure)
        children = getattr(item, "children", None)
        if children:
            for child in children:
                child_text = getattr(child, "text", "")
                if not child_text:
                    continue
                fmt = getattr(child, "formatting", None)
                if fmt:
                    runs.append(TextRun(
                        text=child_text,
                        bold=getattr(fmt, "bold", False) or False,
                        italic=getattr(fmt, "italic", False) or False,
                        underline=getattr(fmt, "underline", False) or False,
                        strikethrough=getattr(fmt, "strikethrough", False) or False,
                        superscript=getattr(fmt, "script", None) == "superscript",
                        subscript=getattr(fmt, "script", None) == "subscript",
                    ))
                else:
                    runs.append(TextRun(text=child_text))

        # If no children produced runs, check if item has formatting directly
        if not runs:
            fmt = getattr(item, "formatting", None)
            if fmt:
                text = self._get_text(item)
                if text:
                    runs.append(TextRun(
                        text=text,
                        bold=getattr(fmt, "bold", False) or False,
                        italic=getattr(fmt, "italic", False) or False,
                        underline=getattr(fmt, "underline", False) or False,
                        strikethrough=getattr(fmt, "strikethrough", False) or False,
                        superscript=getattr(fmt, "script", None) == "superscript",
                        subscript=getattr(fmt, "script", None) == "subscript",
                    ))

        return runs

    def _convert_table(
        self, item, page: Optional[int], doc=None
    ) -> Optional[TableBlock]:
        """Convert a Docling table item to a TableBlock.

        Tries native table_cells first for accurate row/col spans,
        falls back to DataFrame export.
        """
        # Try native table cells with real spans
        native = self._convert_table_native(item, page)
        if native is not None:
            return native

        # Fallback: DataFrame
        return self._convert_table_dataframe(item, page)

    def _convert_table_native(
        self, item, page: Optional[int]
    ) -> Optional[TableBlock]:
        """Convert table using item.data.table_cells for real span info."""
        try:
            data = getattr(item, "data", None)
            if data is None:
                return None
            table_cells = getattr(data, "table_cells", None)
            if not table_cells:
                return None

            cells = []
            max_row = 0
            max_col = 0

            for tc in table_cells:
                r_start = getattr(tc, "start_row_offset_idx", 0)
                r_end = getattr(tc, "end_row_offset_idx", r_start + 1)
                c_start = getattr(tc, "start_col_offset_idx", 0)
                c_end = getattr(tc, "end_col_offset_idx", c_start + 1)
                text = getattr(tc, "text", "")
                text = re.sub(r"[ \t]+", " ", text).strip() if text else ""

                row_span = max(r_end - r_start, 1)
                col_span = max(c_end - c_start, 1)

                cells.append(
                    TableCell(
                        row=r_start,
                        col=c_start,
                        row_span=row_span,
                        col_span=col_span,
                        text=text,
                    )
                )

                max_row = max(max_row, r_start + row_span)
                max_col = max(max_col, c_start + col_span)

            if not cells:
                return None

            return TableBlock(
                page=page,
                num_rows=max_row,
                num_cols=max_col,
                cells=cells,
            )
        except Exception as exc:
            logger.debug("Native table conversion failed: %s", exc)
            return None

    def _convert_table_dataframe(
        self, item, page: Optional[int]
    ) -> Optional[TableBlock]:
        """Convert table using DataFrame export (fallback)."""
        try:
            table_data = item.export_to_dataframe()
            num_rows = len(table_data)
            num_cols = len(table_data.columns) if num_rows > 0 else 0

            cells = []

            # Check if column names are auto-generated integers (skip fake header)
            cols_are_auto = all(
                isinstance(c, int) for c in table_data.columns
            )

            if not cols_are_auto:
                # Add header row from column names
                for col_idx, col_name in enumerate(table_data.columns):
                    cells.append(
                        TableCell(row=0, col=col_idx, text=str(col_name))
                    )
                row_offset = 1
            else:
                row_offset = 0

            # Add data rows
            for row_idx, (_, row) in enumerate(table_data.iterrows()):
                for col_idx, value in enumerate(row):
                    cells.append(
                        TableCell(
                            row=row_idx + row_offset,
                            col=col_idx,
                            text=str(value),
                        )
                    )

            total_rows = num_rows + row_offset

            return TableBlock(
                page=page,
                num_rows=total_rows,
                num_cols=num_cols,
                cells=cells,
            )
        except Exception as exc:
            logger.warning("Failed to convert table: %s", exc)
            text = self._get_text(item)
            if text:
                return TableBlock(
                    page=page,
                    num_rows=1,
                    num_cols=1,
                    cells=[TableCell(row=0, col=0, text=text)],
                )
            return None

    def _convert_figure(
        self, item, doc, pdf_path: Optional[Path], page: Optional[int]
    ) -> FigureBlock:
        """Convert a Docling figure/picture item to a FigureBlock.

        Extracts the PIL image via item.get_image(doc) and saves it to disk.
        """
        caption = self._get_caption(item)
        image_path = None
        width_inches = None
        height_inches = None

        # Try to extract the actual image
        try:
            pil_image = item.get_image(doc)
            if pil_image is not None and pdf_path is not None:
                # Create images directory
                images_dir = pdf_path.parent / f"{pdf_path.stem}_images"
                images_dir.mkdir(exist_ok=True)

                # Generate filename from page number and item id
                item_id = getattr(item, "self_ref", None)
                if item_id:
                    img_name = f"fig_p{page or 0}_{str(item_id).replace('/', '_').replace('#', '')}.png"
                else:
                    import uuid
                    img_name = f"fig_p{page or 0}_{uuid.uuid4().hex[:8]}.png"

                img_path = images_dir / img_name
                pil_image.save(str(img_path), format="PNG")
                image_path = str(img_path)

                # Compute dimensions in inches
                dpi = pil_image.info.get("dpi", (96, 96))
                dpi_x = max(dpi[0], 72) if isinstance(dpi, tuple) else max(dpi, 72)
                dpi_y = max(dpi[1], 72) if isinstance(dpi, tuple) else max(dpi, 72)
                width_inches = pil_image.width / dpi_x
                height_inches = pil_image.height / dpi_y
        except Exception as exc:
            logger.debug("Could not extract image: %s", exc)

        return FigureBlock(
            page=page,
            caption=caption,
            image_path=image_path,
            width_inches=width_inches,
            height_inches=height_inches,
        )

    def _get_caption(self, item) -> str:
        """Extract caption text from a figure item."""
        # Docling v2: captions is a list of RefItem
        captions = getattr(item, "captions", None)
        if captions:
            parts = []
            for ref in captions:
                ref_text = getattr(ref, "text", None)
                if ref_text:
                    parts.append(str(ref_text))
                else:
                    parts.append(str(ref))
            return " ".join(parts)

        # Fallback: single caption attribute
        caption = getattr(item, "caption", None)
        if caption:
            return str(caption)
        return ""

    def _get_page_count(self, doc) -> int:
        """Get total page count from the Docling document."""
        try:
            return doc.num_pages()
        except (AttributeError, TypeError):
            pass
        try:
            pages = getattr(doc, "pages", None)
            if pages:
                return len(pages)
        except (AttributeError, TypeError):
            pass
        return 0

    def _get_title(self, doc, body: list[IRBlock]) -> str:
        """Extract document title from Docling doc or first heading."""
        # Try Docling's title
        try:
            title = getattr(doc, "title", None)
            if title:
                return str(title)
        except AttributeError:
            pass

        # Fall back to first heading
        for block in body:
            if isinstance(block, HeadingBlock):
                return block.text

        return ""


# ---------------------------------------------------------------------------
# Heading numbering detection
# ---------------------------------------------------------------------------

def _level_from_numbering(text: str) -> Optional[int]:
    """Infer heading level from section numbering in text.

    Matches patterns like:
    - "1. Introduction" → level 1
    - "1.2 Scope" → level 2
    - "1.2.3 Details" → level 3
    - "A.1 Section" → level 2
    - "B.2.1 Sub" → level 3

    Does NOT match:
    - "1 Week Lookback" (digit followed by non-section word)
    - "100 items" (number without dot and without uppercase section start)
    """
    # Bare section numbers: entire text is just "2.2" or "2.2." etc.
    bare = re.match(r"^(\d+(?:\.\d+)+)\.?\s*$", text.strip())
    if bare:
        parts = bare.group(1).split(".")
        return min(len(parts), 9)

    # Numbered sections: 1. or 1.2 or 1.2.3 followed by space+letter or end
    match = re.match(r"^(\d+(?:\.\d+)*)(\.?\s+\S)", text)
    if match:
        parts = match.group(1).split(".")
        # Single number like "1 Week" — require trailing dot: "1. " or "1.x"
        # Exceptions that ARE headings:
        #   "3 QUALITY CONTROL" — number + ALL-CAPS text
        #   "1 Locomotives Affected" — single digit + capitalized word (5+ chars)
        if len(parts) == 1:
            if not re.match(r"^\d+\.\s", text) and not re.match(r"^\d+\.\d", text):
                # Allow: single digit + space + capitalized word of 5+ chars
                # e.g. "3 Safety Instructions", "1 Locomotives Affected"
                # Rejects: "1 Week Lookback", "2 Way valve"
                if not re.match(r"^\d+\s+[A-Z]{2}", text):
                    if not re.match(r"^\d\s+[A-Z][a-z]{4,}", text):
                        return None
        return min(len(parts), 9)

    # Letter-prefixed: A.1, B.2.1
    match = re.match(r"^[A-Z]\.(\d+(?:\.\d+)*)\s", text)
    if match:
        parts = match.group(1).split(".")
        return min(len(parts) + 1, 9)

    return None


# ---------------------------------------------------------------------------
# Structural marker detection
# ---------------------------------------------------------------------------

_STRUCTURAL_MARKER_RE = re.compile(
    r"^(?:PART|CHAPTER)\s+(?:[IVXLCDM]+|\d+)\b", re.IGNORECASE
)
_LEVEL1_STRUCTURAL_RE = re.compile(
    r"^(?:PART|CHAPTER|APPENDIX|EXHIBIT|ANNEX)\s+(?:[IVXLCDM]+|[A-Z]|\d+)\b",
    re.IGNORECASE,
)


def _is_structural_marker(text: str) -> bool:
    """PART/CHAPTER markers (triggers has_parts offset)."""
    return bool(_STRUCTURAL_MARKER_RE.match(text.strip()))


def _is_level1_structural(text: str) -> bool:
    """Any structural marker that should be level 1 (includes APPENDIX etc.)."""
    return bool(_LEVEL1_STRUCTURAL_RE.match(text.strip()))


# ---------------------------------------------------------------------------
# Split compound headings (middle-dot merged by Docling)
# ---------------------------------------------------------------------------

_COMPOUND_SEP_RE = re.compile(r"\s+[·•]\s+")


def _split_compound_headings(elements: list) -> list:
    """Split headings that Docling merged via middle-dot/bullet separators.

    E.g. "PAY APPLICATIONS · Managed in Aconex" becomes:
    - HeadingBlock("PAY APPLICATIONS")
    - ParagraphBlock("Managed in Aconex")
    """
    result = []
    for el in elements:
        if isinstance(el, HeadingBlock) and _COMPOUND_SEP_RE.search(el.text):
            parts = _COMPOUND_SEP_RE.split(el.text, maxsplit=1)
            el.text = parts[0].strip()
            el.runs = []  # clear stale runs
            el.confidence = min(el.confidence, 0.75)
            prev = el.classification_reason or "unknown"
            el.classification_reason = f"{prev}; compound_split"
            result.append(el)
            result.append(ParagraphBlock(text=parts[1].strip(), page=el.page))
        else:
            result.append(el)
    return result


# ---------------------------------------------------------------------------
# Promote numbered paragraphs to headings
# ---------------------------------------------------------------------------

_MULTI_LEVEL_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+\S")


def _promote_numbered_paragraphs(elements: list) -> list:
    """Promote ParagraphBlocks starting with multi-level numbering (2+ parts)
    to HeadingBlock. Catches items Docling misclassified as text.

    Only multi-level numbers (e.g. 1.1, 1.2.3) are promoted — single-level
    numbers (e.g. "1. something") are left alone to avoid false positives.

    For 3+ part numbers (e.g. 1.3.1.2) there is no length limit — these are
    unambiguous section markers. For 2-part numbers (e.g. 1.2) the 120-char
    limit is kept to avoid false positives like "1.2 billion dollars...".
    """
    result = []
    for el in elements:
        if isinstance(el, ParagraphBlock):
            match = _MULTI_LEVEL_NUMBER_RE.match(el.text)
            if match:
                parts_count = len(match.group(1).split("."))
                if parts_count >= 3:
                    conf = 0.90
                    reason = f"promoted:multi_level_{parts_count}_parts"
                elif len(el.text) < 120:
                    conf = 0.70
                    reason = f"promoted:two_level_{len(el.text)}_chars"
                else:
                    result.append(el)
                    continue
                result.append(
                    HeadingBlock(
                        level=2,  # placeholder, resolved later
                        text=el.text,
                        page=el.page,
                        runs=el.runs,
                        confidence=conf,
                        classification_reason=reason,
                    )
                )
                continue
        result.append(el)
    return result


# ---------------------------------------------------------------------------
# Promote numbered list items to headings
# ---------------------------------------------------------------------------

def _promote_numbered_list_items(elements: list) -> list:
    """Promote _PendingListItem entries starting with multi-level numbering to HeadingBlock.

    Docling sometimes classifies numbered sections (e.g. "8.1.2 Open the panel...")
    as list items rather than headings. This catches them the same way
    _promote_numbered_paragraphs catches misclassified paragraphs.
    """
    result = []
    for el in elements:
        if isinstance(el, _PendingListItem):
            match = _MULTI_LEVEL_NUMBER_RE.match(el.text)
            if match:
                parts_count = len(match.group(1).split("."))
                if parts_count >= 3:
                    conf = 0.85
                    reason = f"promoted_list_item:multi_level_{parts_count}_parts"
                elif len(el.text) < 120:
                    conf = 0.65
                    reason = f"promoted_list_item:two_level_{len(el.text)}_chars"
                else:
                    result.append(el)
                    continue
                result.append(
                    HeadingBlock(
                        level=2,  # placeholder, resolved later
                        text=el.text,
                        page=el.page,
                        runs=el.runs,
                        confidence=conf,
                        classification_reason=reason,
                    )
                )
                continue
        result.append(el)
    return result


# ---------------------------------------------------------------------------
# Universal heading level resolution
# ---------------------------------------------------------------------------


def _resolve_heading_levels(elements: list, has_parts: bool) -> None:
    """Assign heading levels based on text content only.

    Mutates HeadingBlock.level in-place.

    Rules (in priority order):
    1. Structural markers (PART, APPENDIX, etc.) → level 1
    2. Section numbering (1., 1.1, 1.2.3) → count of parts (+ offset if has_parts)
    3. First heading in document → level 1 (document title)
    4. Unnumbered heading → inherit last_level
    """
    level_offset = 1 if has_parts else 0
    first_heading_seen = False
    last_level = 2

    for el in elements:
        if not isinstance(el, HeadingBlock):
            continue

        level_reason: str
        if _is_level1_structural(el.text):
            el.level = 1
            el.confidence = max(el.confidence, 0.95)
            level_reason = "structural_marker"
        else:
            num_level = _level_from_numbering(el.text)
            if num_level is not None:
                el.level = min(num_level + level_offset, 9)
                level_reason = f"numbering:{num_level}+offset_{level_offset}"
            elif not first_heading_seen:
                el.level = 1  # document title
                el.confidence = min(el.confidence, 0.80)
                level_reason = "first_heading_as_title"
            else:
                el.level = last_level  # inherit
                el.confidence = min(el.confidence, 0.50)
                level_reason = f"inherited_{last_level}"

        if el.classification_reason:
            el.classification_reason += f"; level:{level_reason}"
        else:
            el.classification_reason = f"level:{level_reason}"

        last_level = el.level
        first_heading_seen = True


# ---------------------------------------------------------------------------
# List grouping
# ---------------------------------------------------------------------------

def _detect_marker_format(items: list[_PendingListItem]) -> Optional[str]:
    """Detect the numbering format from list item markers.

    Inspects the first few items' marker fields to determine the format:
    - a. / b. / a) / b) → "lowerLetter"
    - A. / B. / A) / B) → "upperLetter"
    - i. / ii. / iii. / iv. → "lowerRoman"
    - I. / II. / III. → "upperRoman"
    - else → None (default decimal)
    """
    _LOWER_LETTER_RE = re.compile(r"^[a-z][.)]")
    _UPPER_LETTER_RE = re.compile(r"^[A-Z][.)]")
    _LOWER_ROMAN_RE = re.compile(r"^(?:i{1,3}|iv|vi{0,3}|ix|x)[.)]", re.IGNORECASE)

    for item in items[:3]:
        m = item.marker.strip()
        if not m:
            continue
        if _LOWER_ROMAN_RE.match(m) and m[0].islower():
            return "lowerRoman"
        if _LOWER_LETTER_RE.match(m):
            return "lowerLetter"
        if _LOWER_ROMAN_RE.match(m) and m[0].isupper():
            return "upperRoman"
        if _UPPER_LETTER_RE.match(m):
            return "upperLetter"
        # Has a marker but didn't match letter/roman → decimal
        return None
    return None


def _group_list_items(elements: list) -> list[IRBlock]:
    """Group consecutive _PendingListItem into ListBlock with nested items.

    Uses nesting_depth to create the list hierarchy.
    """
    result: list[IRBlock] = []
    pending: list[_PendingListItem] = []

    def flush_pending():
        if not pending:
            return
        # Determine if ordered based on first item
        ordered = pending[0].enumerated
        style = "ordered" if ordered else "unordered"
        page = pending[0].page

        marker_format = _detect_marker_format(pending) if ordered else None
        items = _nest_list_items(pending)
        result.append(ListBlock(
            style=style, items=items, page=page, marker_format=marker_format,
        ))
        pending.clear()

    for el in elements:
        if isinstance(el, _PendingListItem):
            pending.append(el)
        else:
            flush_pending()
            result.append(el)

    flush_pending()
    return result


def _nest_list_items(pending: list[_PendingListItem]) -> list[ListItem]:
    """Convert flat pending items with nesting_depth into nested ListItems."""
    if not pending:
        return []

    root_items: list[ListItem] = []
    # Stack of (depth, ListItem)
    stack: list[tuple[int, ListItem]] = []

    base_depth = pending[0].nesting_depth

    for p in pending:
        li = ListItem(text=p.text, runs=p.runs)
        depth = p.nesting_depth - base_depth

        # Pop stack until we find a parent at a lower depth
        while stack and stack[-1][0] >= depth:
            stack.pop()

        if stack:
            stack[-1][1].children.append(li)
        else:
            root_items.append(li)

        stack.append((depth, li))

    return root_items


# ---------------------------------------------------------------------------
# Heading tree builder
# ---------------------------------------------------------------------------

def _build_heading_tree(flat_elements: list[IRBlock]) -> list[IRBlock]:
    """Convert a flat list of blocks into a tree where headings contain children.

    Uses a stack-based algorithm:
    - When encountering a heading, pop from the stack until we find a heading
      with a lower level (the parent), then nest under it.
    - Non-heading blocks are always added as children of the most recent heading,
      or at root level if no heading has appeared yet.

    Args:
        flat_elements: Flat list of IR blocks from the parser.

    Returns:
        Tree-structured list of IR blocks.
    """
    if not flat_elements:
        return []

    # Stack of (level, block) — level=0 means root
    root: list[IRBlock] = []
    # Stack tracks the current heading chain: [(level, heading_block), ...]
    stack: list[tuple[int, HeadingBlock]] = []

    for block in flat_elements:
        if isinstance(block, HeadingBlock):
            # Pop stack until we find a heading with a strictly lower level
            while stack and stack[-1][0] >= block.level:
                stack.pop()

            if stack:
                # Nest under the parent heading
                stack[-1][1].children.append(block)
            else:
                # Top-level heading
                root.append(block)

            stack.append((block.level, block))
        else:
            # Non-heading: add as child of current heading, or root
            if stack:
                stack[-1][1].children.append(block)
            else:
                root.append(block)

    return root
