"""笔记管理 + Obsidian 同步 + AI 精读笔记生成"""

import os, re, datetime, hashlib, httpx
from config import OBSIDIAN_VAULT, DEEPSEEK_API_KEY, DEEPSEEK_MODEL, DEEPSEEK_BASE_URL


# ================================================================
#  基础笔记 CRUD
# ================================================================

def create_note(paper_title, paper_authors, note_content, note_title="", tags=None):
    """
    在 Obsidian Vault 中创建 Markdown 笔记。

    Obsidian Properties（YAML frontmatter）格式:
      - title: 笔记标题
      - paper: wiki-link 到论文
      - authors: 作者列表
      - date: 创建时间
      - tags: 标签列表
    """
    if not note_content.strip():
        return ("", False, "笔记内容为空")

    safe_title = _safe_filename(note_title or paper_title)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = _ensure_unique(f"{date_str} - {safe_title}")

    tags_yaml = "\n  - ".join(tags) if tags else ""
    if tags_yaml:
        tags_yaml = "\n  - " + tags_yaml
    authors_str = ", ".join(paper_authors[:5])
    if len(paper_authors) > 5:
        authors_str += " 等"
    paper_link = _safe_wikilink(paper_title)

    # Obsidian Properties 格式
    content = f"""---
title: "{note_title or paper_title}"
paper: "[[{paper_link}]]"
authors: "{authors_str}"
date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
tags:{tags_yaml}
---

# 📝 {note_title or paper_title}

> **论文**: [[{paper_link}]]
> **作者**: {authors_str}
> **创建**: {datetime.datetime.now().strftime('%Y-%m-%d')}

---

{note_content.strip()}

---

*📌 本笔记由 alphaXiv-Local 创建，存储在 Obsidian Vault 中*
"""
    filepath = os.path.join(OBSIDIAN_VAULT, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return (filepath, True, "")
    except Exception as e:
        return ("", False, f"写入失败: {e}")


def update_note(filepath, note_content):
    """更新已有笔记内容，保留 frontmatter"""
    if not os.path.exists(filepath):
        return (False, "文件不存在")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            old = f.read()
        if old.startswith("---"):
            parts = old.split("---", 2)
            new = f"---{parts[1]}---\n\n{note_content.strip()}\n" if len(parts) >= 3 else note_content
        else:
            new = note_content
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new)
        return (True, "")
    except Exception as e:
        return (False, str(e))


def get_note(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def list_notes():
    notes = []
    if not os.path.exists(OBSIDIAN_VAULT):
        return notes
    for fn in sorted(os.listdir(OBSIDIAN_VAULT), reverse=True):
        if fn.endswith(".md"):
            fp = os.path.join(OBSIDIAN_VAULT, fn)
            with open(fp, "r", encoding="utf-8") as f:
                c = f.read()
            notes.append({
                "filename": fn, "filepath": fp,
                "title": _extract_title(c, fn),
                "preview": c[:8000],
                "modified": datetime.datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M"),
            })
    return notes


def find_notes_for_paper(paper_title):
    all_notes = list_notes()
    return [n for n in all_notes if _safe_wikilink(paper_title) in (get_note(n["filepath"]) or "")]


def delete_note(filepath):
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False


# ================================================================
#  AI 精读笔记生成
# ================================================================

def generate_structured_note(paper, full_text, source_type):
    """
    生成结构化精读笔记，存入 Obsidian。
    输出格式: 问题 / 方法 / 结果 / 要点 / AI摘要
    """
    if not DEEPSEEK_API_KEY:
        return (False, "未配置 API Key")

    title = paper.get('title', '')[:100]
    authors = ', '.join(paper.get('authors', [])[:5])
    journal = paper.get('publication', '') or '未知'
    doi = paper.get('DOI', '')
    abstract = paper.get('abstract', '')[:800]

    # 构建上下文
    if full_text:
        ctx = "论文全文:\n\n" + full_text[:6000]
    else:
        ctx = "摘要: " + abstract

    prompt = f"""你是资深学术研究者。请为以下论文生成一份精炼的结构化阅读笔记。

论文标题: {title}
作者: {authors}
期刊: {journal}
DOI: {doi or '无'}

{ctx}

---

请严格按照以下 Markdown 格式输出（不要输出任何开场白或结语，直接输出以下内容）:

---

## ❓ 研究问题

> 用 1-3 句话概括：这篇论文要解决什么核心问题？

（在此处填写）

---

## 🔬 方法与创新

> 研究者用了什么方法？关键创新点是什么？（3-5 句话）

（在此处填写。如果有具体的技术路线或实验设计，用列表列出关键步骤）

- 步骤 1：
- 步骤 2：
- 步骤 3：

---

## 📊 关键发现

> 最重要的实验结果是哪些？数据说明了什么？（3-5 句）

| 指标 | 本文方法 | Baseline | 提升 |
|------|---------|----------|------|
| （如有具体数据请填写） | | | |

（如果论文中没有具体的对比数据表，用列表总结关键发现）

---

## 💡 核心要点

> 这篇论文最值得记住的 3-5 个关键结论：

1.
2.
3.
4.
5.

---

## 🤖 AI 摘要

> 用一段话（≤200 字）通俗完整地概括：论文做了什么、怎么做的、发现了什么。

（在此处填写）

---

*🤖 本笔记由 DeepSeek AI 自动生成 | 基于 paper-analyzer 方法论*
"""

    try:
        resp = httpx.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": "你是学术笔记专家。你的输出直接保存为 Obsidian Markdown 文件。只输出笔记内容，使用规范的 Markdown 语法。标题用 ##，要点用列表，引用用 >，数据用表格。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
            },
            timeout=120.0,
        )
        data = resp.json()
        ai_content = data["choices"][0]["message"]["content"]

        # 后处理：确保内容以 ## 开头（去掉可能的开场白）
        ai_content = _clean_note_content(ai_content)

        # 包装为完整 Obsidian 笔记
        tags = ["精读笔记", "AI生成"]
        filepath, ok, err = create_note(
            title,
            paper.get("authors", []),
            ai_content,
            note_title=f"📖 {title[:50]}",
            tags=tags,
        )
        return (ok, err if not ok else filepath)

    except Exception as e:
        return (False, f"API 请求失败: {e}")


