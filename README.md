# 教材配课助手

把教材目录变成一张按小节排列的 B 站网课计划表。上传带书签或可复制文字的 PDF，或直接粘贴目录。确认后，每小节会显示首选视频、最多两个备选和推荐理由。能确认分集时会链接到具体分集。未找到可靠资源的小节仍会保留，并提供 B 站搜索入口。

## 本地运行

用 [uv](https://docs.astral.sh/uv/getting-started/installation/) 管理 Python 3.12 和依赖。在源码目录执行：

```bash
uv run --locked --no-dev streamlit run app.py
```

浏览器会打开本地网页，默认地址是 `http://127.0.0.1:8501`。选择「试用示例」，可以直接用高等数学、数据结构或历史各五个小节生成计划。选择「粘贴目录」或「上传 PDF」即可换成自己的材料。

### 整理自己的目录

每行放一个标题，支持常见的中文章、节编号和 `1.1` 式编号。也可以每级缩进两个空格来明确层级：

```text
第一章 函数与极限
  1.2 数列的极限
  1.3 函数的极限
第二章 导数
  2.1 导数的定义
```

PDF 上限 20 MB。优先读取书签，没有可用书签时从前 30 页提取目录文字。若遇到扫描件、加密文件或提取结果不全，可直接修改可编辑目录或粘贴文本。填写书名、版次或科目有助于区分同名章节。生成的 CSV 使用带 BOM 的 UTF-8，便于用 Excel 打开。

### 联网查找更多资源

从 [Brave Search](https://api-dashboard.search.brave.com/app/keys) 获得 API 密钥，将它设置为启动进程的环境变量 `BRAVE_SEARCH_API_KEY`。可以用终端的隐藏输入读取密钥：

```bash
# Bash 或 Zsh
printf 'Brave Search API key: '
IFS= read -rs BRAVE_SEARCH_API_KEY
printf '\n'
export BRAVE_SEARCH_API_KEY
uv run --locked --no-dev streamlit run app.py
```

```powershell
# PowerShell 7.2+
$env:BRAVE_SEARCH_API_KEY = Read-Host "Brave Search API key" -MaskInput
uv run --locked --no-dev streamlit run app.py
```

启动网页后勾选「联网查找更多 B 站视频」，再生成计划。每个不同的小节查询最多请求一次 Brave Search，连续使用时会在当前页面会话中复用已完成的查询。超时或限流时，计划表保留已取得的结果和内置索引匹配，可以稍后再次生成。

教材 PDF 在本机内存中处理。勾选联网选项后，发给 Brave Search 的仅有根据确认后的书名、科目、章节标题生成的查询。程序使用 Brave 已索引的 B 站视频页面，检索范围取决于其索引。联网推荐依据标题、摘要和章节上下文，视频能否播放及内容细节以原页为准。

## 开发与贡献

```bash
uv run --locked pytest -q
```

`app.py` 提供网页入口，`course_matcher/` 包含目录解析、检索、匹配和 CSV 导出。内置索引位于 `course_matcher/data/catalog.json`。贡献视频时，请提供原视频页链接，核对主题、对应的分集编号及分集标题。示例中的宋浩老师高数分集可在 [B 站选集列表](https://www.bilibili.com/list/ml2772390947?bvid=BV1Eb411u7Fw&oid=48624233) 和 [分集目录](https://www.bilibili.com/opus/855060162516353042) 中核对。

项目代码采用 [MIT 许可证](LICENSE)。课程链接指向 B 站原页面，视频内容的权利归相应权利人。
