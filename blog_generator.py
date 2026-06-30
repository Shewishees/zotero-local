"""AI 博客生成模块 — paper-analyzer 方法论 + 图片嵌入"""

import os, re, hashlib, json, httpx
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_MODEL, DEEPSEEK_BASE_URL,
    CACHE_DIR, BLOG_TEMPERATURE, BLOG_MAX_TOKENS,
)

STYLES = {
    "storytelling": {"label": "故事型", "desc": "公众号爆文风格，生动比喻"},
    "academic": {"label": "学术型", "desc": "深度解析，专业严谨"},
}


def generate_blog(paper, full_text="", source_type="pdf", style="academic", images=None):
    """
    生成论文博客。

    参数:
        paper: dict
        full_text: str
        source_type: "pdf"|"abstract"|"none"
        style: "academic"|"storytelling"
        images: dict {"pages": [...], "figures": [...]}  图片信息

    返回:
        dict: {"markdown": str, "cached": bool, "source_type": str, "style": str}
    """
    cache_key = _cache_key(paper["key"], style)
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.md")

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            blog = f.read()
        # 后处理注入图片（缓存也可能之前没图片信息）
        blog = _inject_images(blog, images)
        return {"markdown": blog, "cached": True, "source_type": source_type, "style": style}

    if not DEEPSEEK_API_KEY:
        blog = _build_fallback(paper, images)
        return {"markdown": blog, "cached": False, "source_type": "fallback", "style": style}

    system = _build_system(style, images)
    user = _build_user_prompt(paper, full_text, source_type, style, images)

    try:
        resp = httpx.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": BLOG_TEMPERATURE, "max_tokens": BLOG_MAX_TOKENS, "stream": False,
            },
            timeout=180.0,
        )
        resp.raise_for_status()
        blog_md = resp.json()["choices"][0]["message"]["content"]

        # 后处理：注入真实图片
        blog_md = _inject_images(blog_md, images)
        blog_md = _post_process(blog_md, paper)

        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(blog_md)

        return {"markdown": blog_md, "cached": False, "source_type": source_type, "style": style}

    except Exception as e:
        return {"markdown": _build_error(paper, str(e)), "cached": False, "source_type": "error", "style": style}


def _cache_key(key, style):
    return f"{hashlib.md5(key.encode()).hexdigest()[:12]}_{style}"


# ============================================================
#  图片注入
# ============================================================

def _inject_images(markdown, images):
    """将博客中的 [FIG:N] 标记替换为实际提取的论文图片"""
    if not images:
        return markdown

    # 优先使用提取的嵌入图片 (figures)，其次才是页面图片
    figures = images.get("figures", [])
    if not figures:
        # 降级：用页面图片（但用户更想要 figures）
        pages = images.get("pages", [])
        if pages:
            page_map = {p["page"]: p for p in pages}
            def _rep(m):
                n = int(m.group(1))
                p = page_map.get(n)
                return f'\n\n![第{n}页]({p["path"]})\n\n>\n' if p else m.group(0)
            return re.sub(r'\[FIG:(\d+)\]', _rep, markdown)
        return markdown

    # 用提取的嵌入图片
    fig_map = {}
    for i, f in enumerate(figures):
        fig_map[i + 1] = f  # 1-indexed

    def replace_fig(m):
        n = int(m.group(1))
        f = fig_map.get(n)
        if f:
            return (
                f'\n\n![论文图 {n}]({f["path"]})\n\n'
                f'*▲ 图 {n}（原文第 {f["page"]} 页，{f["width"]}×{f["height"]}）*\n'
            )
        return m.group(0)

    return re.sub(r'\[FIG:(\d+)\]', replace_fig, markdown)


# ============================================================
#  System Prompt
# ============================================================

