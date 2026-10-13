import pytest

from app.modules.knowledge.chunking import Section, chunk_sections, split_markdown
from app.modules.knowledge.ingest import UnsupportedDocumentError, derive_title, extract_sections

DOC = """# Annual Leave Policy

Intro paragraph.

## Entitlement

Full-time employees receive 25 days.

### Part-time

Pro-rata entitlement.

```bash
# not a heading
echo hi
```

## Carry-over

Up to 5 days.
"""


def test_split_markdown_tracks_heading_path() -> None:
    sections = split_markdown(DOC)
    headings = [s.heading for s in sections]
    assert headings == [
        "Annual Leave Policy",
        "Annual Leave Policy > Entitlement",
        "Annual Leave Policy > Entitlement > Part-time",
        "Annual Leave Policy > Carry-over",
    ]


def test_headings_inside_code_fences_are_ignored() -> None:
    part_time = split_markdown(DOC)[2]
    assert "# not a heading" in part_time.text


def test_chunks_respect_max_size_and_overlap() -> None:
    paragraph = "This is a sentence about leave. " * 20  # ~640 chars
    section = Section("Policy", "\n\n".join([paragraph.strip()] * 5))
    chunks = chunk_sections([section], max_chars=1000, overlap_chars=100)
    assert len(chunks) > 1
    assert all(len(c.content) <= 1000 for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    # The second chunk starts with the tail of the first one
    tail = chunks[0].content[-60:]
    assert tail.split(" ", 1)[-1] in chunks[1].content


def test_unbreakable_text_is_hard_split() -> None:
    chunks = chunk_sections([Section(None, "x" * 2500)], max_chars=1000)
    assert len(chunks) == 3
    assert all(len(c.content) <= 1000 for c in chunks)


def test_title_from_first_heading_or_filename() -> None:
    assert derive_title("leave.md", split_markdown(DOC)) == "Annual Leave Policy"
    assert derive_title("vpn-error-809.txt", [Section(None, "text")]) == "Vpn Error 809"


def test_extract_sections_rejects_unknown_types() -> None:
    with pytest.raises(UnsupportedDocumentError):
        extract_sections("malware.exe", b"MZ")
    with pytest.raises(UnsupportedDocumentError):
        extract_sections("latin1.txt", "caf\xe9".encode("latin-1"))
