# alphaXiv-Local 架构文档

## 1. 项目概述

**alphaXiv-Local** 是一个本地的学术论文阅读系统，将 Zotero 中的论文自动转化为 AI 驱动的结构化博客，并支持笔记同步到 Obsidian。

### 核心功能清单

| 功能 | 说明 |
|------|------|
| 📄 **论文管理** | 读取本地 Zotero 数据库（zotero.sqlite），展示期刊/会议/预印本论文 |
| 📖 **AI 博客生成** | DeepSeek API 生成结构化博客（学术型/故事型双风格），带浮动目录 |
| 🖼 **论文图片嵌入** | AI 博客中自动引用 Python 从 PDF 提取的嵌入图表 |
| 📕 **PDF 预览** | 浏览器原生 iframe 查看器，完整阅读论文 PDF |
| 📝 **笔记系统** | 手动笔记 + AI 精读笔记（问题/方法/结果/要点/AI摘要 五部分），存入 Obsidian |
| 🏷 **标签推荐** | AI 自动推荐论文标签，支持手动添加/删除 |
| 💬 **AI 问答** | 选中博客文字后提问，AI 结合论文上下文回答 |
| 🔍 **搜索/分类** | 按标题/作者/摘要搜索，按 Zotero 分类筛选 |

---

## 2. 项目结构

```
alphaxiv-local/
├── app.py              # Flask 主应用（路由、API 端点）
├── config.py           # 全局配置（路径、API Key、参数）
├── zotero_reader.py    # Zotero SQLite 数据库只读访问层
├── pdf_processor.py    # PDF 文本提取 + 图片渲染/提取
├── blog_generator.py   # AI 博客生成（prompt 工程 + 图片注入）
├── note_manager.py     # 笔记 CRUD + AI 笔记 + 标签推荐 + Chat
├── start.sh            # 启动脚本（加载 .env）
├── .env                # API Key（不入 git）
├── .env.example        # API Key 模板（入 git）
├── requirements.txt    # Python 依赖
├── .gitignore
├── cache/              # 生成的博客缓存（Markdown 文件）
├── static/
│   ├── style.css       # 全局样式（186 行）
│   └── images/         # PDF 渲染的图片（不入 git）
└── templates/
    ├── index.html      # 首页：论文卡片列表
    ├── blog.html       # 详情页：论文信息/AI 博客 Tab + 右侧笔记面板 + 聊天
    └── notes.html      # 笔记管理页
```

---

## 3. 技术栈

| 层 | 技术 | 版本要求 |
|----|------|---------|
| Web 框架 | Flask | ≥3.0 |
| PDF 处理 | PyMuPDF (fitz) | ≥1.24 |
| HTTP 客户端 | httpx | ≥0.27 |
| AI API | DeepSeek Chat (OpenAI 兼容 `/chat/completions`) | — |
| 前端 | Jinja2 + Vanilla JS + Marked.js (CDN) | — |
| 数据源 | Zotero SQLite（只读） | Zotero 6/7 |
| 笔记存储 | Markdown 文件 → Obsidian | — |

---

## 4. 模块详解

### 4.1 `config.py` — 配置中心

```python
ZOTERO_DB     = "/mnt/c/Users/24974/Zotero/zotero.sqlite"  # Zotero 数据库路径
ZOTERO_STORAGE = "/mnt/c/Users/24974/Zotero/storage"        # PDF 存储目录
OBSIDIAN_VAULT = "/mnt/c/Users/24974/Documents/Obsidian Vault/文献"  # 笔记目录
CACHE_DIR      = "<项目根>/cache"                            # 博客缓存

DEEPSEEK_API_KEY = 从 .env 读取                              # API Key
DEEPSEEK_MODEL   = "deepseek-chat"                           # 可选 deepseek-reasoner
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

FLASK_HOST = "0.0.0.0"   # 必须 0.0.0.0，否则 WSL2 的 Windows 端无法访问
FLASK_PORT = 5000
```

**`.env` 加载机制**：`config.py` 启动时自动读取项目根目录的 `.env` 文件，将其中的 `KEY=VALUE` 注入 `os.environ`（不覆盖已有环境变量）。

**启用条件**：`.env` 文件存在即可。如果 `.env` 不存在，需手动设置环境变量 `DEEPSEEK_API_KEY`。

---

