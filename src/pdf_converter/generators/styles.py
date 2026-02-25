"""Polarion-optimized Word document style management.

Handles heading styles (H1-H9), list styles (bullet/number, levels 1-3),
and other Polarion-specific formatting concerns.
"""

from __future__ import annotations

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from pdf_converter.config import StyleConfig


def heading_style_name(config: StyleConfig, level: int) -> str:
    """Return the Word style name for a heading level (e.g. 'Heading 1')."""
    return f"{config.heading_prefix} {level}"


def list_style_name(config: StyleConfig, ordered: bool, level: int = 1) -> str:
    """Return the Word style name for a list item.

    Args:
        config: Style configuration.
        ordered: True for numbered lists, False for bulleted.
        level: Nesting level (1-3). Levels > 1 get ' 2', ' 3' suffix.
    """
    base = config.list_number_style if ordered else config.list_bullet_style
    if level <= 1:
        return base
    return f"{base} {level}"


def ensure_styles_exist(doc: Document, config: StyleConfig) -> None:
    """Ensure the document has all required list numbering definitions.

    python-docx creates heading styles on demand, but bullet/number list
    styles need abstract numbering definitions to actually render bullets.
    This creates bullet and number abstract numbering with 3 indent levels.
    """
    numbering_part = doc.part.numbering_part
    numbering_elem = numbering_part._element

    # Create bullet numbering definition
    _create_bullet_numbering(numbering_elem)
    # Create number numbering definition
    _create_number_numbering(numbering_elem)
    # Create letter numbering definitions
    _create_lower_letter_numbering(numbering_elem)
    _create_upper_letter_numbering(numbering_elem)


def _create_bullet_numbering(numbering_elem) -> None:
    """Create an abstract numbering definition for bullets (3 levels)."""
    bullet_chars = ["\u2022", "\u25CB", "\u25AA"]  # bullet, circle, square
    abstract_num_id = "100"

    abstract_num = OxmlElement("w:abstractNum")
    abstract_num.set(qn("w:abstractNumId"), abstract_num_id)

    for i in range(3):
        lvl = OxmlElement("w:lvl")
        lvl.set(qn("w:ilvl"), str(i))

        start = OxmlElement("w:start")
        start.set(qn("w:val"), "1")
        lvl.append(start)

        num_fmt = OxmlElement("w:numFmt")
        num_fmt.set(qn("w:val"), "bullet")
        lvl.append(num_fmt)

        lvl_text = OxmlElement("w:lvlText")
        lvl_text.set(qn("w:val"), bullet_chars[i])
        lvl.append(lvl_text)

        lvl_jc = OxmlElement("w:lvlJc")
        lvl_jc.set(qn("w:val"), "left")
        lvl.append(lvl_jc)

        ppr = OxmlElement("w:pPr")
        ind = OxmlElement("w:ind")
        left = str(720 * (i + 1))
        ind.set(qn("w:left"), left)
        ind.set(qn("w:hanging"), "360")
        ppr.append(ind)
        lvl.append(ppr)

        abstract_num.append(lvl)

    numbering_elem.insert(0, abstract_num)

    # Create concrete num referencing this abstract
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), abstract_num_id)
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), abstract_num_id)
    num.append(abstract_ref)
    numbering_elem.append(num)


def _create_number_numbering(numbering_elem) -> None:
    """Create an abstract numbering definition for ordered lists (3 levels)."""
    formats = ["decimal", "lowerLetter", "lowerRoman"]
    texts = ["%1.", "%2.", "%3."]
    abstract_num_id = "101"

    abstract_num = OxmlElement("w:abstractNum")
    abstract_num.set(qn("w:abstractNumId"), abstract_num_id)

    for i in range(3):
        lvl = OxmlElement("w:lvl")
        lvl.set(qn("w:ilvl"), str(i))

        start = OxmlElement("w:start")
        start.set(qn("w:val"), "1")
        lvl.append(start)

        num_fmt = OxmlElement("w:numFmt")
        num_fmt.set(qn("w:val"), formats[i])
        lvl.append(num_fmt)

        lvl_text = OxmlElement("w:lvlText")
        lvl_text.set(qn("w:val"), texts[i])
        lvl.append(lvl_text)

        lvl_jc = OxmlElement("w:lvlJc")
        lvl_jc.set(qn("w:val"), "left")
        lvl.append(lvl_jc)

        ppr = OxmlElement("w:pPr")
        ind = OxmlElement("w:ind")
        left = str(720 * (i + 1))
        ind.set(qn("w:left"), left)
        ind.set(qn("w:hanging"), "360")
        ppr.append(ind)
        lvl.append(ppr)

        abstract_num.append(lvl)

    numbering_elem.insert(0, abstract_num)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), abstract_num_id)
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), abstract_num_id)
    num.append(abstract_ref)
    numbering_elem.append(num)


