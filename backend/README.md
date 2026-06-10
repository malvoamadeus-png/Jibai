# Backend

Python 后端负责：

- 小红书账号抓取
- X 账号抓取
- AI 提取与时间线物化
- SQLite 落库
- 定时调度

## 依赖

```bash
cd backend
pip install -r requirements.txt
python -m playwright install chromium
```

`pip install -r requirements.txt` 只安装 Python 包，不会安装 Playwright Chromium。X 抓取强依赖 Playwright Chromium，不会回退使用本机 Chrome。

crypto asset brief 的 X 搜索运行时也已经内化在 backend 主线中，直接依赖
`backend/packages/public_app/x_search.py`。它不允许再从 `Reference/` 目录加载脚本，所以部署或新环境初始化时同样必须安装 Chromium。

## AI

AI 层通过 `LiteLLM SDK` 统一调用：

- `openai-compatible`
- `anthropic`

配置优先级：

1. `data/config/ai_settings.local.json`
2. 根目录 `.env`
3. 代码默认值

## 常用命令

```bash
python src/main.py login --config ../data/config/watchlist.json
python src/main.py run-once --config ../data/config/watchlist.json
python src/main.py run-once-x --config ../data/config/x_watchlist.json
python src/main.py run-scheduler --config ../data/config/watchlist.json
python src/main.py export-daily-author-viewpoints --date 2026-06-08
python src/main.py public-api --host 127.0.0.1 --port 8010
```
