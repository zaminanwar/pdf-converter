"""Tests for parser base class, factory, and the heading tree algorithm.

These tests don't require Docling — they test the heading tree builder
with hand-crafted flat element lists, and the factory/base class logic.
"""

import pytest

from pdf_converter.config import Config
from pdf_converter.exceptions import ConfigError
from pdf_converter.ir.schema import (
    FigureBlock,
    HeadingBlock,
    ListBlock,
    ListItem,
    PageBreakBlock,
    ParagraphBlock,
    TableBlock,
    TableCell,
)
from pdf_converter.parsers.base import BasePdfParser
from pdf_converter.parsers.docling_parser import (
    _build_heading_tree,
    _detect_marker_format,
    _group_list_items,
    _is_level1_structural,
    _is_structural_marker,
    _level_from_numbering,
    _PendingListItem,
    _promote_numbered_list_items,
    _promote_numbered_paragraphs,
    _resolve_heading_levels,
    _split_compound_headings,
)
from pdf_converter.parsers.factory import create_parser


# ---------------------------------------------------------------------------
# _build_heading_tree algorithm tests
# ---------------------------------------------------------------------------

class TestBuildHeadingTree:
    def test_empty_input(self):
        assert _build_heading_tree([]) == []

    def test_single_paragraph(self):
        """A lone paragraph stays at root level."""
        p = ParagraphBlock(text="Hello")
        result = _build_heading_tree([p])
        assert len(result) == 1
        assert result[0].text == "Hello"

    def test_single_heading_no_children(self):
        h = HeadingBlock(level=1, text="Title")
        result = _build_heading_tree([h])
        assert len(result) == 1
        assert result[0].text == "Title"
        assert result[0].children == []

    def test_heading_with_paragraph_child(self):
        """Paragraph after a heading becomes its child."""
        elements = [
            HeadingBlock(level=1, text="H1"),
            ParagraphBlock(text="Under H1"),
        ]
        result = _build_heading_tree(elements)
        assert len(result) == 1
        assert result[0].text == "H1"
        assert len(result[0].children) == 1
        assert result[0].children[0].text == "Under H1"

    def test_nested_headings(self):
        """H2 under H1, with content under each."""
        elements = [
            HeadingBlock(level=1, text="H1"),
            ParagraphBlock(text="P1"),
            HeadingBlock(level=2, text="H2"),
            ParagraphBlock(text="P2"),
        ]
        result = _build_heading_tree(elements)
        assert len(result) == 1

        h1 = result[0]
        assert h1.text == "H1"
        assert len(h1.children) == 2  # P1 + H2

        assert h1.children[0].text == "P1"

        h2 = h1.children[1]
        assert h2.text == "H2"
        assert len(h2.children) == 1
        assert h2.children[0].text == "P2"

    def test_sibling_headings(self):
        """Two H1s at the same level are siblings at root."""
        elements = [
            HeadingBlock(level=1, text="Chapter 1"),
            ParagraphBlock(text="Content 1"),
            HeadingBlock(level=1, text="Chapter 2"),
            ParagraphBlock(text="Content 2"),
        ]
        result = _build_heading_tree(elements)
        assert len(result) == 2
        assert result[0].text == "Chapter 1"
        assert result[1].text == "Chapter 2"
        assert result[0].children[0].text == "Content 1"
        assert result[1].children[0].text == "Content 2"

    def test_deep_nesting(self):
        """H1 > H2 > H3 with content at each level."""
        elements = [
            HeadingBlock(level=1, text="H1"),
            ParagraphBlock(text="Under H1"),
            HeadingBlock(level=2, text="H2"),
            ParagraphBlock(text="Under H2"),
            HeadingBlock(level=3, text="H3"),
            ParagraphBlock(text="Under H3"),
        ]
        result = _build_heading_tree(elements)
        assert len(result) == 1

        h1 = result[0]
        assert len(h1.children) == 2  # P + H2

        h2 = h1.children[1]
        assert h2.text == "H2"
        assert len(h2.children) == 2  # P + H3

        h3 = h2.children[1]
        assert h3.text == "H3"
        assert len(h3.children) == 1
        assert h3.children[0].text == "Under H3"

    def test_level_skip(self):
        """H1 followed by H3 (skipping H2) — H3 nests under H1."""
        elements = [
            HeadingBlock(level=1, text="H1"),
            HeadingBlock(level=3, text="H3"),
            ParagraphBlock(text="Content"),
        ]
        result = _build_heading_tree(elements)
        assert len(result) == 1
        h1 = result[0]
        assert len(h1.children) == 1
        h3 = h1.children[0]
        assert h3.text == "H3"
        assert h3.children[0].text == "Content"

    def test_pop_back_to_higher_level(self):
        """H1 > H2 > content, then H1 again pops back to root."""
        elements = [
            HeadingBlock(level=1, text="Chapter 1"),
            HeadingBlock(level=2, text="Section 1.1"),
            ParagraphBlock(text="Details"),
            HeadingBlock(level=1, text="Chapter 2"),
            ParagraphBlock(text="New chapter"),
        ]
        result = _build_heading_tree(elements)
        assert len(result) == 2

        ch1 = result[0]
        assert ch1.text == "Chapter 1"
        assert len(ch1.children) == 1
        assert ch1.children[0].text == "Section 1.1"

        ch2 = result[1]
        assert ch2.text == "Chapter 2"
        assert ch2.children[0].text == "New chapter"

    def test_mixed_block_types(self):
        """Various block types nest correctly under headings."""
        elements = [
            HeadingBlock(level=1, text="H1"),
            ParagraphBlock(text="Para"),
            TableBlock(num_rows=1, num_cols=1, cells=[TableCell(row=0, col=0, text="A")]),
            FigureBlock(caption="Fig"),
            PageBreakBlock(),
        ]
        result = _build_heading_tree(elements)
        assert len(result) == 1
        h1 = result[0]
        assert len(h1.children) == 4
        assert h1.children[0].type == "paragraph"
        assert h1.children[1].type == "table"
        assert h1.children[2].type == "figure"
        assert h1.children[3].type == "page_break"

    def test_paragraphs_before_any_heading(self):
        """Content before any heading stays at root level."""
        elements = [
            ParagraphBlock(text="Preamble"),
            HeadingBlock(level=1, text="H1"),
            ParagraphBlock(text="Under H1"),
        ]
        result = _build_heading_tree(elements)
        assert len(result) == 2
        assert result[0].text == "Preamble"
        assert result[1].text == "H1"
        assert result[1].children[0].text == "Under H1"

    def test_realistic_document_structure(self):
        """Simulates a real requirements document structure."""
        elements = [
            HeadingBlock(level=1, text="1. Introduction"),
            ParagraphBlock(text="This document..."),
            HeadingBlock(level=2, text="1.1 Purpose"),
            ParagraphBlock(text="The purpose is..."),
            HeadingBlock(level=2, text="1.2 Scope"),
            ParagraphBlock(text="The scope covers..."),
            HeadingBlock(level=1, text="2. Requirements"),
            HeadingBlock(level=2, text="2.1 Functional"),
            TableBlock(num_rows=2, num_cols=2, cells=[
                TableCell(row=0, col=0, text="ID"),
                TableCell(row=0, col=1, text="Description"),
                TableCell(row=1, col=0, text="REQ-001"),
                TableCell(row=1, col=1, text="The system shall..."),
            ]),
            HeadingBlock(level=2, text="2.2 Non-Functional"),
            ParagraphBlock(text="Performance targets..."),
            HeadingBlock(level=1, text="3. Appendix"),
            FigureBlock(caption="Architecture diagram"),
        ]
        result = _build_heading_tree(elements)

        assert len(result) == 3  # 3 top-level headings

        intro = result[0]
        assert intro.text == "1. Introduction"
        assert len(intro.children) == 3  # paragraph + 2 sub-headings

        reqs = result[1]
        assert reqs.text == "2. Requirements"
        assert len(reqs.children) == 2  # 2 sub-headings
        assert reqs.children[0].children[0].type == "table"

        appendix = result[2]
        assert appendix.text == "3. Appendix"
        assert appendix.children[0].type == "figure"