### 4.2 `zotero_reader.py` — 数据访问层

**工作方式**：只读连接 `zotero.sqlite`（URI 模式 `file:path?mode=ro`），不会修改 Zotero 数据。

**Zotero 数据库关键表结构**：

```
items           —— 所有条目（论文、笔记、附件等）
itemTypes       —— 条目类型（journalArticle=22, conferencePaper=11, preprint=31）
itemData        —— 条目字段数据（桥接表）
itemDataValues  —— 字段实际值
fieldsCombined  —— 字段名映射（fieldID=1→title, 2→abstractNote, 8→DOI...）
creators        —— 作者姓名
itemCreators    —— 条目-作者关联
itemAttachments —— 附件（PDF 路径格式: "storage:filename.pdf"）
itemNotes       —— Zotero 笔记（HTML 格式）
collections     —— Zotero 分类/文件夹
```

**核心函数**：

| 函数 | 返回 | 说明 |
|------|------|------|
| `get_all_papers()` | `list[dict]` | 所有期刊/会议/预印本论文，含元数据+作者+PDF路径+笔记预览 |
| `get_paper(item_id)` | `dict` | 单篇论文 |
| `get_paper_by_key(key)` | `dict` | 通过 Zotero item key 查找 |
| `search_papers(q)` | `list[dict]` | 按标题/作者/摘要模糊搜索 |
| `get_collections()` | `list` | Zotero 分类列表 |
| `get_papers_by_collection(id)` | `list[dict]` | 按分类筛选 |
| `get_full_notes(item_id)` | `list[dict]` | 某论文的全部 Zotero 笔记（纯文本） |

**论文 dict 结构**：
```python
{
    "item_id": 60,           # Zotero 内部 ID（整数）
    "key": "5U3SI5MG",       # Zotero item key（字符串，对应 storage 目录名）
    "type": "journalArticle",
    "title": "...",
    "abstract": "...",
    "date": "2025",
    "DOI": "10.xxx",
    "publication": "西北工业大学学报",
    "volume": "44",
    "issue": "1",
    "pages": "1-10",
    "authors": ["冯传宴", "李志忠", ...],
    "pdf_path": "/mnt/c/Users/24974/Zotero/storage/5U3SI5MG/xxx.pdf",
    "notes": [{"id": 50, "preview": "前200字"}]
}
```

**PDF 路径解析**：Zotero 内部存储格式为 `storage:filename.pdf`。解析逻辑：
1. 从 `itemAttachments` 表通过 `parentItemID` 找到附件记录
2. 取其 `path` 字段（去掉 "storage:" 前缀）= `filename.pdf`
3. 取其对应 `items.key` = `attach_key`
4. 拼接：`ZOTERO_STORAGE / attach_key / filename.pdf`

---

### 4.3 `pdf_processor.py` — PDF 处理

**文本提取**（`extract_text`）：
- 使用 `fitz.open()` 打开 PDF
- 逐页调用 `page.get_text("text")`
- 截断到 30000 字符（`BLOG_MAX_PDF_CHARS`）
- 返回 `(text, page_count, success, error)`

**页面渲染**（`extract_page_images`）：
- 将 PDF 每页渲染为 PNG 图片（120 dpi）
- 保存到 `static/images/<paper_key>/page_N.png`
- 通过 Flask 静态文件服务访问

**嵌入图片提取**（`extract_figures`）：
- 使用 `page.get_images(full=True)` 获取每页嵌入图片的 xref
- 用 `doc.extract_image(xref)` 提取二进制数据
- 过滤小于 20000 像素² 的图标
- 保存到 `static/images/<paper_key>/figures/`

---

### 4.4 `blog_generator.py` — AI 博客生成

**设计理念**：基于 `paper-analyzer` skill 的 academic 方法论，通过精心设计的 System Prompt 控制 DeepSeek 输出高质量结构化博客。

**核心流程**：

```
generate_blog(paper, full_text, source_type, style, images)
  │
  ├─ 1. 检查缓存（cache/<hash>_<style>.md）
  │     └─ 命中 → 读取 + _inject_images() → 返回
  │
  ├─ 2. 无 API Key → _build_fallback() → 返回降级博客
  │
  ├─ 3. _build_system(style, images) → System Prompt
  │     _build_user_prompt(paper, text, ...) → User Prompt
  │
  ├─ 4. POST /chat/completions → DeepSeek API
  │
  ├─ 5. _inject_images() → 将 [FIG:N] 替换为实际 <img> 标签
  │    _post_process() → 添加 YAML frontmatter
  │
  └─ 6. 写入缓存 + 返回 Markdown
```

