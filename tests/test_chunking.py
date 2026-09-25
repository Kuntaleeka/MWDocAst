from _lib.chunking import OVERLAP_CHARS, TARGET_CHARS, Section, chunk_sections, clean, split_markdown
from _lib.parsing import UnsupportedDocument, parse

import pytest


def test_markdown_sections_use_heading_path():
    md = "Intro text.\n\n# Policies\n\nGeneral.\n\n## Refunds\n\nWithin 30 days.\n\n# Contact\n\nEmail us."
    titles = [s.title for s in split_markdown(md)]
    assert titles == [None, "Policies", "Policies > Refunds", "Contact"]


def test_headings_inside_code_fences_are_ignored():
    md = "# Setup\n\n```bash\n# not a heading\nls\n```\n"
    sections = split_markdown(md)
    assert [s.title for s in sections] == ["Setup"]
    assert "# not a heading" in sections[0].text


def test_small_section_is_one_chunk():
    chunks = chunk_sections([Section("A", "one\n\ntwo")])
    assert [(c.index, c.section, c.content) for c in chunks] == [(0, "A", "one\n\ntwo")]


def test_long_section_is_split_with_overlap_and_bounded_size():
    paras = [f"Paragraph {i}. " + "word " * 150 for i in range(40)]
    chunks = chunk_sections([Section("Big", "\n\n".join(paras))])
    assert len(chunks) > 1
    assert all(len(c.content) <= TARGET_CHARS + OVERLAP_CHARS + 2 for c in chunks)
    # The start of each chunk repeats the end of the previous one.
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt.content[:50] in prev.content
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_giant_paragraph_without_breaks_is_hard_split():
    chunks = chunk_sections([Section(None, "x" * (TARGET_CHARS * 3))])
    assert len(chunks) >= 3


def test_chunks_never_cross_sections():
    chunks = chunk_sections([Section("A", "alpha"), Section("B", "beta")])
    assert [(c.section, c.content) for c in chunks] == [("A", "alpha"), ("B", "beta")]


def test_clean_strips_nul_and_collapses_whitespace():
    assert clean("a\x00b  \t c\r\n\n\n\nd") == "ab c\n\nd"


def test_parse_rejects_unknown_type_and_empty_text():
    with pytest.raises(UnsupportedDocument):
        parse("evil.exe", b"MZ")
    with pytest.raises(UnsupportedDocument):
        parse("empty.md", b"   \n\n ")
