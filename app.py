import os

import httpx
import streamlit as st

from course_matcher.catalog import load_catalog
from course_matcher.export import export_csv
from course_matcher.matching import Book, build_plan
from course_matcher.outline import MAX_PDF_MB, OutlineError, extract_pdf_outline, format_outline, parse_outline, sections_from
from course_matcher.presentation import HERO, STYLE, render_plan
from course_matcher.videos import BraveSearch


st.set_page_config(page_title="教材配课助手", page_icon="📗", layout="wide")
st.html(STYLE + HERO)

examples, catalog = load_catalog()
examples_by_name = {example.name: example for example in examples}
api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()


def load_example(example):
    st.session_state.book_title = example.book.title
    st.session_state.book_subject = example.book.subject
    st.session_state.draft_outline = example.outline


def switch_source():
    if st.session_state.outline_source == "试用示例":
        selected = st.session_state.get("example_name", examples[0].name)
        if not st.session_state.draft_outline.strip():
            load_example(examples_by_name[selected])
        return
    current = (st.session_state.book_title, st.session_state.book_subject, st.session_state.draft_outline)
    if any(current == (example.book.title, example.book.subject, example.outline) for example in examples):
        st.session_state.book_title = ""
        st.session_state.book_subject = ""
        st.session_state.draft_outline = ""


def import_pdf(upload):
    try:
        entries = extract_pdf_outline(upload.getvalue())
    except OutlineError as error:
        st.session_state.pdf_error = str(error)
    else:
        st.session_state.pdf_error = ""
        st.session_state.draft_outline = format_outline(entries)


if "draft_outline" not in st.session_state:
    load_example(examples[0])

input_column, preview_column = st.columns([1.14, 1], gap="medium")
with input_column, st.container(key="course_input"):
    st.subheader("导入教材目录")
    mode = st.radio(
        "目录来源", ("试用示例", "粘贴目录", "上传 PDF"), key="outline_source",
        horizontal=True, label_visibility="collapsed", on_change=switch_source,
    )
    if mode == "试用示例":
        name = st.selectbox(
            "选择示例", examples_by_name, key="example_name",
            on_change=lambda: load_example(examples_by_name[st.session_state.example_name]),
        )
        st.button("重新载入示例", on_click=load_example, args=(examples_by_name[name],))
    elif mode == "上传 PDF":
        upload = st.file_uploader("选择 PDF", type=["pdf"], max_upload_size=MAX_PDF_MB, key="uploaded_pdf")
        st.button("提取目录", disabled=upload is None, on_click=import_pdf, args=(upload,))
        if st.session_state.get("pdf_error"):
            st.warning(st.session_state.pdf_error)

    title_column, subject_column = st.columns(2)
    with title_column:
        book_title = st.text_input("书名（可选）", placeholder="可带教材版次", key="book_title", max_chars=120)
    with subject_column:
        subject = st.text_input("科目（可选）", placeholder="例如有机化学", key="book_subject", max_chars=80)

    raw_outline = st.text_area(
        "可编辑目录", placeholder="每行一个章或小节", height=225, key="draft_outline",
        help="可保留教材编号。需要手动指定层级时，每级用两个空格缩进。",
    )

entries = parse_outline(raw_outline)
sections = sections_from(entries)
with preview_column, st.container(key="course_preview"):
    st.subheader("确认目录与检索范围")
    if sections:
        st.markdown(f"**{len(sections)} 个小节**将依次加入计划")
        st.text(format_outline(entries))
    else:
        st.info("添加目录后，可在这里检查章节顺序和层级。")

    if api_key:
        live = st.checkbox("联网查找更多 B 站视频")
        st.caption("联网时只把确认后的书名、科目和章节关键词发送给 Brave Search。PDF 文件在本机处理。")
    else:
        live = False
        st.caption("当前使用内置视频索引。配置 BRAVE_SEARCH_API_KEY 后可联网查找更多 B 站视频。")

    book = Book(book_title.strip(), subject.strip())
    fingerprint = (book, tuple(sections), live)
    if st.button("生成学习计划", type="primary", disabled=not sections, width="stretch"):
        if live:
            indicator = st.progress(0.0, text="正在查找视频…")

            def update_progress(done, total):
                indicator.progress(done / total, text=f"已处理 {done} / {total} 个小节")

            cache = st.session_state.setdefault("search_cache", {})
            with httpx.Client(follow_redirects=False) as client:
                plan = build_plan(sections, book, catalog, BraveSearch(client, api_key), cache, update_progress)
            indicator.empty()
        else:
            plan = build_plan(sections, book, catalog)
        st.session_state["saved_plan"] = (fingerprint, plan)

saved = st.session_state.get("saved_plan")
if saved and saved[0] == fingerprint:
    plan = saved[1]
    st.subheader("学习计划表")
    if plan.search_issue:
        st.warning(f"{plan.search_issue}。{plan.skipped_searches} 个小节未完成联网检索，表中保留已有结果。"
                   "再次生成时会复用已经完成的搜索。")
    matched = sum(row.first is not None for row in plan.rows)
    st.caption(f"共 {len(plan.rows)} 个小节 · 已匹配 {matched} 个 · 待匹配 {len(plan.rows) - matched} 个")
    st.html(render_plan(plan))
    st.download_button(
        "下载 CSV", export_csv(plan), file_name="教材学习计划.csv", mime="text/csv; charset=utf-8",
        on_click="ignore",
    )
elif saved:
    st.caption("目录或检索设置已修改，重新生成后即可查看对应计划。")