def _clean_note_content(text):
    """清理 AI 输出：去掉开场白，保留正文"""
    # 去掉可能的 "好的，以下是..." 开场
    lines = text.split("\n")
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("---"):
            start = i
            break
        if stripped.startswith("好的") or stripped.startswith("以下") or stripped.startswith("这是"):
            start = i + 1
            break
    return "\n".join(lines[start:]).strip()


# ================================================================
#  标签推荐
# ================================================================

def suggest_tags(paper):
    if not DEEPSEEK_API_KEY:
        return ["论文"]
    prompt = f"""根据论文信息推荐 5-8 个学术标签，覆盖：研究领域、方法、主题。
标题: {paper.get('title', '')}
摘要: {paper.get('abstract', '')[:600]}
期刊: {paper.get('publication', '')}

只输出标签，每行一个 # 开头，例如: #深度学习"""
    try:
        resp = httpx.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={"model": DEEPSEEK_MODEL, "messages": [
                {"role": "system", "content": "你是学术标签推荐专家。只输出标签。"},
                {"role": "user", "content": prompt},
            ], "temperature": 0.3, "max_tokens": 200}, timeout=30.0,
        )
        text = resp.json()["choices"][0]["message"]["content"]
        tags = []
        for line in text.split("\n"):
            tag = line.strip().lstrip("#").strip()
            if tag and len(tag) < 30:
                tags.append(tag)
        return tags[:8] if tags else ["论文"]
    except Exception:
        return ["论文"]


# ================================================================
#  Chat 问答
# ================================================================

def chat_about_paper(paper, blog_content, selected_text, question, history=None):
    if not DEEPSEEK_API_KEY:
        return "❌ API Key 未配置"
    context = f"""你是论文解读助手。帮助用户理解以下论文。
论文: {paper.get('title', '')}
作者: {', '.join(paper.get('authors', [])[:5])}
摘要: {paper.get('abstract', '')[:500]}
博客节选: {blog_content[:3000] if blog_content else '无'}
用户选中文字: "{selected_text}" """
    msgs = [{"role": "system", "content": context}]
    if history:
        msgs.extend(history[-10:])
    msgs.append({"role": "user", "content": question})
    try:
        resp = httpx.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={"model": DEEPSEEK_MODEL, "messages": msgs, "temperature": 0.5, "max_tokens": 1500},
            timeout=60.0,
        )
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ 请求失败: {e}"


# ================================================================
#  辅助函数
# ================================================================

def _safe_filename(title):
    safe = title.strip()
    safe = re.sub(r'[\\/:*?"<>|]', '-', safe)
    safe = re.sub(r'\s+', ' ', safe)
    return safe[:60].rstrip('. ')


def _safe_wikilink(title):
    return title.replace("[", "(").replace("]", ")").replace("|", "-")


def _ensure_unique(base_name):
    fn = f"{base_name}.md"
    if not os.path.exists(os.path.join(OBSIDIAN_VAULT, fn)):
        return fn
    i = 1
    while True:
        fn = f"{base_name} ({i}).md"
        if not os.path.exists(os.path.join(OBSIDIAN_VAULT, fn)):
            return fn
        i += 1


def _extract_title(c, fn):
    if c.startswith("---"):
        parts = c.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].split("\n"):
                if line.startswith("title:"):
                    return line.split(":", 1)[1].strip().strip('"')
    for line in c.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return fn.replace(".md", "")
