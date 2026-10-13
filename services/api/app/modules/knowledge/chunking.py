"""Split documents into retrieval-sized chunks, keeping each chunk's heading path."""

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Section:
    heading: str | None  # e.g. "Annual Leave Policy > Carry-over"
    text: str


@dataclass(frozen=True)
class TextChunk:
    ordinal: int
    heading: str | None
    content: str


def split_markdown(text: str) -> list[Section]:
    """Split markdown into sections at headings. Headings inside code fences are ignored."""
    sections: list[Section] = []
    path: list[str] = []
    buffer: list[str] = []
    in_code_block = False

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append(Section(" > ".join(path) or None, body))
        buffer.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code_block = not in_code_block
        match = None if in_code_block else _HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            path = [*path[: level - 1], match.group(2).strip()]
        else:
            buffer.append(line)
    flush()
    return sections


def chunk_sections(
    sections: list[Section], *, max_chars: int = 1200, overlap_chars: int = 150
) -> list[TextChunk]:
    """Pack paragraphs into chunks of at most `max_chars`. Consecutive chunks of one section
    share a short overlap, so a fact split across a boundary is still retrievable."""
    chunks: list[TextChunk] = []
    for section in sections:
        units = [
            piece
            for paragraph in _PARAGRAPH_BREAK_RE.split(section.text)
            if paragraph.strip()
            for piece in _split_long(paragraph.strip(), max_chars)
        ]
        current = ""
        for unit in units:
            candidate = f"{current}\n\n{unit}" if current else unit
            if len(candidate) <= max_chars:
                current = candidate
                continue
            chunks.append(TextChunk(len(chunks), section.heading, current))
            tail = _tail(current, overlap_chars)
            fits_with_overlap = tail and len(tail) + len(unit) + 2 <= max_chars
            current = f"{tail}\n\n{unit}" if fits_with_overlap else unit
        if current:
            chunks.append(TextChunk(len(chunks), section.heading, current))
    return chunks


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END_RE.split(paragraph):
        while len(sentence) > max_chars:  # no usable sentence boundary: hard split
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _tail(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return ""  # the whole chunk would repeat; skip overlap
    tail = text[-max_chars:]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail
