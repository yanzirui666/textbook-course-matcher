from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_users_can_try_examples_and_edit_the_outline(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
    assert not app.exception
    assert not app.checkbox

    for index, expected, count in [(0, "数列的极限", 10), (1, "二叉树的定义", 5), (2, "君主立宪制的英国", 5)]:
        app.selectbox[0].select_index(index).run()
        assert expected in app.text_area[0].value
        next(button for button in app.button if button.label == "生成学习计划").click().run()
        assert not app.exception
        assert any(f"已匹配 {count} 个" in caption.value for caption in app.caption)
        assert app.get("download_button")

    app.radio[0].set_value("粘贴目录").run()
    app.text_area[0].set_value("第一章 新教材\n  第一节 一个没有匹配的标题").run()
    assert not app.get("download_button")
    next(button for button in app.button if button.label == "生成学习计划").click().run()
    assert any("待匹配 1 个" in caption.value for caption in app.caption)
    assert app.get("download_button")