# ---------------------------------------------------------------------------
# _level_from_numbering tests
# ---------------------------------------------------------------------------

class TestLevelFromNumbering:
    def test_single_number_with_dot(self):
        assert _level_from_numbering("1. Introduction") == 1

    def test_two_level_numbering(self):
        assert _level_from_numbering("1.2 Scope") == 2

    def test_three_level_numbering(self):
        assert _level_from_numbering("1.2.3 Details") == 3

    def test_no_false_positive_week(self):
        """'1 Week Lookback' must NOT match as a heading number."""
        assert _level_from_numbering("1 Week Lookback") is None

    def test_no_false_positive_plain_number(self):
        """'100 items' must NOT match."""
        assert _level_from_numbering("100 items") is None

    def test_letter_prefix_a1(self):
        assert _level_from_numbering("A.1 Section") == 2

    def test_letter_prefix_b21(self):
        assert _level_from_numbering("B.2.1 Sub") == 3

    def test_no_match_plain_text(self):
        assert _level_from_numbering("RFI's") is None

    def test_no_match_all_caps(self):
        assert _level_from_numbering("SUBMITTALS") is None

    def test_quote_after_number(self):
        """'2. 'TURNOVER' PHASE' should match as level 1."""
        assert _level_from_numbering("2. 'TURNOVER' PHASE") == 1

    def test_dotless_single_number_all_caps(self):
        """'3 QUALITY CONTROL PLAN' (no dot) should match as level 1."""
        assert _level_from_numbering("3 QUALITY CONTROL PLAN") == 1

    def test_dotless_single_number_lowercase_no_match(self):
        """'1 Week Lookback' should still NOT match."""
        assert _level_from_numbering("1 Week Lookback") is None

    def test_dotless_single_number_short_lower_no_match(self):
        """'3 day notice' should NOT match."""
        assert _level_from_numbering("3 day notice") is None


