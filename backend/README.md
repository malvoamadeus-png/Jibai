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
```

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
```
