"""Structure-aware chunking.

Documents are first split into sections (markdown headings, or PDF pages) so every chunk can be
cited as "file § section". Each section is then packed paragraph-by-paragraph into chunks of
~TARGET_CHARS with OVERLAP_CHARS of trailing context carried into the next chunk. Chunks never
cross a section boundary, so a citation always points at one place.
"""

import re
from dataclasses import dataclass

# ~4 chars per token → ~800-token chunks with ~15% overlap.
TARGET_CHARS = 3200
OVERLAP_CHARS = 480

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Section:
    title: str | None
    text: str


@dataclass(frozen=True)
class Chunk:
    index: int
    section: str | None
    content: str


def clean(text: str) -> str:
    # Postgres text can't hold NUL; PDFs extract with odd whitespace.
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_markdown(text: str) -> list[Section]:
    """Split on headings; a section's title is its heading path, e.g. "Policies > Refunds"."""
    sections: list[Section] = []
    path: list[tuple[int, str]] = []
    buf: list[str] = []

    def flush() -> None:
        body = clean("\n".join(buf))
        if body:
            title = " > ".join(t for _, t in path) or None
            sections.append(Section(title, body))
        buf.clear()

    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else _HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            path = [(lvl, t) for lvl, t in path if lvl < level] + [(level, m.group(2))]
        else:
            buf.append(line)
    flush()
    return sections


def _pieces(paragraph: str) -> list[str]:
    """Break an over-long paragraph into sentence-ish pieces no longer than TARGET_CHARS."""
    if len(paragraph) <= TARGET_CHARS:
        return [paragraph]
    out: list[str] = []
    for sentence in _SENTENCE_END.split(paragraph):
        while len(sentence) > TARGET_CHARS:  # no sentence breaks at all: hard split on a space
            cut = sentence.rfind(" ", 0, TARGET_CHARS)
            cut = cut if cut > TARGET_CHARS // 2 else TARGET_CHARS
            out.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            out.append(sentence)
    return out


def _tail(text: str) -> str:
    """Last ~OVERLAP_CHARS of text, starting on a word boundary."""
    if len(text) <= OVERLAP_CHARS:
        return text
    tail = text[-OVERLAP_CHARS:]
    space = tail.find(" ")
    return tail[space + 1 :] if 0 <= space < OVERLAP_CHARS // 2 else tail


def chunk_sections(sections: list[Section]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in sections:
        pieces = [p for para in re.split(r"\n\s*\n", section.text) for p in _pieces(para.strip()) if p]
        current = ""
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) <= TARGET_CHARS or not current:
                current = candidate
                continue
            chunks.append(Chunk(len(chunks), section.title, current))
            current = f"{_tail(current)}\n\n{piece}"
        if current:
            chunks.append(Chunk(len(chunks), section.title, current))
    return chunks
