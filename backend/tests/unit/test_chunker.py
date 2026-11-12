from app.chunking.heading_chunker import HeadingChunker

DOC = """# Title

Intro paragraph that is long enough to stand on its own as content.

## Section A

Body of section A with some detail about `Foo.bar()` behaviour.

## Section B

Body of section B, which is also long enough to be its own chunk.
"""


def test_splits_on_headings_and_keeps_heading_context():
    chunks = HeadingChunker().chunk(DOC, "markdown")
    headings = [c.heading for c in chunks]
    assert headings == ["Title", "Section A", "Section B"]
    assert chunks[1].content.startswith("Section A")
    assert [c.ordinal for c in chunks] == [0, 1, 2]


def test_deterministic():
    a = HeadingChunker().chunk(DOC, "markdown")
    b = HeadingChunker().chunk(DOC, "markdown")
    assert a == b


def test_oversized_section_split_on_paragraphs():
    big = "# H\n\n" + "\n\n".join("para " + "x" * 400 for _ in range(6))
    chunks = HeadingChunker(max_chars=1000).chunk(big, "markdown")
    assert len(chunks) > 1
    assert all(len(c.content) <= 1000 + len("H\n\n") for c in chunks)


def test_plain_text_single_chunk_and_empty():
    assert len(HeadingChunker().chunk("just text " * 10, "text")) == 1
    assert HeadingChunker().chunk("   ", "text") == []