# ---------------------------------------------------------------------------
# _resolve_heading_levels tests
# ---------------------------------------------------------------------------


class TestResolveHeadingLevels:
    def test_first_heading_gets_level_1(self):
        """An unnamed first heading becomes H1 (document title)."""
        elements = [HeadingBlock(level=2, text="Design Builder Services")]
        _resolve_heading_levels(elements, has_parts=False)
        assert elements[0].level == 1

    def test_numbered_without_parts(self):
        """Without PART markers: 1.→H1, 1.1→H2, 1.1.1→H3."""
        elements = [
            HeadingBlock(level=2, text="1. Introduction"),
            HeadingBlock(level=2, text="1.1 Purpose"),
            HeadingBlock(level=2, text="1.1.1 Sub-purpose"),
        ]
        _resolve_heading_levels(elements, has_parts=False)
        assert elements[0].level == 1
        assert elements[1].level == 2
        assert elements[2].level == 3

    def test_numbered_with_parts(self):
        """With PART markers: PART→H1, 1.→H2, 1.1→H3, 1.1.1→H4."""
        elements = [
            HeadingBlock(level=2, text="PART I - GENERAL"),
            HeadingBlock(level=2, text="1. Introduction"),
            HeadingBlock(level=2, text="1.1 Purpose"),
            HeadingBlock(level=2, text="1.1.1 Sub-purpose"),
        ]
        _resolve_heading_levels(elements, has_parts=True)
        assert elements[0].level == 1
        assert elements[1].level == 2
        assert elements[2].level == 3
        assert elements[3].level == 4

    def test_unnumbered_inherits_last_level(self):
        """Unnumbered headings like 'RFI's' inherit the last seen level."""
        elements = [
            HeadingBlock(level=2, text="PART I - GENERAL"),
            HeadingBlock(level=2, text="2. TECHNICAL SUPPORT"),
            HeadingBlock(level=2, text="2.3 Project Document Control"),
            HeadingBlock(level=2, text="RFI's"),
            HeadingBlock(level=2, text="SUBMITTALS"),
        ]
        _resolve_heading_levels(elements, has_parts=True)
        assert elements[0].level == 1  # PART I
        assert elements[1].level == 2  # 2.
        assert elements[2].level == 3  # 2.3
        assert elements[3].level == 3  # RFI's inherits
        assert elements[4].level == 3  # SUBMITTALS inherits

    def test_structural_markers_always_level_1(self):
        """PART I, PART II, APPENDIX A are all H1."""
        elements = [
            HeadingBlock(level=2, text="PART I - GENERAL"),
            HeadingBlock(level=2, text="1. Scope"),
            HeadingBlock(level=2, text="PART II - CONSTRUCTION"),
            HeadingBlock(level=2, text="1. Phase"),
            HeadingBlock(level=2, text="APPENDIX A - DETAILS"),
        ]
        _resolve_heading_levels(elements, has_parts=True)
        assert elements[0].level == 1  # PART I
        assert elements[1].level == 2  # 1.
        assert elements[2].level == 1  # PART II
        assert elements[3].level == 2  # 1.
        assert elements[4].level == 1  # APPENDIX A

    def test_glo_full_trace(self):
        """22 headings from GLO doc with expected levels."""
        headings = [
            "Design Builder Services",
            "PART I - GENERAL",
            "1. REVIEW OF DOCUMENTS",
            "1.1 Review of Documents",
            "1.2 Permits",
            "2. TECHNICAL SUPPORT",
            "2.1 Design Review",
            "2.2 Commissioning",
            "2.3 Project Document Control",
            "RFI's",
            "SUBMITTALS",
            "3. COMMUNICATION",
            "PART II - CONSTRUCTION",
            "1. CONSTRUCTION PHASE",
            "1.1 Site Management",
            "1.1.9.4 Emergency Response",
            "1.2 Subcontractor Oversight",
            "1.2.1 Safety",
            "1.2.2 Quality",
            "1.2.2.1 Inspections",
            "2. 'TURNOVER' PHASE",
            "2.1 Closeout",
        ]
        expected = [1, 1, 2, 3, 3, 2, 3, 3, 3, 3, 3, 2, 1, 2, 3, 5, 3, 4, 4, 5, 2, 3]
        elements = [HeadingBlock(level=2, text=t) for t in headings]
        _resolve_heading_levels(elements, has_parts=True)
        actual = [el.level for el in elements]
        assert actual == expected


