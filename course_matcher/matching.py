from collections.abc import Callable
from dataclasses import dataclass
import re
from unicodedata import normalize
from urllib.parse import urlencode

from .outline import Section, topic_of
from .videos import SearchError, Video


_UNINFORMATIVE = re.compile(r"^(?:导[论言读]|概[述论览念]|绪论|前言|引言|引入|介绍|定义|基本概念|概念与定义|基本原理|基本方法|性质|原理|应用|例题|总结|小结|复习|习题|练习)(?:[0-9一二三四五六七八九十]*)$")
_CHINESE_POSSESSIVE = re.compile(r"(?<=[\u3400-\u9fff])的(?=[\u3400-\u9fff])")
_EDITION = re.compile(r"第\s*([一二三四五六七八九十0-9]+)\s*版")
_DISCOURAGED = re.compile(r"预告|试听片段|混剪|广告推广|模考|刷题|习题|练习|题型|考点串讲")
_DIGITS = dict(zip("一二三四五六七八九十", range(1, 11), strict=True))

Search = Callable[[str], tuple[Video, ...]]


@dataclass(frozen=True)
class Book:
    title: str = ""
    subject: str = ""


@dataclass(frozen=True)
class Recommendation:
    video: Video
    reason: str


@dataclass(frozen=True)
class PlanRow:
    section: Section
    first: Recommendation | None
    alternatives: tuple[Recommendation, ...]
    search_url: str

    @property
    def status(self) -> str:
        return "已匹配" if self.first else "暂无可靠匹配"


@dataclass(frozen=True)
class Plan:
    rows: tuple[PlanRow, ...]
    search_issue: str | None = None
    skipped_searches: int = 0


def _normalized(value: str) -> str:
    value = normalize("NFKC", value).casefold()
    return "".join(char for char in _CHINESE_POSSESSIVE.sub("", value) if char.isalnum() or char in "+#")


def _similarity(query: str, text: str) -> float:
    if not query or not text:
        return 0.0
    if query in text:
        return 1.0
    if len(query) < 5:
        return 0.0
    grams = {query[index:index + 2] for index in range(len(query) - 1)}
    return sum(gram in text for gram in grams) / len(grams)


def _edition(text: str) -> str:
    match = _EDITION.search(normalize("NFKC", text))
    if not match:
        return ""
    return str(_DIGITS.get(match[1], match[1]))


def _score(section: Section, book: Book, video: Video) -> tuple[bool, float, str] | None:
    topic = _normalized(section.topic)
    title = _normalized(video.part_title or video.title)
    description = _normalized(video.description)
    metadata = _normalized(" ".join((video.title, video.description, video.subject)))
    parent_topic = _normalized(topic_of(section.parents[-1])) if section.parents else ""
    parent_matches = len(parent_topic) >= 2 and _similarity(parent_topic, metadata) >= 0.8
    subject = _normalized(book.subject)
    subject_matches = len(subject) >= 2 and _similarity(subject, metadata) >= 0.8
    book_title = _normalized(_EDITION.sub("", book.title))
    book_matches = len(book_title) >= 2 and _similarity(book_title, metadata) >= 0.8
    book_edition, video_edition = _edition(book.title), _edition(video.title)
    wrong_edition = bool(book_edition and video_edition and book_edition != video_edition)
    alias_match = topic in {_normalized(alias) for alias in video.aliases}
    title_match = max(_similarity(topic, title), float(alias_match))
    description_match = _similarity(topic, description)

    if _UNINFORMATIVE.fullmatch(topic) and not (parent_matches or subject_matches or book_matches):
        return None
    if title_match < 0.8 and description_match < 0.88:
        return None

    score = title_match * 5 + description_match + parent_matches * 1.25 + subject_matches + book_matches
    score += 1.25 if book_edition and book_edition == video_edition else 0
    score += 0.3 if video.curated else 0
    score -= 2 if wrong_edition else 0
    supplemental = bool(_DISCOURAGED.search(video.part_title or video.title))
    score -= 1.35 if supplemental else 0

    direct = title_match >= 0.8 and (not video.course or bool(video.part_number)) and not wrong_edition
    if wrong_edition:
        reason = "主题相关，视频所标教材版次不同。"
    elif video.part_number and title_match >= 0.8:
        reason = f"已核对第 {video.part_number} 集，分集主题与本节对应。"
    elif video.course:
        reason = "合集包含相关主题，具体分集待确认。"
    elif supplemental and direct:
        reason = "本视频通过例题或练习讲解相关主题。"
    elif direct:
        context = "，科目或上级章节也相符" if subject_matches or parent_matches else ""
        reason = f"视频标题对应本节主题{context}。"
    else:
        reason = "视频简介提到相关主题，可作为补充。"
    return direct, score, reason


def match_section(section: Section, book: Book, candidates: list[Video]) -> tuple[Recommendation | None, tuple[Recommendation, ...]]:
    ranked = []
    for video in candidates:
        match = _score(section, book, video)
        if match:
            direct, score, reason = match
            ranked.append((direct, score, Recommendation(video, reason)))
    ranked.sort(key=lambda result: (result[0], result[1]), reverse=True)

    first = ranked[0][2] if ranked and ranked[0][0] else None
    alternatives = []
    seen = {first.video.link} if first else set()
    for _, _, recommendation in ranked:
        video = recommendation.video
        if video.link in seen or (first and video.course and video.url == first.video.url and not video.part_number):
            continue
        seen.add(video.link)
        alternatives.append(recommendation)
        if len(alternatives) == 2:
            break
    return first, tuple(alternatives)


def query_for(section: Section, book: Book) -> str:
    fields = (section.topic, book.title, book.subject, topic_of(section.parents[-1]) if section.parents else "")
    terms = dict.fromkeys(" ".join(re.findall(r"[\w+#]+", field))[:110] for field in fields if field.strip())
    words = " ".join(filter(None, terms)).split()
    return " ".join((*words[:70], "讲解"))


def build_plan(
    sections: list[Section],
    book: Book,
    catalog: tuple[Video, ...],
    search: Search | None = None,
    cache: dict[str, tuple[Video, ...]] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Plan:
    cache = {} if cache is None else cache
    issue = None
    skipped = 0
    rows = []
    for index, section in enumerate(sections, start=1):
        query = query_for(section, book)
        candidates = list(catalog)
        if search is not None:
            if query not in cache and issue is None:
                try:
                    cache[query] = search(query)
                except SearchError as error:
                    issue = str(error)
            if query in cache:
                candidates.extend(cache[query])
            else:
                skipped += 1
        first, alternatives = match_section(section, book, candidates)
        search_url = "https://search.bilibili.com/all?" + urlencode({"keyword": query})
        rows.append(PlanRow(section, first, alternatives, search_url))
        if progress:
            progress(index, len(sections))
    return Plan(tuple(rows), issue, skipped)
