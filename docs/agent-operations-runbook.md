# Agent Operations Runbook

这是一份项目无关的操作手册，给新的 Codex/AI session 使用。它覆盖三类常用操作：

- 直接执行数据库 SQL。
- 推送 GitHub。
- 连接 Linux 并部署后端。

命令里的路径按当前机器约定写；换项目时只需要替换仓库路径、远端地址、服务器路径和服务名。

## 0. 基本规则

- 不打印 `.env`、数据库 URL、API key、token、cookie、私钥内容。
- 只打印变量是否存在，例如 `SUPABASE_DB_URL=set`。
- 不用 `git add .`，只 stage 本次任务明确相关的文件。
- 不在脏工作区里执行 `git reset --hard` 或大范围 checkout，除非用户明确要求。
- 服务器上 `systemctl active` 不等于业务健康；必须看最新 journal。

## 1. WSL 使用 Windows SSH Key

Windows 盘挂载到 WSL 后，私钥文件经常显示为 `0777`，OpenSSH 会拒绝使用：

```text
WARNING: UNPROTECTED PRIVATE KEY FILE
bad permissions
```

处理方式是复制到 WSL 用户自己的 `~/.ssh` 并设置权限。

### GitHub key

```bash
mkdir -p ~/.ssh
cp /mnt/c/Users/Windows/.ssh/id_rsa_A ~/.ssh/id_rsa_A_github
chmod 600 ~/.ssh/id_rsa_A_github

ssh -i ~/.ssh/id_rsa_A_github \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=accept-new \
  -T git@github.com
```

成功时 GitHub 会返回类似：

```text
Hi <github-user>! You've successfully authenticated, but GitHub does not provide shell access.
```

### Linux server key

```bash
mkdir -p ~/.ssh
cp /mnt/c/Users/Windows/.ssh/id_ed25519 ~/.ssh/id_ed25519_prod
chmod 600 ~/.ssh/id_ed25519_prod

ssh -i ~/.ssh/id_ed25519_prod \
  -o BatchMode=yes \
  -o ConnectTimeout=10 \
  -o StrictHostKeyChecking=accept-new \
  root@47.76.243.147 "hostname && uptime"
```

## 2. GitHub Push

先确认本地状态，不要把无关文件混进去。

```bash
git status --short
git branch --show-current
git remote -v
```

只 stage 本次任务相关文件：

```bash
git add path/to/file1 path/to/file2
git status --short
```

提交：

```bash
git commit -m "Short imperative message"
```

从 WSL 推送 GitHub 时，显式指定 key：

```bash
GIT_SSH_COMMAND='ssh -i ~/.ssh/id_rsa_A_github -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new' \
  git push origin main
```

如果仍失败：

- 先跑上面的 `ssh -T git@github.com` 验证 key。
- 不要改 remote URL，除非确认当前 remote 错了。
- 不要把私钥内容贴到聊天或文档里。

## 3. 直接执行 Supabase/Postgres SQL

优先本地执行。需要 `.env` 中存在 `SUPABASE_DB_URL` 或 `DATABASE_URL`。

### Secret-safe preflight

```bash
python3 - <<'PY'
from pathlib import Path

env_path = Path(".env")
keys = {}
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        keys[key.strip()] = bool(value.strip().strip("'\""))

for key in ["SUPABASE_DB_URL", "DATABASE_URL"]:
    print(f"{key}=" + ("set" if keys.get(key) else "missing"))
PY
```

### Apply a SQL file

当前机器推荐用 Windows Anaconda Python：

```bash
/mnt/d/Software/Code/Anaconda/python.exe - <<'PY'
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(".env", override=False)

dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
if not dsn:
    raise SystemExit("missing SUPABASE_DB_URL or DATABASE_URL")

sql_path = Path("supabase/migrations/012_example.sql")
sql = sql_path.read_text(encoding="utf-8")

with psycopg.connect(dsn, autocommit=False) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

print(f"migration=applied file={sql_path}")
PY
```

### Verify with read-only SQL

```bash
/mnt/d/Software/Code/Anaconda/python.exe - <<'PY'
import os

import psycopg
from dotenv import load_dotenv

load_dotenv(".env", override=False)

dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
if not dsn:
    raise SystemExit("missing SUPABASE_DB_URL or DATABASE_URL")

with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("select now()")
        print("db_now=" + str(cur.fetchone()[0]))
PY
```

## 4. Linux 后端部署

先只读检查，不要直接覆盖。

```bash
ssh -i ~/.ssh/id_ed25519_prod \
  -o BatchMode=yes \
  -o ConnectTimeout=10 \
  -o StrictHostKeyChecking=accept-new \
  root@47.76.243.147 \
  "cd /opt/Jibai && git rev-parse --short HEAD && git status --short && systemctl is-active jibai-public-worker.service"
```

如果服务器工作区是干净的，可以正常拉取：

```bash
ssh -i ~/.ssh/id_ed25519_prod root@47.76.243.147 \
  "cd /opt/Jibai && git pull --ff-only origin main"
```

如果服务器工作区是脏的：

- 不要 `git reset --hard`。
- 先看脏文件是否和本次部署重叠。
- 对重叠文件，先备份 diff，再从 `origin/main` 恢复必要文件。

示例：

```bash
ssh -i ~/.ssh/id_ed25519_prod root@47.76.243.147 '
cd /opt/Jibai
GIT_SSH_COMMAND="ssh -i /root/.ssh/id_rsa_A -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" git fetch origin main
ts=$(date +%Y%m%d-%H%M%S)
mkdir -p .codex-backups
git diff -- backend src supabase > .codex-backups/deploy-overlap-$ts.patch
git checkout origin/main -- backend/src/main.py backend/packages supabase/migrations
'
```

根据实际项目替换路径，不要盲目 checkout 全仓库。

### Compile and restart

```bash
ssh -i ~/.ssh/id_ed25519_prod root@47.76.243.147 '
cd /opt/Jibai
.venv/bin/python -m compileall backend/packages backend/src
systemctl restart jibai-public-worker.service
sleep 3
systemctl status jibai-public-worker.service --no-pager -l
journalctl -u jibai-public-worker.service -n 50 --no-pager
'
```

确认点：

- `Active: active (running)`。
- journal 中有应用自己的启动日志。
- 如果有数据库依赖，确认日志中有 DB 检查或实际任务输出。

## 5. Vercel/前端验证

如果 GitHub main 会触发 Vercel 部署，推送后至少检查：

```bash
curl -I -L --max-time 30 https://<your-domain>/<route>
```

如果本机或当前网络访问 Vercel 超时，要明确说明是 HTTP 探测失败，不要把它当成代码构建失败。代码侧仍应先跑：

```bash
cd public-web
npm run lint
npm run build
```

## 6. 常见失败判断

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| GitHub `Permission denied (publickey)` | WSL 没用正确 GitHub key | 复制 Windows key 到 `~/.ssh`，用 `GIT_SSH_COMMAND` |
| SSH `bad permissions` | Windows 挂载盘私钥权限太开放 | 复制 key 到 WSL `~/.ssh` 并 `chmod 600` |
| Supabase REST key 不能执行 SQL | REST key 不是 Postgres DSN | 使用 `SUPABASE_DB_URL` / `DATABASE_URL` |
| systemd active 但没产出 | 进程活着不代表任务健康 | 查最新 `journalctl` 和业务表/队列 |
| 服务器 `git pull` 被脏文件阻塞 | 线上有本地改动 | 备份 diff，只恢复本次必要文件 |