def _create_lower_letter_numbering(numbering_elem) -> None:
    """Create an abstract numbering definition for lower-letter lists (a, b, c)."""
    formats = ["lowerLetter", "lowerRoman", "decimal"]
    texts = ["%1.", "%2.", "%3."]
    abstract_num_id = "102"

    abstract_num = OxmlElement("w:abstractNum")
    abstract_num.set(qn("w:abstractNumId"), abstract_num_id)

    for i in range(3):
        lvl = OxmlElement("w:lvl")
        lvl.set(qn("w:ilvl"), str(i))

        start = OxmlElement("w:start")
        start.set(qn("w:val"), "1")
        lvl.append(start)

        num_fmt = OxmlElement("w:numFmt")
        num_fmt.set(qn("w:val"), formats[i])
        lvl.append(num_fmt)

        lvl_text = OxmlElement("w:lvlText")
        lvl_text.set(qn("w:val"), texts[i])
        lvl.append(lvl_text)

        lvl_jc = OxmlElement("w:lvlJc")
        lvl_jc.set(qn("w:val"), "left")
        lvl.append(lvl_jc)

        ppr = OxmlElement("w:pPr")
        ind = OxmlElement("w:ind")
        left = str(720 * (i + 1))
        ind.set(qn("w:left"), left)
        ind.set(qn("w:hanging"), "360")
        ppr.append(ind)
        lvl.append(ppr)

        abstract_num.append(lvl)

    numbering_elem.insert(0, abstract_num)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), abstract_num_id)
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), abstract_num_id)
    num.append(abstract_ref)
    numbering_elem.append(num)


def _create_upper_letter_numbering(numbering_elem) -> None:
    """Create an abstract numbering definition for upper-letter lists (A, B, C)."""
    formats = ["upperLetter", "upperRoman", "decimal"]
    texts = ["%1.", "%2.", "%3."]
    abstract_num_id = "103"

    abstract_num = OxmlElement("w:abstractNum")
    abstract_num.set(qn("w:abstractNumId"), abstract_num_id)

    for i in range(3):
        lvl = OxmlElement("w:lvl")
        lvl.set(qn("w:ilvl"), str(i))

        start = OxmlElement("w:start")
        start.set(qn("w:val"), "1")
        lvl.append(start)

        num_fmt = OxmlElement("w:numFmt")
        num_fmt.set(qn("w:val"), formats[i])
        lvl.append(num_fmt)

        lvl_text = OxmlElement("w:lvlText")
        lvl_text.set(qn("w:val"), texts[i])
        lvl.append(lvl_text)

        lvl_jc = OxmlElement("w:lvlJc")
        lvl_jc.set(qn("w:val"), "left")
        lvl.append(lvl_jc)

        ppr = OxmlElement("w:pPr")
        ind = OxmlElement("w:ind")
        left = str(720 * (i + 1))
        ind.set(qn("w:left"), left)
        ind.set(qn("w:hanging"), "360")
        ppr.append(ind)
        lvl.append(ppr)

        abstract_num.append(lvl)

    numbering_elem.insert(0, abstract_num)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), abstract_num_id)
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), abstract_num_id)
    num.append(abstract_ref)
    numbering_elem.append(num)


def apply_list_numbering(
    paragraph, doc: Document, ordered: bool, level: int = 1,
    marker_format: str | None = None,
) -> None:
    """Apply <w:numPr> to a paragraph so bullets/numbers actually render.

    Args:
        paragraph: The python-docx paragraph to modify.
        doc: The document (for numbering part reference).
        ordered: True for numbered list, False for bullet.
        level: 1-based nesting level (converted to 0-based ilvl).
    """
    if not ordered:
        num_id = "100"
    elif marker_format == "lowerLetter":
        num_id = "102"
    elif marker_format == "upperLetter":
        num_id = "103"
    else:
        num_id = "101"
    ilvl = max(level - 1, 0)

    pPr = paragraph._element.get_or_add_pPr()
    numPr = OxmlElement("w:numPr")
    ilvl_elem = OxmlElement("w:ilvl")
    ilvl_elem.set(qn("w:val"), str(ilvl))
    numPr.append(ilvl_elem)
    numId_elem = OxmlElement("w:numId")
    numId_elem.set(qn("w:val"), num_id)
    numPr.append(numId_elem)
    pPr.append(numPr)


def apply_highlight(run, color_name: str) -> None:
    """Apply a highlight colour to a run via OOXML <w:highlight>.

    Args:
        run: The python-docx Run object.
        color_name: A Word highlight colour name (e.g. 'yellow', 'green', 'cyan').
    """
    rPr = run._element.get_or_add_rPr()
    highlight = OxmlElement("w:highlight")
    highlight.set(qn("w:val"), color_name)
    rPr.append(highlight)


def apply_caption_formatting(paragraph, config: StyleConfig) -> None:
    """Apply caption formatting (italic) to a paragraph."""
    paragraph.style = doc_style_or_fallback(
        paragraph.part.document, config.caption_style, config.body_style
    )
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in paragraph.runs:
        run.italic = True


def doc_style_or_fallback(
    doc: Document, style_name: str, fallback: str = "Normal"
) -> str:
    """Return style_name if it exists in doc, otherwise fallback."""
    try:
        doc.styles[style_name]
        return style_name
    except KeyError:
        return fallback
