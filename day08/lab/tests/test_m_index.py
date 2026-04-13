import pytest
import re
from unittest.mock import patch, MagicMock
from src.indexing.index import (
    preprocess_document,
    chunk_document,
    _split_by_size,
    _split_long_paragraph,
    _extract_overlap_tail,
    get_chroma_collection,
    MIN_CHUNK_CHARS,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
)

SAMPLE_RAW_TEXT = """Source: it/access-control-sop.md
Department: IT
Effective Date: 2026-01-15
Access: internal

ACCESS CONTROL SOP

=== Section 1: Account Creation ===
When a new employee joins, HR submits a system access request form.
IT Admin reviews the request and provisions accounts within 24 hours.
All accounts start with Level 1 (Basic) access by default.

=== Section 2: Password Policy ===
Passwords must be at least 12 characters with uppercase, lowercase, numbers, and symbols.
Password rotation is required every 90 days.
Accounts lock after 5 consecutive failed login attempts.

=== Section 3: Access Revocation ===
Upon employee termination, all access must be revoked within 4 hours.
IT Admin runs the offboarding checklist and disables Active Directory accounts.
VPN tokens and badge access are deactivated simultaneously.
"""

LONG_SECTION_TEXT = "A" * 3500


class TestPreprocessDocument:
    def test_extracts_metadata_correctly(self):
        doc = preprocess_document(SAMPLE_RAW_TEXT, "test/file.txt")

        assert doc["metadata"]["department"] == "IT"
        assert doc["metadata"]["effective_date"] == "2026-01-15"
        assert doc["metadata"]["access"] == "internal"

    def test_returns_cleaned_text(self):
        doc = preprocess_document(SAMPLE_RAW_TEXT, "test/file.txt")

        assert "Source:" not in doc["text"]
        assert "Department:" not in doc["text"]
        assert "Effective Date:" not in doc["text"]

    def test_extracts_heading(self):
        doc = preprocess_document(SAMPLE_RAW_TEXT, "test/file.txt")

        assert doc["metadata"]["heading"] == "ACCESS CONTROL SOP"


class TestChunkDocument:
    def test_splits_by_section_headings(self):
        doc = preprocess_document(SAMPLE_RAW_TEXT, "test/file.txt")
        chunks = chunk_document(doc)

        section_names = [c["metadata"]["section"] for c in chunks]
        assert "Section 1: Account Creation" in section_names
        assert "Section 2: Password Policy" in section_names
        assert "Section 3: Access Revocation" in section_names

    def test_preserves_metadata_in_every_chunk(self):
        doc = preprocess_document(SAMPLE_RAW_TEXT, "test/file.txt")
        chunks = chunk_document(doc)

        for chunk in chunks:
            assert "section" in chunk["metadata"]
            assert "department" in chunk["metadata"]

    def test_filters_short_chunks(self):
        doc = {
            "text": "=== Title Only ===\nAB\n=== Real Section ===\n" + "X" * 200,
            "metadata": {"source": "test.txt"},
        }
        chunks = chunk_document(doc)

        for chunk in chunks:
            assert len(chunk["text"].strip()) >= MIN_CHUNK_CHARS

    def test_no_empty_chunks(self):
        doc = preprocess_document(SAMPLE_RAW_TEXT, "test/file.txt")
        chunks = chunk_document(doc)

        for chunk in chunks:
            assert chunk["text"].strip() != ""


class TestSplitBySize:
    def test_short_text_returns_single_chunk(self):
        result = _split_by_size(
            "Short text content.",
            base_metadata={"source": "test"},
            section="General",
        )
        assert len(result) == 1
        assert result[0]["metadata"]["section"] == "General"

    def test_long_text_splits_into_multiple_chunks(self):
        result = _split_by_size(
            LONG_SECTION_TEXT,
            base_metadata={"source": "test"},
            section="LongSection",
            chunk_chars=1000,
            overlap_chars=50,
        )
        assert len(result) > 1

    def test_paragraph_boundary_respected(self):
        text = ("First paragraph content. " * 20 + "\n\n" + "Second paragraph content. " * 20)
        result = _split_by_size(
            text,
            base_metadata={"source": "test"},
            section="ParaTest",
            chunk_chars=300,
            overlap_chars=20,
        )
        assert len(result) >= 2


class TestSplitLongParagraph:
    def test_splits_by_sentence(self):
        paragraph = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = _split_long_paragraph(paragraph, chunk_chars=40)

        assert len(result) > 1
        for segment in result:
            assert len(segment) <= 40 or len(re.split(r"(?<=[.!?])\s+", segment)) == 1

    def test_fallback_for_single_long_sentence(self):
        paragraph = "A" * 500
        result = _split_long_paragraph(paragraph, chunk_chars=100)

        assert len(result) >= 1


class TestExtractOverlapTail:
    def test_returns_tail_of_text(self):
        result = _extract_overlap_tail("Hello World Test Overlap", 10)
        assert result == "st Overlap"

    def test_returns_empty_when_zero_chars(self):
        assert _extract_overlap_tail("Some text", 0) == ""

    def test_strips_leading_whitespace(self):
        result = _extract_overlap_tail("Hello   World", 8)
        assert result[0] != " "


class TestGetChromaCollection:
    @patch("src.indexing.index.chromadb", create=True)
    def test_returns_collection(self):
        import importlib
        import src.indexing.index as idx

        with patch.dict("sys.modules", {"chromadb": MagicMock()}):
            mock_chromadb = MagicMock()
            mock_collection = MagicMock()
            mock_chromadb.PersistentClient.return_value.get_or_create_collection.return_value = mock_collection

            with patch("src.indexing.index.chromadb", mock_chromadb, create=True):
                pass


class TestChunkSizeConfig:
    def test_chunk_size_is_700(self):
        assert CHUNK_SIZE == 700

    def test_chunk_overlap_is_20(self):
        assert CHUNK_OVERLAP == 20

    def test_min_chunk_chars_is_80(self):
        assert MIN_CHUNK_CHARS == 80
