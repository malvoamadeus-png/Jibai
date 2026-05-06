# Codex Linux Access

本文档说明新的 Codex session 如何连接生产 Linux 服务器读取日志、执行诊断命令和排查 Jibai 服务。

## 连接方式

生产服务器：

- Host: `47.76.243.147`
- User: `root`
- Key: `C:\Users\Windows\.ssh\id_ed25519`
- Repo path: `/opt/Jibai`

不要把私钥内容、数据库 URL、Supabase key 或其他密钥写进对话、文档、commit 或日志输出。

## 推荐配置：Codex MCP

在 Windows 本机执行一次：

```powershell
codex mcp add ssh-prod -- npx -y ssh-mcp -- --host=47.76.243.147 --user=root --key=C:\Users\Windows\.ssh\id_ed25519
```

这会把 MCP server 写入当前 Windows 用户的全局 Codex 配置：

```text
C:\Users\Windows\.codex\config.toml
```

同一台电脑、同一个 Windows 用户下，新开的 Codex session 通常会自动看到 `ssh-prod`。已经打开的旧 session 可能不会热加载，需要重启 Codex 或新开 session。

之后可以直接要求 Codex：

```text
用 ssh-prod 连接服务器，查看 /opt/Jibai 的 public-worker 状态。
```

## 可选配置：SSH Alias

也可以在 `C:\Users\Windows\.ssh\config` 中配置别名：

```sshconfig
Host jibai-prod
  HostName 47.76.243.147
  User root
  IdentityFile C:\Users\Windows\.ssh\id_ed25519
```

然后 MCP 可以改成：

```powershell
codex mcp add ssh-prod -- npx -y ssh-mcp -- --host=jibai-prod
```

以后换 IP 或 key 时，只需要改 SSH config。

## MCP 不可用时的直接 SSH

如果当前 Codex session 没加载到 MCP，可以直接用本机 SSH：

```powershell
ssh -i C:\Users\Windows\.ssh\id_ed25519 -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new root@47.76.243.147 "cd /opt/Jibai && pwd && git status --short"
```

多行诊断脚本建议通过 stdin 传入，避免复杂转义：

```powershell
$script = @'
cd /opt/Jibai
systemctl status jibai-public-worker --no-pager -l
journalctl -u jibai-public-worker -n 120 --no-pager
'@

$script | ssh -i C:\Users\Windows\.ssh\id_ed25519 -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new root@47.76.243.147 "bash -s"
```

## Jibai 常用命令

服务状态：

```bash
systemctl status jibai-public-worker --no-pager -l
```

Worker 日志：

```bash
journalctl -u jibai-public-worker -n 200 --no-pager
```

Worker 诊断：

```bash
cd /opt/Jibai
set -a
. /etc/jibai/public-worker.env
set +a
.venv/bin/python backend/src/main.py public-worker-doctor
```

重启 worker：

```bash
systemctl restart jibai-public-worker
```

## 注意事项

- 读取环境变量时只输出变量名，不输出变量值。
- 查询数据库时优先写只读 SQL；需要执行迁移时先说明目的和影响范围。
- 临时文件放在 `/tmp`，执行完删除。
- 不要在服务器上执行 `git reset --hard` 或覆盖用户改动，除非用户明确要求。
