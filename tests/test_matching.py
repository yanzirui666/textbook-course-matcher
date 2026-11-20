import csv
from io import StringIO
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from course_matcher.catalog import load_catalog
from course_matcher.export import export_csv
from course_matcher.matching import Book, build_plan, match_section
from course_matcher.outline import Section, parse_outline, sections_from
from course_matcher.videos import BraveSearch, SearchError, Video, canonical_video_url


def video(title, number=1, **kwargs):
    return Video(f"https://www.bilibili.com/video/av{number}/", title, **kwargs)


def test_all_examples_match_five_chapters_in_order():
    examples, catalog = load_catalog()
    expected_links = [
        [f"https://www.bilibili.com/video/BV1Eb411u7Fw/?p={part}" for part in [7, 10, 12, 14, 15]],
        [f"https://www.bilibili.com/video/{item}/" for item in [
            "BV1Hy4y1t7ij", "BV1CQ4y1e7av", "BV11P4y1L7in", "BV18i4y1Z7am", "BV1GY4y1u7b2",
        ]],
        [f"https://www.bilibili.com/video/{item}/" for item in [
            "BV1ew411k75L", "BV1QZ4y157tK", "BV17RyqBjEWi", "BV1pU1sBdEHg", "BV1MECeBnEzk",
        ]],
    ]
    for example, links in zip(examples, expected_links, strict=True):
        sections = sections_from(parse_outline(example.outline))
        plan = build_plan(sections, example.book, catalog)
        assert [row.section for row in plan.rows] == sections
        assert [row.first.video.link for row in plan.rows] == links
        assert all(len(row.alternatives) <= 2 and row.first.reason for row in plan.rows)


def test_context_and_edition_disambiguate_topic():
    section = Section("1.1 基本概念", "基本概念", ("第一章 树与二叉树",))
    biology = video("分子生物学 基本概念")
    computer_science = video("数据结构基本概念：树与二叉树", 2)
    first, alternatives = match_section(section, Book(subject="数据结构"), [biology, computer_science])
    assert first.video == computer_science
    assert alternatives == ()

    section = Section("1.2 数列极限", "数列极限", ())
    old = video("高等数学第七版 数列极限")
    new = video("高等数学第八版 数列极限", 2)
    first, alternatives = match_section(section, Book(title="高等数学第8版"), [old, new])
    assert first.video == new
    assert "版次不同" in alternatives[0].reason


def test_unconfirmed_collection_stays_an_alternative_and_preserves_missing_row():
    book = Book("线性代数", "数学")
    section = Section("第一节 矩阵乘法", "矩阵乘法", ("第一章 矩阵",))
    whole = video("线性代数全套", description="课程介绍矩阵乘法。")
    wrong = video("矩阵加法", 2)
    plan = build_plan([section], book, (whole, wrong))
    row = plan.rows[0]
    assert row.status == "暂无可靠匹配"
    assert row.first is None
    assert [alternative.video for alternative in row.alternatives] == [whole]
    assert "矩阵乘法" in parse_qs(urlsplit(row.search_url).query)["keyword"][0]


def test_partial_search_preserves_completed_results_and_retry_reuses_cache():
    sections = sections_from(parse_outline("甲主题\n乙主题\n丙主题"))
    fallback = video("乙主题", 2)
    known = video("甲主题")
    requests = []

    def unreliable(query):
        requests.append(query)
        if "乙主题" in query:
            raise SearchError("限流")
        return (known,)

    cache = {}
    partial = build_plan(sections, Book(), (fallback,), unreliable, cache)
    assert [row.first.video if row.first else None for row in partial.rows] == [known, fallback, None]
    assert partial.search_issue == "限流"
    assert partial.skipped_searches == 2
    assert len(requests) == 2
    requests.clear()

    def recovered(query):
        requests.append(query)
        return ()

    result = build_plan(sections, Book(), (fallback,), recovered, cache)
    assert result.search_issue is None
    assert result.rows[0].first.video == known
    assert len(requests) == 2
    assert not any("甲主题" in query for query in requests)


@pytest.mark.parametrize("url", [
    "http://bilibili.com/video/av123/",
    "https://bilibili.com.example.org/video/av123/",
    "https://www.bilibili.com@evil.example/video/av123/",
    "https://www.bilibili.com/opus/123",
    "https://www.bilibili.com/video/av123/more",
])
def test_canonical_url_accepts_only_direct_https_video_paths(url):
    assert canonical_video_url(url) is None


def test_brave_adapter_limits_scope_filters_links_and_leaves_parts_unconfirmed():
    def respond(request):
        assert request.url.host == "api.search.brave.com"
        assert request.headers["X-Subscription-Token"] == "fake-key"
        assert request.url.params["q"] == "数学 极限 site:bilibili.com lang:zh"
        return httpx.Response(200, json={"web": {"results": [
            {"title": "数学<strong>极限</strong>", "url": "https://bilibili.com/video/av123/?p=8", "description": "数学 &amp; 极限"},
            {"title": "无效链接", "url": "https://bilibili.com.example.org/video/av456/"},
            {"description": "缺少链接"},
        ]}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert BraveSearch(client, "fake-key")("数学 极限") == (Video(
            "https://www.bilibili.com/video/av123/", "数学 极限", "数学 & 极限", series=True,
        ),)


@pytest.mark.parametrize(("status", "message"), [(429, "限流"), (401, "密钥"), (503, "503")])
def test_brave_reports_unavailable_status(status, message):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status))) as client:
        with pytest.raises(SearchError, match=message):
            BraveSearch(client, "fake")("代数")


def test_brave_reports_timeout():
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(SearchError, match="超时"):
            BraveSearch(client, "fake")("代数")


def test_csv_has_excel_bom_ordered_rows_and_escapes_formulas():
    sections = [Section("第一节 树与二叉树", "树与二叉树", ("第一章 数据结构",)), Section("=1+1", "=1+1", ())]
    plan = build_plan(sections, Book(), (video("树与二叉树", description="二叉树基础"),))
    raw = export_csv(plan)
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw
    rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
    assert [row["顺序"] for row in rows] == ["1", "2"]
    assert rows[0]["教材章节"] == "第一章 数据结构 › 第一节 树与二叉树"
    assert rows[0]["首选链接"] == "https://www.bilibili.com/video/av1/"
    assert rows[1]["教材章节"] == "'=1+1"
    assert rows[1]["匹配状态"] == "暂无可靠匹配"
