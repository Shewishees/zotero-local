#!/bin/bash
# alphaXiv-Local 启动脚本
cd "$(dirname "$0")"

echo "🔧 正在激活虚拟环境..."
source .venv/bin/activate

echo ""
echo "📚 启动 alphaXiv-Local 论文博客系统..."
echo ""

# DeepSeek API Key（从 .env 文件或环境变量读取）
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi
if [ -n "$DEEPSEEK_API_KEY" ]; then
    echo "✅ DeepSeek API Key 已配置 (model: deepseek-chat)"
else
    echo "⚠️  未设置 DEEPSEEK_API_KEY，请编辑 .env 文件填入你的 Key"
fi

exec .venv/bin/python app.py
