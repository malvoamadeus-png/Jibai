# Data

本目录只保存本地配置和本地运行态。

## config

- `ai_settings.local.json`: 本地 AI 配置，不进入 Git
- `ai_settings.example.json`: AI 配置示例
- `watchlist.json`: 小红书账号配置，不进入 Git
- `watchlist.example.json`: 小红书账号配置示例
- `x_watchlist.json`: X 账号配置，不进入 Git
- `x_watchlist.example.json`: X 账号配置示例
- `runtime_settings.json`: 调度时间配置，不进入 Git
- `runtime_settings.example.json`: 调度时间示例
- `security_aliases.json`: 股票别名映射，不进入 Git
- `security_aliases.example.json`: 股票别名映射示例

## runtime

`runtime/` 下的内容全部是本机生成的运行态：

- `insight.db`: SQLite 数据库
- `state/`: 登录态和状态文件
- `x/`: X 抓取调试数据
- `xhs/`: 小红书原始抓取数据
- `ai/`: AI 快照与物化产物
