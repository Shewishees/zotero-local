"""配置文件 — 集中管理所有路径和参数"""

import os

# ---- 加载 .env 文件 ----
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                if _key.strip() not in os.environ:
                    os.environ[_key.strip()] = _val.strip().strip('"').strip("'")

# ---- 路径配置 ----
ZOTERO_DB = "/mnt/c/Users/24974/Zotero/zotero.sqlite"
ZOTERO_STORAGE = "/mnt/c/Users/24974/Zotero/storage"
OBSIDIAN_VAULT = "/mnt/c/Users/24974/Documents/Obsidian Vault/文献"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

# ---- DeepSeek API ----
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-chat"       # 或 deepseek-reasoner
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# ---- Blog 生成 ----
BLOG_MAX_PDF_CHARS = 30000   # 送入 API 的最大 PDF 字符数
BLOG_TEMPERATURE = 0.7
BLOG_MAX_TOKENS = 16000

# ---- Flask ----
FLASK_HOST = "0.0.0.0"   # 绑定所有接口，WSL2 中 Windows 才能通过 localhost 访问
FLASK_PORT = 5000
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "alphaxiv-local-dev-key")

# ---- 确保目录存在 ----
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OBSIDIAN_VAULT, exist_ok=True)
