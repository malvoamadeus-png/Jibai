<p align="center">
  <img src="Logo.png" alt="集百 Logo" width="180">
</p>

<h1 align="center">集百</h1>

<p align="center">
  <strong>集百家之长，一把抓住，顷刻炼化。</strong>
</p>

<p align="center">
  一个本地运行的、<b>针对股票</b>的内容抓取、AI 分析与观点时间线整理工具。
</p>

集百是一个面向个人研究与归档场景的本地工具：抓取小红书和 X 的账号内容，完成去重、AI 提取与结构化分析，落库到本地 SQLite，再在前端按作者、股票和 Theme 回看观点变化。它强调本地、自托管、可控，配置、运行和数据都掌握在你自己的机器上。

## 核心能力

- 抓取小红书账号内容，并保留本地登录态完成后续运行
- 抓取 X 账号内容，支持按账号配置抓取条数
- 对抓取内容做去重、AI 提取、观点结构化与时间线物化
- 将原始内容、分析结果和聚合视图写入本地 SQLite
- 在前端按作者、股票、Theme 浏览观点时间线和日度变化
- 通过 `/control` 页面统一管理抓取配置、调度时间、AI 设置与手动运行

## 工作流

项目的实际链路是：

**抓取 -> 去重 -> AI 分析 -> SQLite 落库 -> 前端浏览**

使用时通常是先配置抓取账号和 AI，再运行抓取任务，最后在作者、股票或 Theme 页面查看结果。

## 快速开始

下面的复制命令以 Windows PowerShell 为例；如果你在 macOS 或 Linux 上运行，请将 `copy` 替换为 `cp`。

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt

cd ../frontend
npm install
```

### 2. 初始化本地配置

复制示例配置文件：

```bash
copy .env.example .env
copy data\config\ai_settings.example.json data\config\ai_settings.local.json
copy data\config\watchlist.example.json data\config\watchlist.json
copy data\config\x_watchlist.example.json data\config\x_watchlist.json
copy data\config\runtime_settings.example.json data\config\runtime_settings.json
copy data\config\security_aliases.example.json data\config\security_aliases.json
```

如果你暂时不想直接改 JSON，也可以先只准备 `.env`，再到前端控制台里补充 AI 配置。

### 3. 启动前端

```bash
cd frontend
npm run dev
```

默认访问地址：`http://localhost:3000`

控制台页面：`/control`

### 4. 常用后端命令

```bash
python backend/src/main.py login --config data/config/watchlist.json
python backend/src/main.py run-once --config data/config/watchlist.json
python backend/src/main.py run-once-x --config data/config/x_watchlist.json
python backend/src/main.py run-scheduler --config data/config/watchlist.json
```

## 配置说明

项目的主要配置都放在 `data/config/` 下：

- `ai_settings.local.json`：AI provider、model、Base URL、API key 等本地 AI 配置
- `watchlist.json`：小红书账号配置
- `x_watchlist.json`：X 账号配置
- `runtime_settings.json`：调度时间配置
- `security_aliases.json`：股票别名与归一化映射

这些配置都提供了对应的示例文件，便于初始化和按需调整。

## 重要限制与注意事项

> [!CAUTION]
> **小红书必须使用账号登录。**
> **极高概率在使用一段时间后收到警告、风控，甚至封号。**
> **必须使用小号，不要使用主号。**

- 项目依赖本地运行环境，不是云服务，也不会替你托管数据或登录态
- 小红书登录态、SQLite 数据库、运行态目录都不应上传到 GitHub
- 平台抓取可能因为页面结构变化、平台限制或风控策略而失效
- AI 配置属于本地敏感信息，建议仅保存在本机配置文件中

## 目录结构与运行说明

### 目录结构

- `backend/`：Python 后端，负责抓取、AI 分析、SQLite 落库和调度
- `frontend/`：Next.js 前端，负责本地浏览和控制台配置
- `data/config/`：本地配置文件
- `data/runtime/`：本地运行态数据，不进入 Git

### 运行说明

- 小红书登录态默认存放在 `data/runtime/state/xhs_chrome_user_data/`
- SQLite 数据库默认位于 `data/runtime/insight.db`
- 调度时区固定为 `Asia/Shanghai`
- `TWELVE_DATA_API_KEY`、`PYTHON_EXECUTABLE`、`INSIGHT_DB_PATH` 都是可选环境项

## 许可证

本项目使用仓库内的 [LICENSE](LICENSE) 作为许可证说明。上传到 GitHub 前，请确认已经移除真实密钥、本地运行数据和浏览器登录态。
