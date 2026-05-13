# AGENTS.md

## 新 Session 必读

如果任务涉及下面任一操作，先读 `docs/agent-operations-runbook.md`，再执行：

- 直接执行 Supabase/Postgres SQL、迁移、数据回填或验证。
- GitHub commit / push / 拉取远端。
- 连接 Linux 服务器、部署后端、重启 systemd 服务、检查 journal。
- WSL 中调用 Windows SSH key。

这个仓库在 Windows/WSL 混合环境里运行。不要假设默认 `ssh` 或 `git push`
能自动拿到正确 key；按 runbook 里的 key 复制和 `GIT_SSH_COMMAND` 流程走。

## 操作原则

- 不打印密钥、数据库 URL、token、cookie 或私钥内容。
- 不用 `git add .`。只 stage 本次任务明确相关的文件。
- 远端服务器可能有脏工作区。部署前先 `git status --short`，不要用
  `git reset --hard` 覆盖线上本地改动，除非用户明确要求。
- 数据库迁移优先从本地执行，使用 `.env` 里的 `SUPABASE_DB_URL` 或
  `DATABASE_URL`，不是 Supabase REST key。
- systemd `active` 不等于业务正常。重启后必须看最新 `journalctl`，确认
  启动行、数据库检查或业务日志。

## 文档维护规则

修改代码时必须同步检查文档。

- 如果修改通用操作流程、GitHub/数据库/Linux 部署方法，更新
  `docs/agent-operations-runbook.md`。
- 如果修改 Supabase 迁移或重分析的项目内细节，更新
  `docs/supabase-migration-and-reanalysis.md`。
- 如果修改单个模块的输入、输出、状态、环境变量、命令或失败处理，更新对应
  `docs/*.md`。
- 模块细节以对应 `docs/*.md` 和实际代码为准。
- 不要在文档中保留已经废弃的 JSON 示例、状态名或分类名。
