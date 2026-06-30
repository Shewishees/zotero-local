"""PDF 文本/图片提取模块 — 使用 PyMuPDF"""

import os
import fitz
from config import BLOG_MAX_PDF_CHARS, CACHE_DIR

IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images")
os.makedirs(IMAGES_DIR, exist_ok=True)


def extract_text(pdf_path):
    """提取 PDF 纯文本，返回 (text, page_count, success, error_msg)"""
    if not pdf_path:
        return ("", 0, False, "PDF 路径为空")

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return ("", 0, False, f"无法打开 PDF: {e}")

    page_count = len(doc)
    parts = []

    for i in range(page_count):
        try:
            text = doc[i].get_text("text")
            if text.strip():
                parts.append(f"[第{i+1}页]\n{text}")
        except Exception:
            continue
    doc.close()

    full_text = "\n\n".join(parts)
    if not full_text.strip():
        return ("", page_count, False, "PDF 无可提取文本")

    if len(full_text) > BLOG_MAX_PDF_CHARS:
        full_text = full_text[:BLOG_MAX_PDF_CHARS] + "\n\n[... 截断 ...]"

    return (full_text, page_count, True, "")


def extract_page_images(pdf_path, paper_key, max_pages=12, dpi=150):
    """
    将 PDF 页面渲染为图片并保存。

    返回: list of dicts [{page, path, filename}, ...]
    """
    if not pdf_path or not os.path.exists(pdf_path):
        return []

    img_dir = os.path.join(IMAGES_DIR, paper_key)
    os.makedirs(img_dir, exist_ok=True)

    images = []
    try:
        doc = fitz.open(pdf_path)
        limit = min(len(doc), max_pages)

        for i in range(limit):
            page = doc[i]
            # 只渲染包含图片的页面（检测页面上是否有嵌入图）
            has_image = len(page.get_images()) > 0

            pix = page.get_pixmap(dpi=dpi)
            filename = f"page_{i+1}.png"
            filepath = os.path.join(img_dir, filename)
            pix.save(filepath)

            images.append({
                "page": i + 1,
                "path": f"/static/images/{paper_key}/{filename}",
                "has_figure": has_image,
                "size": os.path.getsize(filepath),
            })
        doc.close()
    except Exception:
        pass

    return images


def extract_figures(pdf_path, paper_key, dpi=200):
    """
    提取 PDF 中的嵌入图片，保存为独立文件。

    返回: list of image paths
    """
    if not pdf_path or not os.path.exists(pdf_path):
        return []

    img_dir = os.path.join(IMAGES_DIR, paper_key, "figures")
    os.makedirs(img_dir, exist_ok=True)

    figures = []
    try:
        doc = fitz.open(pdf_path)

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            image_list = page.get_images(full=True)

            for img_idx, img_info in enumerate(image_list):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    ext = base_image["ext"]
                    img_bytes = base_image["image"]

                    filename = f"fig_p{page_idx+1}_{img_idx+1}.{ext}"
                    filepath = os.path.join(img_dir, filename)

                    with open(filepath, "wb") as f:
                        f.write(img_bytes)

                    w, h = base_image.get("width", 0), base_image.get("height", 0)
                    if w * h >= 20000:  # 过滤太小的图片（图标等）
                        figures.append({
                            "page": page_idx + 1,
                            "path": f"/static/images/{paper_key}/figures/{filename}",
                            "width": w,
                            "height": h,
                        })
                except Exception:
                    continue
        doc.close()
    except Exception:
        pass

    return figures


def extract_text_from_paper(paper):
    """从论文对象提取文本，优先 PDF 后降级为摘要"""
    pdf_path = paper.get("pdf_path")
    if pdf_path:
        text, pages, ok, err = extract_text(pdf_path)
        if ok:
            return text, pages, "pdf"
    abstract = paper.get("abstract", "")
    return (abstract if abstract.strip() else ""), 0, "abstract" if abstract.strip() else "none"


def get_figure_context(pdf_path, paper_key):
    """
    获取图片上下文——返回页面图片列表（用于博客中展示）。
    同时提取嵌入的高清图片。
    """
    page_imgs = extract_page_images(pdf_path, paper_key, max_pages=15, dpi=120)
    figures = extract_figures(pdf_path, paper_key, dpi=200)
    return {"pages": page_imgs, "figures": figures}
