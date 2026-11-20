from dataclasses import dataclass
from io import BytesIO
import re

from pypdf import PdfReader
from pypdf.errors import PyPdfError


MAX_PDF_MB = 20
TOC_PAGE_LIMIT = 30

_HEADING = re.compile(r"^(?:目\s*录|contents|table of contents)\s*[:：]?$", re.I)
_SKIP = re.compile(r"^(?:封[面底]|扉页|版权(?:页)?|书名页)$")
_CHINESE = re.compile(r"^第\s*[〇零一二三四五六七八九十百千两0-9]+\s*(部分|单元|部(?!分)|[篇章节编课讲])\s*[:：、.．]?\s*")
_ENGLISH = re.compile(r"^(part|unit|chapter|section)\s+[0-9IVX]+\b[.\s:：]+", re.I)
_DECIMAL = re.compile(r"^(\d+(?:[.．\-－–]\d+)*)(?:\s+|[.．、:：)）](?!\d)\s*|(?<=[0-9])(?=[\u3400-\u9fff]))")
_LIST = re.compile(r"^(?:[§]\s*\d+(?:[.．\-－–]\d+)*\s*|[（(][一二三四五六七八九十0-9]+[）)]\s*|[一二三四五六七八九十]+[、.．]\s*|[-•*]\s+)")
_PAGE_REF = re.compile(r"(?:[.．·…⋯—-]{2,}\s*|\s{2,})[（(]?(?:\d{1,4}|[ivxlcdm]{1,8})[）)]?\s*$", re.I)
_SINGLE_PAGE_REF = re.compile(r"\s+(?:\d{1,3}|[ivxlcdm]{1,8})\s*$", re.I)
_PAGE_NUMBER = re.compile(r"^(?:[-—]\s*)?\d{1,4}(?:\s*[-—])?$")


@dataclass(frozen=True)
class Entry:
    label: str
    depth: int


@dataclass(frozen=True)
class Section:
    label: str
    topic: str
    parents: tuple[str, ...]

    @property
    def path(self) -> str:
        return " › ".join((*self.parents, self.label))


class OutlineError(ValueError):
    pass


def _prefix(label: str):
    return _CHINESE.match(label) or _ENGLISH.match(label) or _DECIMAL.match(label) or _LIST.match(label)


def topic_of(label: str) -> str:
    prefix = _prefix(label)
    return (label[prefix.end():].strip() or label) if prefix else label


def _clean_line(line: str, *, pdf: bool) -> str:
    label = _PAGE_REF.sub("", line.strip())
    if pdf and _prefix(label):
        label = _SINGLE_PAGE_REF.sub("", label)
    return re.sub(r"\s+", " ", label).strip()


def _infer_levels(labels: list[str]) -> list[int]:
    levels = []
    has_part = any(
        (match := _CHINESE.match(label)) and match[1] in {"篇", "编", "部", "部分", "单元"}
        or (match := _ENGLISH.match(label)) and match[1].lower() in {"part", "unit"}
        for label in labels
    )
    inside_chapter = False
    for label in labels:
        zh, en, number = _CHINESE.match(label), _ENGLISH.match(label), _DECIMAL.match(label)
        kind = zh[1] if zh else en[1].lower() if en else ""
        if kind in {"篇", "编", "部", "部分", "单元", "part", "unit"}:
            level, inside_chapter = 0, False
        elif kind in {"章", "chapter"}:
            level, inside_chapter = int(has_part), True
        elif kind in {"节", "课", "讲", "section"}:
            level = int(has_part or inside_chapter) + int(has_part and inside_chapter)
        elif number:
            segments = len(re.split(r"[.．\-－–]", number[1]))
            level = int(has_part) + (max(1, segments - 1) if inside_chapter else segments - 1)
        elif _LIST.match(label):
            level = int(has_part) + int(inside_chapter)
        else:
            inside_chapter = False
            level = 0
        levels.append(level)
    return levels


