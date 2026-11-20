from dataclasses import dataclass
from html import unescape
import re
from urllib.parse import parse_qs, urlsplit

import httpx


BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
_VIDEO_PATH = re.compile(r"/video/(BV[0-9A-Za-z]{10}|av[1-9][0-9]*)/?")
_COLLECTION = re.compile(r"合集|全集|全[套册]|全\s*\d+\s*[节课集讲]|课程合集|完整课程|系列课程|选集|共\s*\d+\s*[节课集讲]")
_TEXT_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Video:
    url: str
    title: str
    description: str = ""
    subject: str = ""
    aliases: tuple[str, ...] = ()
    series: bool = False
    part_number: int | None = None
    part_title: str = ""
    curated: bool = False

    @property
    def link(self) -> str:
        return f"{self.url}?p={self.part_number}" if self.part_number else self.url

    @property
    def display_title(self) -> str:
        return f"{self.part_title} · {self.title}" if self.part_title else self.title

    @property
    def course(self) -> bool:
        return self.series or bool(_COLLECTION.search(self.title))


def canonical_video_url(value: str) -> str | None:
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    if url.scheme != "https" or url.netloc.lower() not in {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}:
        return None
    match = _VIDEO_PATH.fullmatch(url.path)
    return f"https://www.bilibili.com/video/{match[1]}/" if match else None


def _plain_text(value) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(_TEXT_TAG.sub(" ", unescape(value)).split())


class SearchError(Exception):
    pass


class BraveSearch:
    def __init__(self, client: httpx.Client, api_key: str):
        self.client = client
        self.api_key = api_key

    def __call__(self, query: str) -> tuple[Video, ...]:
        try:
            response = self.client.get(
                BRAVE_URL,
                headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
                params={
                    "q": f"{query} site:bilibili.com lang:zh",
                    "count": 10,
                    "result_filter": "web",
                    "safesearch": "strict",
                    "spellcheck": "false",
                },
                timeout=6.0,
            )
        except httpx.TimeoutException:
            raise SearchError("联网搜索超时") from None
        except httpx.RequestError:
            raise SearchError("无法连接搜索服务") from None

        if response.status_code == 429:
            raise SearchError("搜索服务限流，请稍后重试")
        if response.status_code in {401, 403}:
            raise SearchError("搜索服务拒绝了密钥，请检查配置")
        if not response.is_success:
            raise SearchError(f"搜索服务返回 HTTP {response.status_code}")

        try:
            results = response.json().get("web", {}).get("results", [])
        except (ValueError, AttributeError):
            raise SearchError("搜索服务返回了无法读取的结果") from None
        if not isinstance(results, list):
            raise SearchError("搜索服务返回了无法读取的结果")
        videos = []
        for result in results:
            if not isinstance(result, dict):
                continue
            result_url = _plain_text(result.get("url"))
            url = canonical_video_url(result_url)
            title = _plain_text(result.get("title"))
            if url and title:
                part_hint = "p" in parse_qs(urlsplit(result_url).query)
                videos.append(Video(url, title, _plain_text(result.get("description")), series=part_hint))
        return tuple(videos)
