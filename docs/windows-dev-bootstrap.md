# Windows Dev Bootstrap

这份文档解决两类新电脑常见问题：

- PowerShell 执行策略会拦 `npm.ps1`
- 系统 Python 经常缺依赖，或者版本不适合当前项目

目标是把本地开发入口统一到仓库自带脚本，不再直接依赖系统
`python`、`pip` 或 PowerShell 里默认解析到的 `npm.ps1`。

## 一次性初始化

在仓库根目录运行：

```cmd
install.cmd
```

它会做这些事：

- 自动寻找受支持的 Python `3.11`、`3.12` 或 `3.13`
- 在仓库根目录创建固定虚拟环境 `.venv`
- 把后端依赖和 `pytest` 装进 `.venv`
- 安装 Playwright Chromium
- 用 `npm.cmd` 安装 `public-web`，以及存在时安装 `frontend`

如果你更习惯 PowerShell，也可以直接运行：

```powershell
.\install.cmd
```

这里仍然走 `install.cmd`，因为它会用 `-ExecutionPolicy Bypass` 调用
`install.ps1`，避免本机策略影响安装入口。

## 以后日常怎么用

不要再直接依赖系统 `python`、`pip`、`pytest` 或 PowerShell 里的
`npm`。统一走仓库根目录的 `dev.cmd`：

```cmd
dev.cmd check
dev.cmd public-web run dev
dev.cmd public-web run lint
dev.cmd public-web run build
dev.cmd pytest tests\test_crypto_pipeline.py -q
dev.cmd backend public-worker-doctor
```

常用映射：

- `dev.cmd python ...` 等价于 `.venv\Scripts\python.exe ...`
- `dev.cmd pip ...` 等价于 `.venv\Scripts\python.exe -m pip ...`
- `dev.cmd pytest ...` 等价于 `.venv\Scripts\python.exe -m pytest ...`
- `dev.cmd public-web ...` 会进入 `public-web/` 后调用 `npm.cmd ...`
- `dev.cmd backend ...` 会带上 `PYTHONPATH=backend` 调用 `backend/src/main.py`

## 环境要求

- Windows 上安装 Node.js，并确保 `npm.cmd` 可用
- Windows 上安装 Python `3.11`、`3.12` 或 `3.13`

当前仓库不建议直接用 Python `3.14` 作为主开发解释器，因为部分依赖在新
版本上的兼容性不稳定，容易导致每次新环境都要单独兜底。

## 自检

初始化后运行：

```cmd
dev.cmd check
```

它会检查：

- `.venv` 里的 Python 是否存在
- `node` 和 `npm.cmd` 是否可用
- 根目录 `.env` 是否存在
- `public-web/.env.local` 是否存在

## 前端本地环境

`public-web` 仍然需要自己的环境文件。首次本地启动前：

```cmd
copy public-web\.env.example public-web\.env.local
```

然后补齐里面的：

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

## 后端本地环境

根目录 `.env` 仍然是后端和本地 SQL / reanalysis 命令的入口。首次初始化：

```cmd
copy .env.example .env
```

再按实际环境补上需要的密钥和 DSN。