def _build_system(style, images=None):
    base = """⚠️ 生产级指令。你的任务：产出一篇让读者觉得"比我读论文还清楚"的深度 Markdown 长文。

你是资深学术论文解读专家。核心要求：
1. 吃透论文逻辑链：为什么做 → 怎么做 → 为什么这样设计 → 证据是什么
2. 每个核心创新独立展开：①问题 ②怎么做 ③为什么有效 ④与已有方法差异
3. 对关键实验数据深入解读——不只是报数字，要解释"这意味着什么"
4. 学术严谨但不死板——比论文好读

## 通用铁律
- 中文撰写（原标题/专有名词保留原文）
- **必须包含 `## 📑 目录` 章节**，列出所有二级标题的锚点链接
- ❌ 禁止 AI 套话："深入探讨""至关重要""值得注意的是"
- ❌ 禁止捏造论文中不存在的实验/数据/引用
- ✅ 不确定处标注「据论文推断」
- ✅ 数据翻译为可感知对比："提升 12%（67.3→75.4）"
"""

    # 图片标记指令
    img_instruction = ""
    if images:
        figures = images.get("figures", [])
        if figures:
            fig_list = "\n".join(
                f"│ 图 {i+1} │ 第 {f['page']} 页 │ {f['width']}×{f['height']} │"
                for i, f in enumerate(figures[:20])
            )
            img_instruction = f"""
## 📸 可用的论文原图
已从 PDF 中提取到 {len(figures)} 张嵌入图片。当博客中需要展示图表、实验结果、方法框架时，
用 `[FIG:N]` 标记插入（N 为图片编号）。

| 编号 | 所在页 | 尺寸 |
|------|--------|------|
{fig_list}

示例：
```
图 1 展示了 DEMATEL-TAISM 方法的分析框架 [FIG:1]
实验结果的对比数据如上表所示，其可视化呈现见 [FIG:3]
```

要求：
- 方法部分至少引用 1 处原文图片
- 实验结果部分至少引用 1 处原文图表
- **[FIG:N] 独占一行，前后留空行**
- 只用表格中的编号，不要编造不存在的编号
"""
        elif images.get("pages"):
            img_instruction = f"""
## 📸 可用图片
论文共 {len(images['pages'])} 页。重要图表可用 [FIG:N] 引用（N 为页码）。
"""

    if style == "academic":
        return base + img_instruction + """
## 学术型 硬标准
- ≥4000 字，≥8 章节
- 实验数据表 ≥2 张
- 指出局限 ≥2 处（含作者自述 ≥1）
- 对 ≥3 个关键实验做深入解读

## 结构
1. 论文信息卡（标题/作者/期刊/DOI）
2. 📑 目录（列出所有二级标题的锚点链接）
3. 一句话总结（≤100 字）
4. 研究背景与动机（4-5 段）
5. 方法详解（8-10 段，每个创新点独立成节）
6. 实验分析（4-6 段，表格+解读+消融实验）
7. 讨论（适用边界+未解决问题）
8. 局限分析（作者自述+独立判断）
9. 结论（凝练贡献+展望）
"""
    else:
        return base + img_instruction + """
## 故事型 硬标准
- ≥3000 字，≥2 个类比/比喻
- 用"你"和读者对话

## 结构
1. 钩子开头（反常识/共鸣场景）
2. 📑 目录（列出所有小节标题链接）
3. 为什么会这样（现有方法瓶颈）
4. 核心洞察（一句话发现+类比）
5. 方法详解（分步骤+类比）
6. 实验效果（"这意味着什么"）
7. 深层意义
8. 局限
9. 收束（闭环）+ 金句
"""


def _build_user_prompt(paper, full_text, source_type, style, images=None):
    title = paper.get("title", "")
    authors = ", ".join(paper.get("authors", []))
    pub = paper.get("publication", "") or ""
    date = paper.get("date", "") or ""
    doi = paper.get("DOI", "") or ""
    abstract = paper.get("abstract", "") or ""

    img_note = ""
    if images and images.get("figures"):
        figs = images["figures"]
        pages = sorted(set(f['page'] for f in figs))
        img_note = f"\n> 📸 本文共 {len(figs)} 张图（第 {', '.join(map(str, pages[:10]))}{'...' if len(pages)>10 else ''} 页）。用 [FIG:N] 标记引用。\n"

    header = f"""请为以下论文写一篇深度解读。严格按 system prompt 要求执行。

## 论文信息
- **标题**: {title}
- **作者**: {authors}
- **期刊**: {pub}
- **时间**: {date}
- **DOI**: {doi}
{img_note}
"""

    source_label = ""
    if source_type == "pdf" and full_text.strip():
        txt = full_text[:25000]
        source_label = f"\n## 论文全文（PDF 提取，{len(txt)} 字符）\n\n{txt}"
    elif source_type == "abstract" and full_text.strip():
        source_label = f"\n## 摘要\n{full_text[:3000]}"

    return header + source_label + f"""

---

**风格**: {STYLES[style]['label']}
**输出**: 只输出博客正文，不输出分析过程。图片引用用 [FIG:N] 标记。"""


# ============================================================
#  降级 / 错误处理
# ============================================================

def _build_fallback(paper, images=None):
    title = paper.get("title", "未知")
    authors = ", ".join(paper.get("authors", ["未知"]))
    abstract = paper.get("abstract", "") or "（无摘要）"
    blog = f"""# 📄 {title}

> **作者**: {authors}
> **来源**: {paper.get('publication', '未知')} ({paper.get('date', '')})

## 📝 摘要
{abstract}

> ⚠️ 离线降级版本。设置 `DEEPSEEK_API_KEY` 后重新生成即可获得深度解析。
"""
    return _inject_images(blog, images)


def _build_error(paper, error):
    return f"""# ❌ 生成失败

> 论文: {paper.get('title', '')}
> 错误: {error}

请稍后重试。"""


def _post_process(md, paper):
    """后处理：添加 frontmatter"""
    title = paper.get("title", "")
    authors = ", ".join(paper.get("authors", [])[:5])
    if len(paper.get("authors", [])) > 5:
        authors += " 等"
    header = f"""---
title: "{title}"
authors: "{authors}"
journal: "{paper.get('publication', '')}"
date: "{paper.get('date', '')}"
doi: "{paper.get('DOI', '')}"
---

"""
    if not md.startswith("---"):
        md = header + md
    return md