# ---------------------------------------------------------------------------
# _promote_numbered_paragraphs tests
# ---------------------------------------------------------------------------


class TestPromoteNumberedParagraphs:
    def test_multi_level_paragraph_promoted(self):
        """Multi-level numbered paragraph becomes HeadingBlock."""
        elements = [ParagraphBlock(text="1.1.9.4 Emergency Response", page=5)]
        result = _promote_numbered_paragraphs(elements)
        assert len(result) == 1
        assert isinstance(result[0], HeadingBlock)
        assert result[0].text == "1.1.9.4 Emergency Response"
        assert result[0].page == 5

    def test_long_two_part_paragraph_not_promoted(self):
        """2-part paragraphs > 120 chars are NOT promoted (false positive risk)."""
        long_text = "1.2 " + "x" * 120
        elements = [ParagraphBlock(text=long_text)]
        result = _promote_numbered_paragraphs(elements)
        assert isinstance(result[0], ParagraphBlock)

    def test_single_level_not_promoted(self):
        """Single-level numbering ('1. something') is NOT promoted."""
        elements = [ParagraphBlock(text="1. Introduction paragraph text")]
        result = _promote_numbered_paragraphs(elements)
        assert isinstance(result[0], ParagraphBlock)

    def test_non_numbered_unchanged(self):
        """Non-numbered paragraphs pass through unchanged."""
        elements = [ParagraphBlock(text="Just a regular paragraph")]
        result = _promote_numbered_paragraphs(elements)
        assert isinstance(result[0], ParagraphBlock)
        assert result[0].text == "Just a regular paragraph"

    def test_preserves_runs_on_promotion(self):
        """Promoted headings keep their original runs."""
        from pdf_converter.ir.schema import TextRun
        runs = [TextRun(text="1.1.9.4 Emergency Response", bold=True)]
        elements = [ParagraphBlock(text="1.1.9.4 Emergency Response", page=3, runs=runs)]
        result = _promote_numbered_paragraphs(elements)
        assert isinstance(result[0], HeadingBlock)
        assert len(result[0].runs) == 1
        assert result[0].runs[0].bold is True


# ---------------------------------------------------------------------------
# _is_structural_marker tests
# ---------------------------------------------------------------------------


class TestIsStructuralMarker:
    def test_part_roman(self):
        assert _is_structural_marker("PART I - GENERAL") is True

    def test_part_arabic(self):
        assert _is_structural_marker("PART 1 - GENERAL") is True

    def test_part_lowercase(self):
        assert _is_structural_marker("Part II") is True

    def test_chapter(self):
        assert _is_structural_marker("CHAPTER 3") is True

    def test_appendix_not_structural(self):
        """APPENDIX triggers level1 but NOT has_parts offset."""
        assert _is_structural_marker("APPENDIX A") is False

    def test_appendix_is_level1(self):
        assert _is_level1_structural("APPENDIX A") is True

    def test_exhibit_is_level1(self):
        assert _is_level1_structural("EXHIBIT B") is True

    def test_annex_is_level1(self):
        assert _is_level1_structural("ANNEX I") is True

    def test_rfis_not_structural(self):
        assert _is_structural_marker("RFI's") is False
        assert _is_level1_structural("RFI's") is False

    def test_numbered_not_structural(self):
        assert _is_structural_marker("1.1 Scope") is False
        assert _is_level1_structural("1.1 Scope") is False


# ---------------------------------------------------------------------------
# _group_list_items tests
# ---------------------------------------------------------------------------

