# A

本项目是一个可自托管的本地内容监控与 AI 分析工具：

- 后端使用 Python，负责小红书 / X 抓取、定时调度、AI 提取与 SQLite 落库
- 前端使用 Next.js，负责本地浏览和控制台配置
- AI 支持两类接入方式：
  - `openai-compatible`：官方 OpenAI 或兼容中转站
  - `anthropic`：Claude / Anthropic

## 目录结构

- `backend/`: Python 后端
- `frontend/`: Next.js 前端
- `data/config/`: 本地配置
- `data/runtime/`: 本地运行态数据，不进入 Git

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt

cd ../frontend
npm install
```

### 2. 初始化本地配置

复制并填写示例文件：

```bash
copy ..\\.env.example ..\\.env
copy ..\\data\\config\\ai_settings.example.json ..\\data\\config\\ai_settings.local.json
copy ..\\data\\config\\watchlist.example.json ..\\data\\config\\watchlist.json
copy ..\\data\\config\\x_watchlist.example.json ..\\data\\config\\x_watchlist.json
copy ..\\data\\config\\runtime_settings.example.json ..\\data\\config\\runtime_settings.json
copy ..\\data\\config\\security_aliases.example.json ..\\data\\config\\security_aliases.json
```

也可以只先配置 `.env`，启动后再去前端控制台填写 AI 设置。  
AI 配置读取优先级：

1. `data/config/ai_settings.local.json`
2. `.env`
3. 代码默认值

### 3. 启动前端

```bash
cd frontend
npm run dev
```

默认地址：`http://localhost:3000`

控制台页面：`/control`

### 4. 常用后端命令

```bash
python backend/src/main.py login --config data/config/watchlist.json
python backend/src/main.py run-once --config data/config/watchlist.json
python backend/src/main.py run-once-x --config data/config/x_watchlist.json
python backend/src/main.py run-scheduler --config data/config/watchlist.json
```

## AI 配置

支持两种 provider：

- `openai-compatible`
  - 需要：`api_key`、`base_url`、`model`
  - 适用于官方 OpenAI 或兼容 OpenAI API 的中转站
- `anthropic`
  - 需要：`api_key`、`model`

AI 设置页位于前端控制台中。  
API key 只会保存到服务端本地配置文件，不会通过 `NEXT_PUBLIC_*` 暴露到浏览器，也不会在读取接口里明文返回。

## 运行说明

- 小红书登录态存放在 `data/runtime/state/xhs_chrome_user_data/`，每个使用者都需要自己生成
- SQLite 默认位于 `data/runtime/insight.db`
- 调度时区固定为 `Asia/Shanghai`
- `TWELVE_DATA_API_KEY`、代理、`PYTHON_EXECUTABLE`、`INSIGHT_DB_PATH` 都是可选项

## 发布说明

这个仓库按公开发布版本整理：

- 不包含真实密钥
- 不包含运行态数据
- 不包含浏览器登录态
- 不包含 `Reference/` 和本地参考材料

发布到 GitHub 前，请先轮换任何已经出现在旧历史或本地 `.env` 里的真实密钥。
