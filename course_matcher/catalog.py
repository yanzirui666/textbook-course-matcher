from dataclasses import dataclass
from functools import cache
from importlib.resources import files
import json

from .matching import Book
from .videos import Video, canonical_video_url


@dataclass(frozen=True)
class Example:
    name: str
    book: Book
    outline: str


@cache
def load_catalog() -> tuple[tuple[Example, ...], tuple[Video, ...]]:
    data = json.loads(files("course_matcher").joinpath("data/catalog.json").read_text(encoding="utf-8"))
    examples = tuple(
        Example(item["name"], Book(item["book"], item["subject"]), "\n".join(item["outline"]))
        for item in data["examples"]
    )
    videos = []
    for record in data["videos"]:
        url = canonical_video_url(record["url"])
        if not url:
            raise ValueError(f"内置索引包含无效视频链接 {record['url']}")
        part = record.get("part_number")
        if part is not None and (type(part) is not int or part < 1 or not record.get("part_title")):
            raise ValueError(f"内置索引包含无效分集 {record['url']}")
        videos.append(Video(**{
            **record, "url": url, "aliases": tuple(record.get("aliases", ())), "curated": True,
        }))
    return examples, tuple(videos)