class TestGroupListItems:
    def test_no_list_items(self):
        """Non-list elements pass through unchanged."""
        elements = [
            ParagraphBlock(text="Hello"),
            HeadingBlock(level=1, text="H1"),
        ]
        result = _group_list_items(elements)
        assert len(result) == 2
        assert result[0].text == "Hello"
        assert result[1].text == "H1"

    def test_single_bullet_list(self):
        """Consecutive bullet items → one ListBlock."""
        elements = [
            _PendingListItem(text="A", enumerated=False, nesting_depth=0),
            _PendingListItem(text="B", enumerated=False, nesting_depth=0),
        ]
        result = _group_list_items(elements)
        assert len(result) == 1
        assert isinstance(result[0], ListBlock)
        assert result[0].style == "unordered"
        assert len(result[0].items) == 2
        assert result[0].items[0].text == "A"
        assert result[0].items[1].text == "B"

    def test_ordered_list(self):
        """Enumerated items → ordered ListBlock."""
        elements = [
            _PendingListItem(text="First", enumerated=True, nesting_depth=0),
            _PendingListItem(text="Second", enumerated=True, nesting_depth=0),
        ]
        result = _group_list_items(elements)
        assert len(result) == 1
        assert result[0].style == "ordered"

    def test_nested_list_items(self):
        """Items with different nesting depths → nested ListItems."""
        elements = [
            _PendingListItem(text="Parent", enumerated=False, nesting_depth=0),
            _PendingListItem(text="Child", enumerated=False, nesting_depth=1),
            _PendingListItem(text="Sibling", enumerated=False, nesting_depth=0),
        ]
        result = _group_list_items(elements)
        assert len(result) == 1
        lb = result[0]
        assert len(lb.items) == 2  # Parent and Sibling at root
        assert lb.items[0].text == "Parent"
        assert len(lb.items[0].children) == 1
        assert lb.items[0].children[0].text == "Child"
        assert lb.items[1].text == "Sibling"

    def test_list_separated_by_paragraph(self):
        """A paragraph breaks the list into two separate ListBlocks."""
        elements = [
            _PendingListItem(text="A", enumerated=False, nesting_depth=0),
            ParagraphBlock(text="Separator"),
            _PendingListItem(text="B", enumerated=False, nesting_depth=0),
        ]
        result = _group_list_items(elements)
        assert len(result) == 3
        assert isinstance(result[0], ListBlock)
        assert result[0].items[0].text == "A"
        assert isinstance(result[1], ParagraphBlock)
        assert isinstance(result[2], ListBlock)
        assert result[2].items[0].text == "B"

    def test_mixed_content_ordering(self):
        """Lists interleaved with other content preserve order."""
        elements = [
            HeadingBlock(level=1, text="H1"),
            _PendingListItem(text="Item1", enumerated=False, nesting_depth=0),
            _PendingListItem(text="Item2", enumerated=False, nesting_depth=0),
            ParagraphBlock(text="Para"),
        ]
        result = _group_list_items(elements)
        assert len(result) == 3
        assert isinstance(result[0], HeadingBlock)
        assert isinstance(result[1], ListBlock)
        assert isinstance(result[2], ParagraphBlock)


# ---------------------------------------------------------------------------
# Parser factory tests
# ---------------------------------------------------------------------------

class TestParserFactory:
    def test_create_docling_parser(self):
        parser = create_parser()
        assert parser.name == "docling"

    def test_create_docling_explicit(self):
        config = Config.default()
        config.parser.engine = "docling"
        parser = create_parser(config)
        assert parser.name == "docling"

    def test_unknown_engine_raises(self):
        config = Config.default()
        config.parser.engine = "nonexistent"
        with pytest.raises(ConfigError, match="Unknown parser engine"):
            create_parser(config)


# ---------------------------------------------------------------------------
# Base parser tests
# ---------------------------------------------------------------------------

