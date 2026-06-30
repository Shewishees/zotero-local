# alphaXiv-Local

将本地 Zotero 论文自动转化为结构化博客 + 笔记系统，仿 [alphaXiv.org](https://www.alphaxiv.org) 的 Blog 功能。

## 功能

- **Zotero 集成** — 直接读取本地 Zotero 数据库，展示所有论文
- **AI 博客生成** — DeepSeek API 驱动，支持学术型 / 故事型双风格
- **图片嵌入** — 从 PDF 提取图表嵌入博客正文
- **PDF 预览** — 浏览器原生 PDF 查看器，完整阅读
- **浮动目录** — 自动生成博客导航，滚动高亮
- **精读笔记** — AI 生成结构化笔记（问题/方法/结果/要点/AI摘要），存入 Obsidian
- **智能标签** — 自动推荐论文标签，支持手动编辑
- **AI 问答** — 选中博客文字即可提问，AI 结合论文上下文回答

## 架构

```
alphaxiv-local/
├── app.py              # Flask 主应用
├── config.py           # 配置（路径、API）
├── zotero_reader.py    # Zotero SQLite 读取
├── pdf_processor.py    # PDF 文本/图片提取
├── blog_generator.py   # AI 博客生成
├── note_manager.py     # 笔记管理 + Obsidian 同步
├── templates/          # Jinja2 前端模板
├── static/             # CSS / 图片
├── cache/              # 博客缓存
├── .env.example        # API Key 配置示例
└── requirements.txt
```

## 快速开始

### 1. 环境要求

- Python 3.10+
- [Zotero](https://www.zotero.org/) 本地安装（含论文 PDF）
- [DeepSeek API Key](https://platform.deepseek.com/)
- [Obsidian](https://obsidian.md/)（可选，用于笔记同步）

### 2. 安装

```bash
git clone https://github.com/yourname/alphaxiv-local.git
cd alphaxiv-local
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置

编辑 `config.py` 修改路径：

```python
ZOTERO_DB = "/path/to/zotero.sqlite"
ZOTERO_STORAGE = "/path/to/Zotero/storage"
OBSIDIAN_VAULT = "/path/to/Obsidian/Vault/笔记目录"
```

设置 API Key：

```bash
cp .env.example .env
# 编辑 .env 填入你的 DeepSeek API Key
```

或直接设置环境变量：

```bash
export DEEPSEEK_API_KEY=sk-xxx
```

### 4. 启动

```bash
python app.py
```

浏览器打开 **http://127.0.0.1:5000**

## 技术栈

- **后端**: Python Flask
- **PDF 处理**: PyMuPDF (fitz)
- **AI**: DeepSeek Chat API (OpenAI 兼容格式)
- **前端**: Jinja2 + Vanilla JS + Marked.js
- **笔记存储**: Markdown 文件 → Obsidian Vault

## 致谢

- 博客生成方法论基于 [paper-analyzer](https://github.com/yuan1z0825/paper-craft-skills) skill
- 灵感来源于 [alphaXiv.org](https://www.alphaxiv.org)

## License

MIT