def _normalize_levels(labels: list[str], levels: list[int]) -> list[Entry]:
    ancestry = []
    entries = []
    for label, level in zip(labels, levels, strict=True):
        while ancestry and ancestry[-1] >= level:
            ancestry.pop()
        entries.append(Entry(label, len(ancestry)))
        ancestry.append(level)
    return entries


def parse_outline(text: str, *, pdf: bool = False) -> list[Entry]:
    lines = []
    for raw in text.splitlines():
        label = _clean_line(raw, pdf=pdf)
        if not label or _HEADING.fullmatch(label) or _SKIP.fullmatch(label) or _PAGE_NUMBER.fullmatch(label):
            continue
        indent = raw.replace("\u3000", "  ").expandtabs(2)
        lines.append((len(indent) - len(indent.lstrip()), label))

    labels = [label for _, label in lines]
    indents = [indent for indent, _ in lines]
    explicit_indent = any(indent > indents[0] for indent in indents)
    levels = indents if explicit_indent and not pdf else _infer_levels(labels)
    return _normalize_levels(labels, levels)


def format_outline(entries: list[Entry]) -> str:
    return "\n".join(f"{'  ' * entry.depth}{entry.label}" for entry in entries)


def sections_from(entries: list[Entry]) -> list[Section]:
    sections = []
    parents = []
    for index, entry in enumerate(entries):
        del parents[entry.depth:]
        has_children = index + 1 < len(entries) and entries[index + 1].depth > entry.depth
        if has_children:
            parents.append(entry.label)
        else:
            sections.append(Section(entry.label, topic_of(entry.label), tuple(parents)))
    return sections


def _bookmarks(items, depth: int = 0) -> list[Entry]:
    entries = []
    included_parent = False
    for item in items:
        if isinstance(item, list):
            entries.extend(_bookmarks(item, depth + int(included_parent)))
            continue
        label = _clean_line(item.title, pdf=False)
        included_parent = bool(label and not _HEADING.fullmatch(label) and not _SKIP.fullmatch(label))
        if included_parent:
            entries.append(Entry(label, depth))
    return entries


def _text_outline(reader: PdfReader) -> list[Entry]:
    blocks = []
    for page in reader.pages[:TOC_PAGE_LIMIT]:
        lines = [line.strip() for line in (page.extract_text(extraction_mode="layout") or "").splitlines() if line.strip()]
        heading = next((i for i, line in enumerate(lines[:8]) if _HEADING.fullmatch(line)), None)
        if heading is not None:
            lines = lines[heading + 1:]
        referenced = [line for line in lines if _PAGE_REF.search(line) or (_prefix(line) and _SINGLE_PAGE_REF.search(line))]
        recognized = [line for line in lines if line in referenced or _prefix(line)]
        if heading is not None:
            if blocks:
                break
            blocks.append(recognized or lines)
        elif len(referenced) >= (1 if blocks else 3) and len(referenced) * 2 >= len(lines):
            blocks.append(recognized)
        elif blocks:
            if not any(blocks):
                blocks.clear()
            else:
                break
    return parse_outline("\n".join(line for block in blocks for line in block), pdf=True)


def extract_pdf_outline(data: bytes) -> list[Entry]:
    if len(data) > MAX_PDF_MB * 1024 * 1024:
        raise OutlineError(f"PDF 超过 {MAX_PDF_MB} MB。请改用粘贴目录。")
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise OutlineError("PDF 已加密。请改用粘贴目录。")
        try:
            entries = _bookmarks(reader.outline)
            if entries and all(entry.depth == 0 for entry in entries):
                labels = [entry.label for entry in entries]
                entries = _normalize_levels(labels, _infer_levels(labels))
        except (PyPdfError, ValueError, KeyError, TypeError, RecursionError):
            entries = []
        entries = entries or _text_outline(reader)
    except (PyPdfError, OSError, ValueError, KeyError, TypeError, IndexError, RecursionError) as error:
        if isinstance(error, OutlineError):
            raise
        raise OutlineError("无法读取这个 PDF。请检查文件或粘贴目录。") from error
    if not entries:
        raise OutlineError("前 30 页未识别出可用目录。如果是扫描件，可以从其他来源复制目录后粘贴。")
    return entries
