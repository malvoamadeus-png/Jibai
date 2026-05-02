<p align="center">
  <img src="Logo.png" alt="Jibai Logo" width="180">
</p>

<h1 align="center">集百</h1>

<p align="center">
  一个本地运行的股票内容抓取、AI 分析与观点时间线整理工具。
</p>

## 简介

集百用于本地抓取小红书和 X 账号内容，完成去重、AI 提取、结构化分析，并把结果写入本地 SQLite，最后在前端按作者、股票和主题查看观点变化。

核心链路是：

`抓取 -> 去重 -> AI 分析 -> SQLite 落盘 -> 前端浏览`

## 核心能力

- 抓取小红书账号内容，并保留本地登录态
- 抓取 X 账号内容，支持按账号设置抓取条数
- 对抓取内容做去重、AI 提取、结构化分析和时间线整理
- 将原始内容、分析结果和聚合视图写入本地 SQLite
- 通过 `/control` 页面统一管理抓取配置、调度时间、AI 配置和手动运行

## 安装

以下示例以 Windows PowerShell 为例。

### 1. 安装依赖

推荐使用项目安装脚本：

```powershell
.\install.ps1
```

脚本会依次安装后端 Python 依赖、Playwright Chromium 和前端 Node 依赖。X 抓取强依赖 Playwright Chromium，不会回退使用本机 Chrome。

如需手动安装，必须执行完整三步：

```powershell
pip install -r backend/requirements.txt
python -m playwright install chromium

npm install --prefix frontend
```

注意：`pip install -r backend/requirements.txt` 只会安装 Python 包，不会安装 Playwright Chromium。

### 2. 初始化本地配置

```bash
copy .env.example .env
copy data\config\ai_settings.example.json data\config\ai_settings.local.json
copy data\config\watchlist.example.json data\config\watchlist.json
copy data\config\x_watchlist.example.json data\config\x_watchlist.json
copy data\config\runtime_settings.example.json data\config\runtime_settings.json
copy data\config\security_aliases.example.json data\config\security_aliases.json
```

### 3. 启动前端

```bash
cd frontend
npm run dev
```

默认访问地址：`http://localhost:3000`

控制台页面：`http://localhost:3000/control`

## 常用命令

```bash
python backend/src/main.py login --config data/config/watchlist.json
python backend/src/main.py run-once --config data/config/watchlist.json
python backend/src/main.py run-once-x --config data/config/x_watchlist.json
python backend/src/main.py run-scheduler --config data/config/watchlist.json
```

## 配置说明

项目的主要配置都放在 `data/config/` 下：

- `ai_settings.local.json`：AI provider、model、base URL、API key 等本地 AI 配置
- `watchlist.json`：小红书账号配置
- `x_watchlist.json`：X 账号配置
- `runtime_settings.json`：调度时间配置
- `security_aliases.json`：股票别名与归一化映射

### `.env` 和 `ai_settings.local.json` 的关系

这个项目里，根目录 `.env` 不是 AI 配置的主存储位置。

- `.env` 里的 `AI_*`、`OPENAI_*`、`GPT_*` 变量只是后端读取配置时的兜底来源
- `/control` 页面里保存的 AI 配置会写入 `data/config/ai_settings.local.json`
- 运行时会优先读取 `data/config/ai_settings.local.json`，只有本地 JSON 没填时才会回退到 `.env`

这意味着：

- 你在 `/control` 页面里改了 AI key 或 base URL 后，根目录 `.env` 不一定会变化
- 实际是否生效，应优先查看 `data/config/ai_settings.local.json`

### API key 保存语义

`/control` 页面中的 API key 输入框遵循以下规则：

- 输入新的 key 并保存：覆盖当前 key
- 留空直接保存：保留当前 key
- 保存成功后，输入框会清空，页面不会回显已保存的 key 内容

## 运行结果保存位置

- 小红书登录态：`data/runtime/state/xhs_chrome_user_data/`
- SQLite 数据库：`data/runtime/insight.db`
- AI snapshot：`data/runtime/ai/snapshots/`
- 运行状态文件：`data/runtime/state/`

## 如何在新电脑上本地核验“这次运行是否真的成功”

如果你在 `/control` 里点了手动运行，想确认这次是否真的完成了抓取和 AI 分析，建议至少看下面三项：

### 1. 看控制台页面里的手动运行记录

重点看：

- 开始时间和结束时间
- 每个命令的耗时
- 是否有命令输出异常

如果整次运行只有几秒，而且你配置了多个账号，通常需要进一步核验，不要只看“成功”字样。

### 2. 看 snapshot 是否产生了新文件

运行前后对比这个目录：

`data/runtime/ai/snapshots/`

如果这次真的跑到了 AI 分析阶段，通常会生成一个新的 snapshot 文件，文件名类似：

`20260501T220850+0800.json`

### 3. 看 SQLite 是否有新的落盘结果

至少确认这些内容有新的更新时间：

- `data/runtime/insight.db`
- `data/runtime/insight.db-wal`

如果你本机装了 SQLite，也可以直接查最近分析记录：

```bash
sqlite3 data/runtime/insight.db "SELECT run_id, run_at, processed_note_count, error_count FROM analysis_runs ORDER BY run_at DESC, id DESC LIMIT 5;"
```

以及最近抓取记录：

```bash
sqlite3 data/runtime/insight.db "SELECT platform, account_name, run_at, status, candidate_count, new_note_count FROM crawl_account_runs ORDER BY run_at DESC, id DESC LIMIT 10;"
```

如果没有新的 `analysis_runs` 记录，也没有新的 snapshot 文件，那么这次“手动运行成功”大概率只是进程正常退出，不代表真的完成了新的抓取和分析。

## 注意事项

> [!CAUTION]
> 小红书抓取强依赖登录态，并且存在较高风控风险。务必使用小号，不要使用主号。

- 项目完全本地运行，不托管你的数据和登录态
- X 抓取强依赖 Playwright Chromium；如果只安装 Python requirements 而没有运行 `python -m playwright install chromium`，X 抓取会失败
- 小红书登录态、SQLite 数据库、运行态目录都不应提交到 Git
- 平台抓取可能因为页面结构变化、平台限制或风控而失败
- AI key 属于本地敏感信息，建议只保存在本机配置文件中

## 目录结构

- `backend/`：Python 后端，负责抓取、AI 分析、SQLite 落盘和调度
- `frontend/`：Next.js 前端，负责本地浏览和控制台配置
- `data/config/`：本地配置文件
- `data/runtime/`：本地运行态数据

## License

本项目使用仓库内的 [LICENSE](LICENSE)。
