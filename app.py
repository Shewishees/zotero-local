"""Flask 主应用 — 博客 + 笔记的 Web 界面"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, redirect, url_for, jsonify
from config import FLASK_HOST, FLASK_PORT, SECRET_KEY, OBSIDIAN_VAULT
from zotero_reader import (
    get_all_papers,
    get_paper,
    get_paper_by_key,
    search_papers,
    get_collections,
    get_papers_by_collection,
    get_full_notes,
)
from pdf_processor import extract_text_from_paper
from blog_generator import generate_blog
from note_manager import (
    create_note,
    update_note,
    list_notes,
    find_notes_for_paper,
    delete_note,
    get_note,
    generate_structured_note,
    suggest_tags,
    chat_about_paper,
)

app = Flask(__name__)
app.secret_key = SECRET_KEY

# 全局论文缓存（避免重复读数据库）
_papers_cache = None


def load_papers():
    global _papers_cache
    if _papers_cache is None:
        _papers_cache = get_all_papers()
    return _papers_cache


# ==================== 路由 ====================


@app.route("/")
def index():
    """首页 — 论文博客列表"""
    query = request.args.get("q", "").strip()
    collection_id = request.args.get("collection", "").strip()

    if query:
        papers = search_papers(query)
    elif collection_id:
        papers = get_papers_by_collection(int(collection_id))
    else:
        papers = load_papers()

    collections = get_collections()

    # 标记哪些论文已有缓存博客
    from config import CACHE_DIR
    import hashlib

    cached_keys = set()
    for f in os.listdir(CACHE_DIR):
        if f.endswith(".md"):
            cached_keys.add(f.replace(".md", ""))

    for p in papers:
        cache_key = hashlib.md5(p["key"].encode()).hexdigest()[:16]
        p["has_blog"] = cache_key in cached_keys

    from note_manager import list_notes as ln
    return render_template(
        "index.html",
        papers=papers,
        collections=collections,
        current_collection=collection_id,
        query=query,
        total=len(papers),
        notes_count=len(ln()),
    )


@app.route("/paper/<int:item_id>")
def blog_detail(item_id):
    """论文博客详情页 + 笔记面板"""
    paper = get_paper(item_id)
    if not paper:
        return "论文未找到", 404

    # 获取已有的博客内容（尝试匹配任意风格的缓存）
    import hashlib
    import glob as _glob
    from config import CACHE_DIR

    blog_content = ""
    blog_source = "none"
    blog_style = ""

    base_key = hashlib.md5(paper["key"].encode()).hexdigest()[:12]
    # 查找匹配的缓存文件（支持旧格式和新格式）
    patterns = [
        os.path.join(CACHE_DIR, f"{base_key}.md"),        # 旧格式
        os.path.join(CACHE_DIR, f"{base_key}_*.md"),       # 新格式
    ]
    found = []
    for pat in patterns:
        found.extend(_glob.glob(pat))
    # 可能有多个风格缓存，取最新的
    if found:
        cache_path = max(found, key=os.path.getmtime)
        with open(cache_path, "r", encoding="utf-8") as f:
            blog_content = f.read()
        blog_source = "cached"
        # 推断风格
        if "_academic" in cache_path or "academic" in blog_content[:200]:
            blog_style = "academic"
        elif "_storytelling" in cache_path or "storytelling" in blog_content[:200]:
            blog_style = "storytelling"

    # Zotero 原生笔记
    zotero_notes = get_full_notes(item_id)

    # Obsidian 中与此论文相关的笔记
    obsidian_notes = find_notes_for_paper(paper["title"])

    return render_template(
        "blog.html",
        paper=paper,
        blog_content=blog_content,
        blog_source=blog_source,
        blog_style=blog_style,
        zotero_notes=zotero_notes,
        obsidian_notes=obsidian_notes,
    )


@app.route("/paper/<int:item_id>/generate", methods=["POST"])
def generate_blog_post(item_id):
    """触发生成博客（AJAX 接口），同步提取图片嵌入博客"""
    paper = get_paper(item_id)
    if not paper:
        return jsonify({"success": False, "error": "论文未找到"}), 404

    style = request.json.get("style", "academic") if request.is_json else "academic"

    # 1. 提取 PDF 文本
    full_text, pages, source_type = extract_text_from_paper(paper)

    # 2. 提取 PDF 图片（嵌入博客用）
    images = None
    pdf_path = paper.get("pdf_path")
    if pdf_path:
        try:
            from pdf_processor import get_figure_context
            images = get_figure_context(pdf_path, paper["key"])
        except Exception:
            pass  # 图片提取失败不阻塞博客生成

    # 3. 生成博客（传入图片信息）
    result = generate_blog(paper, full_text, source_type, style=style, images=images)

    return jsonify({
        "success": True,
        "markdown": result["markdown"],
        "cached": result["cached"],
        "source_type": result["source_type"],
        "style": result.get("style", style),
    })


# ---- 新增 API 端点 ----

@app.route("/api/paper/<int:item_id>/quick-note", methods=["POST"])
def generate_quick_note(item_id):
    """生成精读笔记（问题/方法/结果/要点/AI摘要）并保存到 Obsidian"""
    paper = get_paper(item_id)
    if not paper:
        return jsonify({"success": False, "error": "论文未找到"}), 404

    full_text, pages, source_type = extract_text_from_paper(paper)
    ok, result = generate_structured_note(paper, full_text, source_type)
    if ok:
        return jsonify({"success": True, "filepath": result})
    return jsonify({"success": False, "error": result}), 500


@app.route("/api/paper/<int:item_id>/tags", methods=["GET", "POST"])
def suggest_paper_tags(item_id):
    """获取推荐标签"""
    paper = get_paper(item_id)
    if not paper:
        return jsonify({"error": "未找到"}), 404

    if request.method == "GET":
        tags = suggest_tags(paper)
        return jsonify({"tags": tags})

    # POST: 用户保存自定义标签
    data = request.get_json()
    # 目前标签是跟笔记关联的，这里返回成功供前端使用
    return jsonify({"success": True, "tags": data.get("tags", [])})


@app.route("/api/paper/<int:item_id>/chat", methods=["POST"])
def chat_api(item_id):
    """论文问答聊天"""
    paper = get_paper(item_id)
    if not paper:
        return jsonify({"error": "论文未找到"}), 404

    data = request.get_json()
    selected_text = data.get("selected_text", "")
    question = data.get("question", "")
    history = data.get("history", [])
    blog_content = data.get("blog_content", "")

    # 调用 note_manager.chat_about_paper（不是递归调用自己！）
    answer = chat_about_paper(paper, blog_content, selected_text, question, history)
    return jsonify({"answer": answer})


@app.route("/pdf/<paper_key>")
def serve_pdf(paper_key):
    """直接提供 PDF 文件（用于浏览器 iframe 嵌入）"""
    import glob as _g
    # 在 Zotero storage 中查找对应的 PDF
    storage = "/mnt/c/Users/24974/Zotero/storage"
    pattern = os.path.join(storage, paper_key, "*.pdf")
    matches = _g.glob(pattern)
    if not matches:
        # 尝试模糊匹配
        for d in os.listdir(storage):
            dp = os.path.join(storage, d)
            if os.path.isdir(dp):
                for f in os.listdir(dp):
                    if f.endswith(".pdf"):
                        # 检查这个 PDF 是否属于该 key
                        from zotero_reader import get_paper_by_key
                        p = get_paper_by_key(paper_key)
                        if p:
                            return _send_pdf(p["pdf_path"])
        return "PDF not found", 404
    return _send_pdf(matches[0])


def _send_pdf(path):
    """发送 PDF 文件流"""
    from flask import send_file
    if not path or not os.path.exists(path):
        return "PDF file not found", 404
    return send_file(path, mimetype="application/pdf")


@app.route("/api/paper/<int:item_id>/page-texts", methods=["GET"])
def get_page_texts(item_id):
    """获取 PDF 每页的提取文字"""
    paper = get_paper(item_id)
    if not paper or not paper.get("pdf_path"):
        return jsonify({"texts": {}, "error": "无 PDF"})

    try:
        import fitz
        doc = fitz.open(paper["pdf_path"])
        texts = {}
        for i in range(len(doc)):
            texts[i + 1] = doc[i].get_text("text")
        doc.close()
        return jsonify({"texts": texts})
    except Exception as e:
        return jsonify({"texts": {}, "error": str(e)})


@app.route("/api/paper/<int:item_id>/images", methods=["GET"])
def get_paper_images(item_id):
    """获取论文 PDF 渲染图片"""
    paper = get_paper(item_id)
    if not paper:
        return jsonify({"error": "未找到"}), 404

    pdf_path = paper.get("pdf_path")
    if not pdf_path:
        return jsonify({"images": [], "figures": [], "error": "无 PDF"})

    from pdf_processor import get_figure_context
    result = get_figure_context(pdf_path, paper["key"])
    return jsonify(result)


# ---- 原有 API 端点 ----
def api_papers():
    """JSON API: 论文列表"""
    papers = load_papers()
    query = request.args.get("q", "").strip()
    if query:
        papers = search_papers(query)
    return jsonify(papers[:100])


@app.route("/api/paper/<int:item_id>")
def api_paper(item_id):
    """JSON API: 单篇论文详情"""
    paper = get_paper(item_id)
    if not paper:
        return jsonify({"error": "未找到"}), 404
    return jsonify(paper)


@app.route("/api/notes", methods=["GET", "POST", "DELETE"])
def api_notes():
    """笔记 CRUD API"""
    if request.method == "GET":
        paper_title = request.args.get("paper", "").strip()
        if paper_title:
            notes = find_notes_for_paper(paper_title)
        else:
            notes = list_notes()
        return jsonify(notes)

    elif request.method == "POST":
        data = request.get_json()
        paper_title = data.get("paper_title", "")
        paper_authors = data.get("paper_authors", [])
        note_content = data.get("content", "")
        note_title = data.get("title", "")
        tags = data.get("tags", [])

        filepath, ok, err = create_note(paper_title, paper_authors, note_content, note_title, tags)
        if ok:
            return jsonify({"success": True, "filepath": filepath})
        return jsonify({"success": False, "error": err}), 400

    elif request.method == "DELETE":
        filepath = request.args.get("filepath", "")
        if delete_note(filepath):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "删除失败"}), 400


@app.route("/notes")
def notes_page():
    """笔记管理页"""
    all_notes = list_notes()
    return render_template("notes.html", notes=all_notes)


# ==================== 启动 ====================

if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════╗
║   📚 alphaXiv-Local 论文博客系统        ║
║   仿 alphaXiv.org Blog 功能             ║
║   数据源: Zotero 本地数据库              ║
║   笔记存储在 Obsidian Vault              ║
║   访问: http://{FLASK_HOST}:{FLASK_PORT} ║
╚══════════════════════════════════════════╝
""")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=True)
