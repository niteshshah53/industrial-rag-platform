"""
Text chunking using LangChain's RecursiveCharacterTextSplitter.

Responsibilities:
  - Split page text into overlapping chunks of configurable character size
  - Attach metadata (document_id, filename, page_number, chunk_index)
  - Generate deterministic chunk IDs from document_id + global chunk index
  - Return DocumentChunk objects ready for embedding

Design decisions:
  - Character-based chunking (not token-based) to avoid the OpenAI tiktoken
    dependency. At ~4 chars/token, CHUNK_SIZE_CHARS=1024 ≈ 256 tokens.
  - Per-page splitting: each page is split independently so that
    page_number metadata is accurate. Chunks never span page boundaries.
  - Deterministic chunk IDs: str(uuid.UUID(hex=sha256(f"{doc_id}:{idx}")[:32]))
    — enables idempotent re-ingestion (same input always produces same IDs).
  - Synchronous — callers must run in a thread pool.

Usage:
    chunker = DocumentChunker(chunk_size_chars=1024, chunk_overlap_chars=128)
    chunks = chunker.chunk(
        pages=[(1, "page text..."), (2, "more text...")],
        document_id="abc-123",
        filename="manual.pdf",
    )
"""

import hashlib
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.logging import get_logger
from app.core.models import DocumentChunk

logger = get_logger(__name__)


def _make_chunk_id(document_id: str, chunk_index: int) -> str:
    """
    Generate a deterministic UUID for a chunk.

    Algorithm: SHA-256 of "{document_id}:{chunk_index}", take first 32 hex chars,
    parse as UUID4 hex. This gives a stable, collision-resistant identifier.
    """
    digest = hashlib.sha256(f"{document_id}:{chunk_index}".encode()).hexdigest()
    return str(uuid.UUID(hex=digest[:32]))


class DocumentChunker:
    """
    Splits extracted page text into overlapping character-based chunks.

    Args:
        chunk_size_chars: Maximum number of characters per chunk.
        chunk_overlap_chars: Number of characters to overlap between chunks.
    """

    def __init__(self, chunk_size_chars: int = 1024, chunk_overlap_chars: int = 128) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size_chars,
            chunk_overlap=chunk_overlap_chars,
            # Prefer splitting at paragraph, sentence, word, then char boundaries.
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
            is_separator_regex=False,
        )
        self._chunk_size = chunk_size_chars
        self._chunk_overlap = chunk_overlap_chars

    def chunk(
        self,
        pages: list[tuple[int, str]],
        document_id: str,
        filename: str,
    ) -> list[DocumentChunk]:
        """
        Split page texts into DocumentChunk objects.

        Args:
            pages: List of (page_number, text) tuples from PDFExtractor.
            document_id: Parent document UUID.
            filename: Original filename for payload metadata.

        Returns:
            List of DocumentChunk objects in document order.
            chunk_index is global (across pages), starting at 0.
        """
        chunks: list[DocumentChunk] = []
        global_index = 0

        for page_number, page_text in pages:
            if not page_text.strip():
                continue

            page_chunks = self._splitter.split_text(page_text)

            for chunk_text in page_chunks:
                chunk_text = chunk_text.strip()
                if not chunk_text:
                    continue

                chunk = DocumentChunk(
                    chunk_id=_make_chunk_id(document_id, global_index),
                    document_id=document_id,
                    filename=filename,
                    text=chunk_text,
                    page_number=page_number,
                    chunk_index=global_index,
                    char_count=len(chunk_text),
                )
                chunks.append(chunk)
                global_index += 1

        logger.debug(
            "Document chunked",
            extra={
                "document_id": document_id,
                "doc_filename": filename,
                "page_count": len(pages),
                "chunk_count": len(chunks),
                "chunk_size_chars": self._chunk_size,
            },
        )

        return chunks
