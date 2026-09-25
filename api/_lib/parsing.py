"""Turn uploaded bytes into sections. Supported: PDF, Markdown, plain text."""

import io
from pathlib import PurePosixPath

from pypdf import PdfReader

from .chunking import Section, clean, split_markdown

MAX_BYTES = 10 * 1024 * 1024
EXTENSIONS = {".pdf": "application/pdf", ".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain"}


class UnsupportedDocument(ValueError):
    pass


def extension(filename: str) -> str:
    ext = PurePosixPath(filename).suffix.lower()
    if ext not in EXTENSIONS:
        raise UnsupportedDocument(f"Unsupported file type {ext or '(none)'}; use PDF, Markdown or .txt")
    return ext


def parse(filename: str, data: bytes) -> list[Section]:
    ext = extension(filename)
    if ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [clean(page.extract_text() or "") for page in reader.pages]
        except Exception as exc:  # pypdf raises a zoo of errors on malformed files
            raise UnsupportedDocument("Could not read PDF") from exc
        sections = [Section(f"p. {i}", text) for i, text in enumerate(pages, start=1) if text]
    else:
        # Plain text is treated as markdown too: headings in .txt files still become sections.
        sections = split_markdown(data.decode("utf-8", errors="replace"))
    if not sections:
        raise UnsupportedDocument("No extractable text (scanned PDFs are not supported)")
    return sections
