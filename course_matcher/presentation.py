from html import escape

from .matching import Plan, Recommendation


STYLE = """
<style>
[data-testid="stAppViewBlockContainer"] {
    max-width: 78rem;
    padding-top: 3.9rem;
    padding-bottom: 4rem;
}
.course-hero {
    background: linear-gradient(115deg, #123a32, #1e5b4d 74%, #286854);
    color: #f6fffb;
    border: 1px solid #245747;
    border-radius: 1.15rem;
    padding: 1.85rem clamp(1.2rem, 4vw, 2.75rem);
    margin: 0 0 .35rem;
}
.course-hero h1 {
    color: inherit;
    font-size: clamp(1.9rem, 4vw, 2.85rem);
    margin: 0 0 .4rem;
    padding: 0;
    letter-spacing: .025em;
}
.course-hero p { color: #def2e9; margin: 0; line-height: 1.6; }
.st-key-course_input, .st-key-course_preview {
    border: 1px solid #dce7e0;
    border-radius: .95rem;
    background: #ffffff;
    padding: clamp(.9rem, 2.5vw, 1.35rem);
}
.st-key-course_preview pre { white-space: pre-wrap; overflow-wrap: anywhere; }
.st-key-course_preview [data-testid="stText"] { max-height: 16rem; overflow: auto; }
.course-plan-scroll {
    overflow: auto;
    background: #fff;
    border: 1px solid #dce7e0;
    border-radius: .95rem;
}
.course-plan-scroll table {
    width: 100%;
    border-collapse: collapse;
    min-width: 42rem;
    text-align: left;
}
.course-plan-scroll th {
    background: #edf5ef;
    font-size: .92rem;
    font-weight: 650;
    text-align: left;
}
.course-plan-scroll th, .course-plan-scroll td {
    padding: .85rem 1rem;
    vertical-align: top;
    border-bottom: 1px solid #e4eee7;
    overflow-wrap: anywhere;
}
.course-plan-scroll tr:last-child td { border-bottom: 0; }
.course-plan-scroll .order { color: #536d61; width: 4.4rem; }
.course-plan-scroll td:nth-child(2) { width: 24%; }
.course-plan-scroll td:nth-child(3) { width: 36%; }
.course-plan-scroll small { display: block; color: #50695e; font-size: .88rem; margin-top: .2rem; }
.course-plan-scroll a { color: #086957; text-decoration-thickness: 1px; text-underline-offset: 3px; }
.course-plan-scroll .alternative + .alternative { margin-top: .75rem; }
.course-plan-scroll tr:hover td { background-color: #f9fcfa; }
@media (max-width: 640px) {
    [data-testid="stAppViewBlockContainer"] { padding-top: 3.3rem; }
    .course-plan-scroll table { display: block; min-width: 0; }
    .course-plan-scroll thead {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip-path: inset(50%);
    }
    .course-plan-scroll tbody, .course-plan-scroll tr, .course-plan-scroll td { display: block; }
    .course-plan-scroll tr { padding: .85rem 1rem; border-bottom: 1px solid #e4eee7; }
    .course-plan-scroll tr:last-child { border-bottom: 0; }
    .course-plan-scroll td { border: 0; padding: .3rem 0; }
    .course-plan-scroll td:nth-child(2), .course-plan-scroll td:nth-child(3) { width: auto; }
    .course-plan-scroll td:nth-child(3)::before, .course-plan-scroll td:nth-child(4)::before {
        display: block;
        color: #50695e;
        font-size: .88rem;
        margin: .25rem 0 .15rem;
        content: attr(data-label);
    }
    .course-plan-scroll .order { font-size: .88rem; }
    .course-plan-scroll .empty-alternatives { display: none; }
}
</style>
"""

HERO = """
<section class="course-hero">
  <h1>教材配课助手</h1>
  <p>导入教材目录，按小节匹配 B 站网课，生成可以照着学的计划表。</p>
</section>
"""


def _link(url: str, label: str) -> str:
    return f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>'


def _recommendation(value: Recommendation) -> str:
    return f"{_link(value.video.link, value.video.display_title)}<small>{escape(value.reason)}</small>"


def render_plan(plan: Plan) -> str:
    rows = []
    for index, row in enumerate(plan.rows, start=1):
        first = _recommendation(row.first) if row.first else "<strong>暂无可靠匹配</strong>"
        search = "" if row.first else f"<small>{_link(row.search_url, '到 B 站搜索')}</small>"
        alternatives = "".join(f'<div class="alternative">{_recommendation(item)}</div>' for item in row.alternatives)
        parents = " › ".join(row.section.parents)
        context = f"<small>{escape(parents)}</small>" if parents else ""
        alternatives_class = "" if alternatives else "empty-alternatives"
        rows.append(f"""
        <tr role="row">
            <td role="cell" class="order">{index}</td>
            <td role="cell"><strong>{escape(row.section.label)}</strong>{context}</td>
            <td role="cell" data-label="首选视频">{first}{search}</td>
            <td role="cell" data-label="备选视频" class="{alternatives_class}">{alternatives or '—'}</td>
        </tr>
        """)
    return f"""
    <div class="course-plan-scroll" tabindex="0" role="region" aria-label="教材与网课对照表">
        <table role="table" aria-label="教材与网课对照表">
            <thead><tr>
                <th scope="col">顺序</th><th scope="col">教材小节</th>
                <th scope="col">首选视频</th><th scope="col">备选视频</th>
            </tr></thead>
            <tbody role="rowgroup">{''.join(rows)}</tbody>
        </table>
    </div>
    """
