"""Build the public sample files from the same catalog used by the local app."""

import argparse
from base64 import b64encode
import json
from pathlib import Path

from course_matcher.catalog import load_catalog
from course_matcher.export import export_csv
from course_matcher.matching import build_plan
from course_matcher.outline import parse_outline, sections_from


ROOT = Path(__file__).resolve().parents[1]
TABLE_START = "<!-- showcase:table:start -->"
TABLE_END = "<!-- showcase:table:end -->"


def video_info(recommendation):
    video = recommendation.video
    return {
        "title": video.part_title or video.title,
        "source": video.title if video.part_number else "",
        "part": video.part_number,
        "url": video.link,
        "reason": recommendation.reason,
    }


def showcase_files(root: Path) -> dict[Path, bytes]:
    examples, catalog = load_catalog()
    samples = []
    for example in examples:
        sections = sections_from(parse_outline(example.outline))
        plan = build_plan(sections, example.book, catalog)
        samples.append({
            "name": example.name,
            "book": example.book.title,
            "outline": example.outline,
            "rows": [
                {
                    "chapter": row.section.label,
                    "status": row.status,
                    "first": video_info(row.first) if row.first else None,
                    "alternatives": [video_info(item) for item in row.alternatives],
                    "search": row.search_url,
                }
                for row in plan.rows
            ],
            "csv": b64encode(export_csv(plan)).decode("ascii"),
        })

    table = ["| 教材小节 | 对应网课 |", "| --- | --- |"]
    for row in samples[0]["rows"]:
        video = row["first"]
        if video:
            label = f"第 {video['part']} 集 · {video['title']}" if video["part"] else video["title"]
            target = f"[{label}]({video['url']})"
        else:
            target = f'{row["status"]} · [到 B 站搜索]({row["search"]})'
        table.append(f'| {row["chapter"]} | {target} |')

    readme = (root / "README.md").read_text(encoding="utf-8")
    start = readme.index(TABLE_START) + len(TABLE_START)
    end = readme.index(TABLE_END, start)
    readme = readme[:start] + "\n\n" + "\n".join(table) + "\n\n" + readme[end:]
    math = examples[0]
    math_plan = build_plan(sections_from(parse_outline(math.outline)), math.book, catalog)
    return {
        root / "README.md": readme.encode(),
        root / "docs" / "samples.json": (json.dumps(samples, ensure_ascii=False, indent=2) + "\n").encode(),
        root / "docs" / "functions-and-limits.csv": export_csv(math_plan),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Report artifacts that need regeneration.")
    args = parser.parse_args()
    files = showcase_files(ROOT)
    if args.check:
        stale = [path.relative_to(ROOT) for path, data in files.items() if not path.is_file() or path.read_bytes() != data]
        if stale:
            parser.exit(1, "需要重新生成 " + "、".join(str(path) for path in stale) + "\n")
        return

    for path, data in files.items():
        path.write_bytes(data)


if __name__ == "__main__":
    main()
