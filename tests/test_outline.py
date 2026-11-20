from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from course_matcher.outline import Entry, OutlineError, extract_pdf_outline, format_outline, parse_outline, sections_from


def pdf_bytes(writer):
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def text_page(writer, lines):
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
    })
    stream = DecodedStreamObject()
    content = "BT /F1 12 Tf 50 740 Td 20 TL "
    content += " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    stream.set_data(content.encode("ascii"))
    page[NameObject("/Contents")] = stream


def test_infers_units_chapters_and_sections():
    outline = parse_outline("""目 录
第六单元 近代社会
第一章 制度的变化
第一节 英国的君主立宪制........17
第二节 美国独立战争…… 23
第二章 工业革命
""")
    assert [entry.depth for entry in outline] == [0, 1, 2, 2, 1]
    sections = sections_from(outline)
    assert [section.topic for section in sections] == ["英国的君主立宪制", "美国独立战争", "工业革命"]
    assert sections[0].parents == ("第六单元 近代社会", "第一章 制度的变化")
    assert parse_outline(format_outline(outline)) == outline


def test_indent_overrides_numbering_and_dotted_labels_group():
    assert parse_outline("复习\n  1.1 目标\n  1.2 要点\n附录") == [
        Entry("复习", 0), Entry("1.1 目标", 1), Entry("1.2 要点", 1), Entry("附录", 0),
    ]
    assert [section.topic for section in sections_from(parse_outline("1 基础\n1.1 概念\n1.2 规律\n2 练习"))] == [
        "概念", "规律", "练习",
    ]
    assert parse_outline("") == []
    assert parse_outline("第一节 Unix 1970")[0].label == "第一节 Unix 1970"


def test_pdf_prefers_nested_bookmarks_and_flattens_directory_wrapper():
    writer = PdfWriter()
    text_page(writer, ["Contents", "Chapter 1 Unused .......... 3"])
    writer.add_outline_item(title="封面", page_number=0)
    toc = writer.add_outline_item(title="目录", page_number=0)
    chapter = writer.add_outline_item(title="第一章 有机化学入门", page_number=0, parent=toc)
    writer.add_outline_item(title="1.1 有机化合物", page_number=0, parent=chapter)
    writer.add_outline_item(title="1.2 碳原子", page_number=0, parent=chapter)
    entries = extract_pdf_outline(pdf_bytes(writer))
    assert entries == [Entry("第一章 有机化学入门", 0), Entry("1.1 有机化合物", 1), Entry("1.2 碳原子", 1)]


def test_pdf_reads_text_directory_across_pages_and_stops_at_body():
    writer = PdfWriter()
    text_page(writer, ["A textbook"])
    text_page(writer, ["Table of Contents", "Chapter 1 Basics", "1.1 First topic .......... 3"])
    text_page(writer, ["1.2 Last topic .......... 9"])
    text_page(writer, ["Chapter 1 Basics", "This is the start of the actual book."])
    entries = extract_pdf_outline(pdf_bytes(writer))
    assert entries == [Entry("Chapter 1 Basics", 0), Entry("1.1 First topic", 1), Entry("1.2 Last topic", 1)]


def test_scan_corruption_encryption_and_page_limit_have_actionable_messages():
    blank = PdfWriter()
    blank.add_blank_page(width=100, height=100)
    with pytest.raises(OutlineError, match="扫描件"):
        extract_pdf_outline(pdf_bytes(blank))
    with pytest.raises(OutlineError, match="粘贴目录"):
        extract_pdf_outline(b"not a PDF")
    blank.encrypt("password")
    with pytest.raises(OutlineError, match="加密"):
        extract_pdf_outline(pdf_bytes(blank))

    long_pdf = PdfWriter()
    for _ in range(30):
        long_pdf.add_blank_page(width=100, height=100)
    text_page(long_pdf, ["Contents", "Chapter 1 Too late .......... 32"])
    with pytest.raises(OutlineError, match="30"):
        extract_pdf_outline(pdf_bytes(long_pdf))
