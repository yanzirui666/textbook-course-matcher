import csv
from io import StringIO

from .matching import Plan, Recommendation


def _cell(value: str) -> str:
    # Excel treats these leading characters as formulas even in quoted CSV cells.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value


def _recommendation_fields(value: Recommendation | None) -> tuple[str, str, str]:
    return (value.video.display_title, value.video.link, value.reason) if value else ("", "", "")


def export_csv(plan: Plan) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow([
        "顺序", "教材章节", "匹配状态", "首选视频", "首选链接", "首选理由",
        "备选一", "备选一链接", "备选一理由", "备选二", "备选二链接", "备选二理由", "B站搜索",
    ])
    for index, row in enumerate(plan.rows, start=1):
        first_alt, second_alt = (*row.alternatives, None, None)[:2]
        fields = (
            row.section.path, row.status, *_recommendation_fields(row.first),
            *_recommendation_fields(first_alt), *_recommendation_fields(second_alt), row.search_url,
        )
        writer.writerow([index, *map(_cell, fields)])
    return buffer.getvalue().encode("utf-8-sig")
