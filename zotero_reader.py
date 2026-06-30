"""Zotero 数据库读取模块 — 只读连接 zotero.sqlite，提取论文元数据"""

import sqlite3
import os
import re
from config import ZOTERO_DB, ZOTERO_STORAGE

# Zotero fields 表中关键 fieldID → 含义映射
FIELD_MAP = {
    1: "title",
    2: "abstractNote",
    6: "date",
    8: "DOI",
    10: "url",
    14: "shortTitle",
    22: "volume",
    35: "pages",
    41: "publicationTitle",
    67: "issue",
    85: "journalAbbreviation",
}


def _connect():
    """创建只读数据库连接"""
    return sqlite3.connect(f"file:{ZOTERO_DB}?mode=ro", uri=True)


def get_all_papers(item_types=None, limit=None, offset=0):
    """
    获取所有论文（默认：期刊文章 + 会议论文 + 预印本）
    返回列表，每项含标题、作者、摘要、日期、期刊、DOI、PDF 路径、Zotero key
    """
    if item_types is None:
        item_types = ["journalArticle", "conferencePaper", "preprint"]

    conn = _connect()
    conn.row_factory = sqlite3.Row

    placeholders = ",".join("?" for _ in item_types)
    query = f"""
        SELECT i.itemID, i.key, it.typeName,
               (SELECT idv.value FROM itemData id
                JOIN itemDataValues idv ON id.valueID = idv.valueID
                WHERE id.itemID = i.itemID AND id.fieldID = 1) AS title,
               (SELECT idv.value FROM itemData id
                JOIN itemDataValues idv ON id.valueID = idv.valueID
                WHERE id.itemID = i.itemID AND id.fieldID = 2) AS abstractNote,
               (SELECT idv.value FROM itemData id
                JOIN itemDataValues idv ON id.valueID = idv.valueID
                WHERE id.itemID = i.itemID AND id.fieldID = 6) AS date,
               (SELECT idv.value FROM itemData id
                JOIN itemDataValues idv ON id.valueID = idv.valueID
                WHERE id.itemID = i.itemID AND id.fieldID = 8) AS DOI,
               (SELECT idv.value FROM itemData id
                JOIN itemDataValues idv ON id.valueID = idv.valueID
                WHERE id.itemID = i.itemID AND id.fieldID = 41) AS publicationTitle,
               (SELECT idv.value FROM itemData id
                JOIN itemDataValues idv ON id.valueID = idv.valueID
                WHERE id.itemID = i.itemID AND id.fieldID = 22) AS volume,
               (SELECT idv.value FROM itemData id
                JOIN itemDataValues idv ON id.valueID = idv.valueID
                WHERE id.itemID = i.itemID AND id.fieldID = 35) AS pages,
               (SELECT idv.value FROM itemData id
                JOIN itemDataValues idv ON id.valueID = idv.valueID
                WHERE id.itemID = i.itemID AND id.fieldID = 67) AS issue,
               (SELECT idv.value FROM itemData id
                JOIN itemDataValues idv ON id.valueID = idv.valueID
                WHERE id.itemID = i.itemID AND id.fieldID = 10) AS url,
               (SELECT idv.value FROM itemData id
                JOIN itemDataValues idv ON id.valueID = idv.valueID
                WHERE id.itemID = i.itemID AND id.fieldID = 14) AS shortTitle
        FROM items i
        JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
        WHERE it.typeName IN ({placeholders})
          AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
        ORDER BY date DESC
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(query, [*item_types, limit or -1, offset]).fetchall()

    papers = []
    for row in rows:
        papers.append({
            "item_id": row["itemID"],
            "key": row["key"],
            "type": row["typeName"],
            "title": row["title"] or "未命名论文",
            "abstract": row["abstractNote"] or "",
            "date": row["date"] or "",
            "DOI": row["DOI"] or "",
            "publication": row["publicationTitle"] or "",
            "volume": row["volume"] or "",
            "issue": row["issue"] or "",
            "pages": row["pages"] or "",
            "url": row["url"] or "",
            "shortTitle": row["shortTitle"] or "",
            "authors": _get_authors(conn, row["itemID"]),
            "pdf_path": _get_pdf_path(conn, row["key"]),
            "notes": _get_notes_brief(conn, row["itemID"]),
        })

    conn.close()
    return papers


def get_paper(item_id):
    """获取单篇论文完整信息"""
    papers = get_all_papers(limit=1000)
    for p in papers:
        if p["item_id"] == item_id:
            return p
    return None


def get_paper_by_key(key):
    """通过 Zotero key 获取论文"""
    papers = get_all_papers(limit=1000)
    for p in papers:
        if p["key"] == key:
            return p
    return None


def search_papers(query_str):
    """按标题搜索论文"""
    papers = get_all_papers(limit=1000)
    q = query_str.lower()
    return [p for p in papers if q in p["title"].lower() or q in (p["abstract"] or "").lower() or any(q in a.lower() for a in p["authors"])]


def get_collections():
    """获取所有 Zotero 分类"""
    conn = _connect()
    rows = conn.execute("SELECT collectionID, collectionName FROM collections ORDER BY collectionName").fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1]} for r in rows]


def get_papers_by_collection(collection_id):
    """按分类获取论文"""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT i.itemID FROM items i
        JOIN collectionItems ci ON i.itemID = ci.itemID
        WHERE ci.collectionID = ? AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
    """, [collection_id]).fetchall()
    item_ids = [r["itemID"] for r in rows]
    conn.close()

    all_papers = get_all_papers(limit=1000)
    return [p for p in all_papers if p["item_id"] in item_ids]