**System Prompt 关键指令**：
- 禁止 AI 套话（"深入探讨"、"至关重要"等）
- 强制包含 `## 📑 目录` 章节
- 数据翻译为可感知对比（"提升 12%（67.3→75.4）"）
- 图片引用使用 `[FIG:N]` 标记（后处理替换）
- Academic 风格要求：≥4000 字、≥8 章节、≥2 数据表、≥2 局限分析
- Storytelling 风格要求：≥3000 字、≥2 类比、用"你"对话

**缓存策略**：文件名格式 `{MD5(paper_key)[:12]}_{style}.md`。同一论文不同风格分别缓存。

---

### 4.5 `note_manager.py` — 笔记管理

**手动笔记**（`create_note`）：
- 生成 Obsidian Properties 格式的 YAML frontmatter
- 支持 tags（YAML 数组）、paper wiki-link（`[[论文名]]`）
- 文件名：`日期 - 标题.md`
- 自动处理特殊字符（`\ / : * ? " < > |` → `-`）

**AI 精读笔记**（`generate_structured_note`）：
- Prompt 要求输出五段式结构：`❓研究问题` / `🔬方法与创新` / `📊关键发现` / `💡核心要点` / `🤖AI摘要`
- 每段用 `---` 分隔，引用用 `>` 前缀
- 自动保存到 Obsidian Vault

**标签推荐**（`suggest_tags`）：
- 调用 DeepSeek，输出 `#标签名` 格式
- 解析后返回列表，前端渲染为可编辑 chip

**AI 问答**（`chat_about_paper`）：
- Context = 论文标题/作者/摘要 + 博客节选 + 用户选中文字
- 支持多轮对话历史（保留最近 10 轮）
- Temperature=0.5，max_tokens=1500

---

### 4.6 `app.py` — Flask 路由表

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页：论文卡片列表（支持 `?q=` 搜索、`?collection=` 筛选） |
| `/paper/<id>` | GET | 论文详情页（论文信息 + 博客 + 笔记面板 + 聊天） |
| `/paper/<id>/generate` | POST | 生成博客（AJAX，body: `{"style":"academic"}`） |
| `/paper/<id>/quick-note` | POST | 生成精读笔记并存入 Obsidian（AJAX） |
| `/paper/<id>/tags` | GET | 获取推荐标签 |
| `/paper/<id>/tags` | POST | 保存用户标签 |
| `/paper/<id>/chat` | POST | AI 问答（body: `{"selected_text":"...","question":"...","history":[],"blog_content":"..."}`） |
| `/paper/<id>/images` | GET | 获取 PDF 渲染页面图片信息 |
| `/paper/<id>/page-texts` | GET | 获取 PDF 每页提取文字 |
| `/pdf/<key>` | GET | 直接提供 PDF 文件流（iframe 嵌入用） |
| `/api/papers` | GET | JSON API：论文列表 |
| `/api/paper/<id>` | GET | JSON API：单篇论文 |
| `/api/notes` | GET/POST/DELETE | 笔记 CRUD |
| `/notes` | GET | 笔记管理页 |

**⚠️ 已知坑**：路由函数命名不能与导入的函数同名（如 `chat_api` vs `chat_about_paper`），否则会递归调用自身导致 500 错误。

---

### 4.7 前端模板

**`index.html`** — 论文列表页：
- 搜索栏 + Zotero 分类筛选下拉框
- 论文卡片网格（`paper-grid`）：标题、作者、摘要预览、生成/阅读按钮
- 已有博客的论文显示 "📝 已有博客" badge

**`blog.html`** — 详情页（最复杂的模板）：
- **左侧主区域**：Tab 切换（📄论文信息 / 📖AI博客）
  - 论文信息 Tab：元数据卡片 + 摘要 + AI 操作区（风格选择、生成博客、生成笔记按钮）+ 标签编辑 + 可折叠 PDF 查看器
  - AI 博客 Tab：浮动目录（`blog-toc`，sticky + overflow-y:auto）+ 博客正文（marked.js 渲染 Markdown）