class TestBasePdfParser:
    def test_file_hash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h = BasePdfParser.file_hash(f)
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest

    def test_file_hash_deterministic(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("same content")
        h1 = BasePdfParser.file_hash(f)
        h2 = BasePdfParser.file_hash(f)
        assert h1 == h2

    def test_file_hash_changes(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("content A")
        f2 = tmp_path / "b.txt"
        f2.write_text("content B")
        assert BasePdfParser.file_hash(f1) != BasePdfParser.file_hash(f2)


# ---------------------------------------------------------------------------
# Issue 1: _level_from_numbering — bare section numbers
# ---------------------------------------------------------------------------

class TestLevelFromNumberingBare:
    def test_bare_two_part(self):
        """'2.2' with no trailing text → level 2."""
        assert _level_from_numbering("2.2") == 2

    def test_bare_two_part_trailing_dot(self):
        """'2.2.' with trailing dot → level 2."""
        assert _level_from_numbering("2.2.") == 2

    def test_bare_three_part(self):
        """'1.3.1' → level 3."""
        assert _level_from_numbering("1.3.1") == 3

    def test_bare_with_whitespace(self):
        """'2.2 ' with trailing space → level 2."""
        assert _level_from_numbering("2.2 ") == 2

    def test_single_number_not_bare(self):
        """'2' alone should NOT match as bare (single part)."""
        assert _level_from_numbering("2") is None


# ---------------------------------------------------------------------------
# Issue 3: _promote_numbered_paragraphs — long 3+ level numbers
# ---------------------------------------------------------------------------

class TestPromoteDeepNumbers:
    def test_long_three_part_promoted(self):
        """3+ part numbered paragraph > 120 chars should still be promoted."""
        long_text = "1.3.1.2 " + "x" * 200
        elements = [ParagraphBlock(text=long_text)]
        result = _promote_numbered_paragraphs(elements)
        assert isinstance(result[0], HeadingBlock)
        assert result[0].text == long_text

    def test_long_two_part_not_promoted(self):
        """2-part numbered paragraph > 120 chars should NOT be promoted."""
        long_text = "1.2 " + "x" * 200
        elements = [ParagraphBlock(text=long_text)]
        result = _promote_numbered_paragraphs(elements)
        assert isinstance(result[0], ParagraphBlock)

    def test_short_two_part_still_promoted(self):
        """2-part numbered paragraph < 120 chars should still be promoted."""
        elements = [ParagraphBlock(text="1.2 Short heading")]
        result = _promote_numbered_paragraphs(elements)
        assert isinstance(result[0], HeadingBlock)


# ---------------------------------------------------------------------------
# Issue 4: _split_compound_headings
# ---------------------------------------------------------------------------

class TestSplitCompoundHeadings:
    def test_middle_dot_split(self):
        """Heading with ' · ' should be split into heading + paragraph."""
        elements = [
            HeadingBlock(level=2, text="PAY APPLICATIONS · Managed in Aconex", page=5),
        ]
        result = _split_compound_headings(elements)
        assert len(result) == 2
        assert isinstance(result[0], HeadingBlock)
        assert result[0].text == "PAY APPLICATIONS"
        assert result[0].page == 5
        assert isinstance(result[1], ParagraphBlock)
        assert result[1].text == "Managed in Aconex"
        assert result[1].page == 5

    def test_bullet_dot_split(self):
        """Heading with ' • ' should also be split."""
        elements = [
            HeadingBlock(level=2, text="HEADING • extra text"),
        ]
        result = _split_compound_headings(elements)
        assert len(result) == 2
        assert result[0].text == "HEADING"
        assert result[1].text == "extra text"

    def test_no_separator_unchanged(self):
        """Headings without separators pass through unchanged."""
        elements = [HeadingBlock(level=2, text="Normal heading")]
        result = _split_compound_headings(elements)
        assert len(result) == 1
        assert result[0].text == "Normal heading"

    def test_non_heading_unchanged(self):
        """Non-heading elements are not affected."""
        elements = [ParagraphBlock(text="Para · with dot")]
        result = _split_compound_headings(elements)
        assert len(result) == 1
        assert isinstance(result[0], ParagraphBlock)

    def test_runs_cleared_on_split(self):
        """After splitting, the heading's stale runs should be cleared."""
        from pdf_converter.ir.schema import TextRun
        elements = [
            HeadingBlock(
                level=2,
                text="HEAD · TAIL",
                runs=[TextRun(text="HEAD · TAIL", bold=True)],
            ),
        ]
        result = _split_compound_headings(elements)
        assert result[0].runs == []


# ---------------------------------------------------------------------------
# Issue 2: _detect_marker_format
# ---------------------------------------------------------------------------

class TestDetectMarkerFormat:
    def test_lower_letter_dot(self):
        items = [
            _PendingListItem(text="first", enumerated=True, marker="a."),
            _PendingListItem(text="second", enumerated=True, marker="b."),
        ]
        assert _detect_marker_format(items) == "lowerLetter"

    def test_lower_letter_paren(self):
        items = [
            _PendingListItem(text="first", enumerated=True, marker="a)"),
        ]
        assert _detect_marker_format(items) == "lowerLetter"

    def test_upper_letter(self):
        items = [
            _PendingListItem(text="first", enumerated=True, marker="A."),
            _PendingListItem(text="second", enumerated=True, marker="B."),
        ]
        assert _detect_marker_format(items) == "upperLetter"

    def test_lower_roman(self):
        items = [
            _PendingListItem(text="first", enumerated=True, marker="i."),
            _PendingListItem(text="second", enumerated=True, marker="ii."),
        ]
        assert _detect_marker_format(items) == "lowerRoman"

    def test_decimal_default(self):
        items = [
            _PendingListItem(text="first", enumerated=True, marker="1."),
        ]
        assert _detect_marker_format(items) is None

    def test_no_marker(self):
        items = [
            _PendingListItem(text="first", enumerated=True, marker=""),
        ]
        assert _detect_marker_format(items) is None

    def test_marker_format_in_grouped_list(self):
        """_group_list_items should set marker_format on the ListBlock."""
        elements = [
            _PendingListItem(text="first", enumerated=True, marker="a.", nesting_depth=0),
            _PendingListItem(text="second", enumerated=True, marker="b.", nesting_depth=0),
        ]
        result = _group_list_items(elements)
        assert len(result) == 1
        assert isinstance(result[0], ListBlock)
        assert result[0].marker_format == "lowerLetter"

    def test_unordered_no_marker_format(self):
        """Unordered lists should not get marker_format."""
        elements = [
            _PendingListItem(text="first", enumerated=False, marker="", nesting_depth=0),
        ]
        result = _group_list_items(elements)
        assert result[0].marker_format is None


# ---------------------------------------------------------------------------
# Heading confidence assignment
# ---------------------------------------------------------------------------

class TestHeadingConfidenceAssignment:
    """Verify confidence scores and classification reasons per heading path."""

    def test_resolve_structural_marker_high_confidence(self):
        elements = [
            HeadingBlock(
                level=2, text="PART I - GENERAL",
                confidence=0.85,
                classification_reason="docling_label:section_header",
            ),
        ]
        _resolve_heading_levels(elements, has_parts=True)
        assert elements[0].level == 1
        assert elements[0].confidence >= 0.95
        assert "structural_marker" in elements[0].classification_reason

    def test_resolve_numbering_preserves_confidence(self):
        elements = [
            HeadingBlock(
                level=2, text="1.2 Scope",
                confidence=0.85,
                classification_reason="docling_label:section_header",
            ),
        ]
        _resolve_heading_levels(elements, has_parts=False)
        assert elements[0].level == 2
        assert elements[0].confidence == 0.85  # unchanged
        assert "numbering" in elements[0].classification_reason

    def test_resolve_first_heading_as_title(self):
        elements = [
            HeadingBlock(
                level=2, text="My Document Title",
                confidence=0.85,
                classification_reason="docling_label:title",
            ),
        ]
        _resolve_heading_levels(elements, has_parts=False)
        assert elements[0].level == 1
        assert elements[0].confidence <= 0.80
        assert "first_heading_as_title" in elements[0].classification_reason

    def test_resolve_inherited_level_low_confidence(self):
        elements = [
            HeadingBlock(
                level=2, text="1. Intro",
                confidence=0.85,
                classification_reason="docling_label:section_header",
            ),
            HeadingBlock(
                level=2, text="RFI's",
                confidence=0.85,
                classification_reason="docling_label:section_header",
            ),
        ]
        _resolve_heading_levels(elements, has_parts=False)
        # Second heading has no numbering and is not first → inherited
        assert elements[1].confidence <= 0.50
        assert "inherited" in elements[1].classification_reason

    def test_promote_paragraph_three_parts(self):
        elements = [ParagraphBlock(text="1.2.3 Details of the work")]
        result = _promote_numbered_paragraphs(elements)
        assert isinstance(result[0], HeadingBlock)
        assert result[0].confidence == 0.90
        assert "multi_level_3_parts" in result[0].classification_reason

    def test_promote_paragraph_two_parts(self):
        elements = [ParagraphBlock(text="1.2 Short")]
        result = _promote_numbered_paragraphs(elements)
        assert isinstance(result[0], HeadingBlock)
        assert result[0].confidence == 0.70
        assert "two_level" in result[0].classification_reason

    def test_compound_split_lowers_confidence(self):
        elements = [
            HeadingBlock(
                level=2, text="PAY APPLICATIONS · Managed in Aconex",
                confidence=0.85,
                classification_reason="docling_label:section_header",
            ),
        ]
        result = _split_compound_headings(elements)
        heading = result[0]
        assert isinstance(heading, HeadingBlock)
        assert heading.text == "PAY APPLICATIONS"
        assert heading.confidence <= 0.75
        assert "compound_split" in heading.classification_reason

    def test_reason_chain_accumulates(self):
        """Classification reason should accumulate across multiple stages."""
        elements = [
            HeadingBlock(
                level=2, text="1.1 Something · Extra",
                confidence=0.85,
                classification_reason="docling_label:section_header",
            ),
        ]
        # Split compound heading
        elements = _split_compound_headings(elements)
        # Resolve level
        _resolve_heading_levels(elements, has_parts=False)

        heading = elements[0]
        assert "docling_label" in heading.classification_reason
        assert "compound_split" in heading.classification_reason
        assert "level:" in heading.classification_reason


# ---------------------------------------------------------------------------
# Single-number heading detection
# ---------------------------------------------------------------------------

class TestSingleNumberHeadings:
    """Verify _level_from_numbering handles single-digit section numbers."""

    def test_single_digit_capitalized_word(self):
        """'3 Safety Instructions' should match as level 1."""
        assert _level_from_numbering("3 Safety Instructions") == 1

    def test_single_digit_title_case(self):
        """'1 Locomotives Affected' should match as level 1."""
        assert _level_from_numbering("1 Locomotives Affected") == 1

    def test_single_digit_with_dot(self):
        """'1. Introduction' should match as level 1."""
        assert _level_from_numbering("1. Introduction") == 1

    def test_single_digit_all_caps(self):
        """'3 QUALITY CONTROL' should match (existing behavior)."""
        assert _level_from_numbering("3 QUALITY CONTROL") == 1

    def test_single_digit_short_word_no_match(self):
        """'1 am' should NOT match — too short to be a section title."""
        assert _level_from_numbering("1 am") is None

    def test_single_digit_lowercase_no_match(self):
        """'2 weeks later' should NOT match — lowercase start."""
        assert _level_from_numbering("2 weeks later") is None

    def test_two_digit_number_no_match(self):
        """'12 Monkeys' should NOT match — only single digits allowed."""
        assert _level_from_numbering("12 Monkeys") is None

    def test_single_digit_measurement_no_match(self):
        """'5 kg of material' should NOT match — lowercase."""
        assert _level_from_numbering("5 kg of material") is None


# ---------------------------------------------------------------------------
# Promote numbered list items to headings
# ---------------------------------------------------------------------------

class TestPromoteNumberedListItems:
    """Verify _promote_numbered_list_items catches mis-classified headings."""

    def test_three_part_list_item_promoted(self):
        elements = [
            _PendingListItem(text="8.1.2 Open the panel and remove screws"),
        ]
        result = _promote_numbered_list_items(elements)
        assert len(result) == 1
        assert isinstance(result[0], HeadingBlock)
        assert result[0].text == "8.1.2 Open the panel and remove screws"
        assert result[0].confidence == 0.85
        assert "promoted_list_item" in result[0].classification_reason

    def test_four_part_list_item_promoted(self):
        elements = [
            _PendingListItem(text="1.2.3.4 Sub-sub-sub section"),
        ]
        result = _promote_numbered_list_items(elements)
        assert isinstance(result[0], HeadingBlock)
        assert result[0].confidence == 0.85

    def test_two_part_short_list_item_promoted(self):
        elements = [
            _PendingListItem(text="3.2 Scope of work"),
        ]
        result = _promote_numbered_list_items(elements)
        assert isinstance(result[0], HeadingBlock)
        assert result[0].confidence == 0.65
        assert "two_level" in result[0].classification_reason

    def test_two_part_long_list_item_not_promoted(self):
        """Long 2-part numbered text stays as list item (likely body text)."""
        long_text = "1.2 " + "x" * 120
        elements = [_PendingListItem(text=long_text)]
        result = _promote_numbered_list_items(elements)
        assert isinstance(result[0], _PendingListItem)

    def test_single_number_list_item_not_promoted(self):
        """Single-number list items stay as list items."""
        elements = [_PendingListItem(text="1. First step")]
        result = _promote_numbered_list_items(elements)
        assert isinstance(result[0], _PendingListItem)

    def test_non_numbered_list_item_unchanged(self):
        elements = [_PendingListItem(text="Just a regular item")]
        result = _promote_numbered_list_items(elements)
        assert isinstance(result[0], _PendingListItem)

    def test_preserves_page_on_promotion(self):
        elements = [
            _PendingListItem(text="8.1.1 Step one", page=11),
        ]
        result = _promote_numbered_list_items(elements)
        assert result[0].page == 11

    def test_mixed_list_items_and_headings(self):
        """Only numbered list items get promoted; others stay."""
        elements = [
            _PendingListItem(text="8.1.1 First step"),
            _PendingListItem(text="Note: be careful"),
            HeadingBlock(level=2, text="8.2 Next section"),
        ]
        result = _promote_numbered_list_items(elements)
        assert isinstance(result[0], HeadingBlock)  # promoted
        assert isinstance(result[1], _PendingListItem)  # kept
        assert isinstance(result[2], HeadingBlock)  # was already heading