# ---- 内部辅助函数 ----

def _get_authors(conn, item_id):
    """获取某论文的作者列表"""
    rows = conn.execute("""
        SELECT c.firstName, c.lastName, ct.creatorType
        FROM itemCreators ic
        JOIN creators c ON ic.creatorID = c.creatorID
        LEFT JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
        WHERE ic.itemID = ?
        ORDER BY ic.orderIndex
    """, [item_id]).fetchall()
    if not rows:
        return ["未知作者"]
    authors = []
    for r in rows:
        first = (r[0] or "").strip()
        last = (r[1] or "").strip()
        if first and last:
            authors.append(f"{last}, {first}")
        elif last:
            authors.append(last)
        elif first:
            authors.append(first)
    return authors if authors else ["未知作者"]


def _get_pdf_path(conn, item_key):
    """获取某论文的 PDF 文件绝对路径"""
    rows = conn.execute("""
        SELECT ia.path, i.key
        FROM itemAttachments ia
        JOIN items i ON ia.itemID = i.itemID
        WHERE ia.parentItemID = (SELECT itemID FROM items WHERE key = ?)
          AND ia.path LIKE '%.pdf'
        LIMIT 1
    """, [item_key]).fetchall()

    if not rows:
        # 备用：直接搜 attachment 的 key
        rows = conn.execute("""
            SELECT ia.path, i.key
            FROM itemAttachments ia
            JOIN items i ON ia.itemID = i.itemID
            JOIN items pi ON ia.parentItemID = pi.itemID
            WHERE pi.key = ? AND ia.path LIKE '%storage:%'
            LIMIT 1
        """, [item_key]).fetchall()

    if not rows:
        return None

    path_field = rows[0][0]
    attach_key = rows[0][1]

    # 路径格式: storage:filename.pdf
    filename = path_field.replace("storage:", "")
    pdf_path = os.path.join(ZOTERO_STORAGE, attach_key, filename)

    if os.path.exists(pdf_path):
        return pdf_path
    return None


def _get_notes_brief(conn, item_id):
    """获取某论文的笔记（仅返回前 200 字符的纯文本预览）"""
    rows = conn.execute("""
        SELECT i.itemID, n.note
        FROM itemNotes n
        JOIN items i ON n.itemID = i.itemID
        WHERE n.parentItemID = ?
    """, [item_id]).fetchall()

    notes = []
    for r in rows:
        note_html = r[1] or ""
        # 去除 HTML 标签
        text = re.sub(r"<[^>]+>", "", note_html).strip()
        notes.append({"id": r[0], "preview": text[:200]})
    return notes


def get_full_notes(item_id):
    """获取某论文的所有笔记完整内容（纯文本）"""
    conn = _connect()
    rows = conn.execute("""
        SELECT i.itemID, n.note, n.title
        FROM itemNotes n
        JOIN items i ON n.itemID = i.itemID
        WHERE n.parentItemID = ?
    """, [item_id]).fetchall()

    notes = []
    for r in rows:
        note_html = r[1] or ""
        text = re.sub(r"<[^>]+>", "", note_html).strip()
        notes.append({"id": r[0], "title": r[2] or "", "content": text})
    conn.close()
    return notes