- **右侧面板**（sticky，340px 宽）：
  - 笔记面板：文本编辑器 + 标签输入 + 已有笔记列表
  - 聊天面板：对话历史 + 输入框 + 选中文字展示

**`notes.html`** — 笔记管理页：
- 笔记卡片列表（Markdown 渲染，跳过 frontmatter）

**CSS 关键变量**（`style.css`）：
```css
--font-serif: "Noto Serif SC", Georgia  /* 博客正文 */  
--font-sans: "PingFang SC", sans-serif /* UI 元素 */
```

---

## 5. 数据流

```
Windows Zotero 软件
  │
  ├── zotero.sqlite ─────────► zotero_reader.py ─► 论文元数据
  │
  └── storage/<key>/*.pdf ──► pdf_processor.py
         │                          │
         │                          ├── 文本 ──► blog_generator.py ──► DeepSeek API ──► Blog Markdown
         │                          │
         │                          ├── 嵌入图片 ──► [FIG:N] 注入 ──► Blog 中的 <img>
         │                          │
         │                          ├── 页面图片 ──► /api/paper/<id>/images
         │                          │
         │                          └── 每页文字 ──► /api/paper/<id>/page-texts
         │
         └── /pdf/<key> ──────────────────────────► iframe 嵌入
```

## 6. 配置与部署

### 6.1 新维护者接入步骤

```bash
# 1. 克隆代码
git clone https://github.com/Shewishees/zotero-local
cd zotero-local

# 2. 创建虚拟环境
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. 修改 config.py 中的路径
# ZOTERO_DB = "你的 Zotero 数据库路径"
# ZOTERO_STORAGE = "你的 Zotero storage 目录"
# OBSIDIAN_VAULT = "你的 Obsidian 笔记目录"

# 4. 配置 API Key
echo "DEEPSEEK_API_KEY=sk-你的key" > .env

# 5. 启动
python app.py
# 打开 http://127.0.0.1:5000
```

### 6.2 WSL2 特别说明

- Flask 必须绑定 `0.0.0.0`（不是 `127.0.0.1`），否则 Windows 浏览器无法访问
- Zotero 路径在 WSL 中为 `/mnt/c/Users/...`
- 如果 Zotero 安装在 Windows，确保 `zotero.sqlite` 路径正确（可能在 `C:\Users\<name>\Zotero\`）

### 6.3 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `DEEPSEEK_API_KEY` | 否* | — | DeepSeek API Key（`.env` 文件也可） |
| `FLASK_SECRET_KEY` | 否 | 内置 dev key | Flask session 密钥 |

*不设置则博客生成降级为仅显示摘要

---

## 7. 已知限制与注意事项

1. **硬件要求**：Python 3.10+，PyMuPDF 需要系统有渲染库
2. **PDF 文字选中**：iframe 嵌入的 PDF 文字无法被 JS 选中到聊天框（浏览器 PDF 插件隔离），只能选中博客正文文字
3. **大 PDF**：超过 30000 字符会被截断后送入 API
4. **论文图片提取**：仅提取 PDF 中嵌入的独立图片（非扫描页），过滤小于 20000px² 的图标
5. **Zotero 数据库**：只读连接，不会修改任何数据。确保 Zotero 软件未同时写入数据库（一般不会有问题）
6. **缓存**：手动删除 `cache/*.md` 可强制重新生成博客
7. **笔记**：直接写入 Obsidian Vault 目录的 `.md` 文件，Obsidian 重启后会自动索引
8. **多用户**：不支持，设计为单用户本地工具

---

## 8. 扩展指南

### 8.1 更换 AI 提供商

编辑 `blog_generator.py` 和 `note_manager.py`，修改 API 调用格式。当前使用 OpenAI 兼容的 `/chat/completions` 接口，任何兼容此格式的服务（OpenAI / DeepSeek / Moonshot / 通义千问 / 本地 Ollama）只需改 `DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL`。

### 8.2 添加新的博客风格

1. 在 `blog_generator.py` 的 `STYLES` 字典添加新条目
2. 在 `_build_system()` 添加对应风格的 `elif style == "xxx":` 分支
3. 在 `blog.html` 的 style-selector 区域添加新 radio button

### 8.3 支持更多论文类型

修改 `zotero_reader.py` 中 `get_all_papers()` 的 `item_types` 默认值，例如添加 `"thesis"`、`"bookSection"`。
