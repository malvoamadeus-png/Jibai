# Codex Linux Access

This document tells a new Codex session how to connect to the Linux server.
It is intentionally project-neutral: it only covers SSH/MCP access and safe
remote-command habits.

## Connection

Current server access:

- Host: `47.76.243.147`
- User: `root`
- Private key: `C:\Users\Windows\.ssh\id_ed25519`
- MCP server name: `ssh-prod`

Do not paste private-key contents, database URLs, API keys, tokens, cookies, or
other secrets into chat, documentation, commits, or logs.

## Recommended Setup: Codex MCP

Run this once on the Windows machine:

```powershell
codex mcp add ssh-prod -- npx -y ssh-mcp -- --host=47.76.243.147 --user=root --key=C:\Users\Windows\.ssh\id_ed25519
```

This writes the MCP server into the current Windows user's global Codex config:

```text
C:\Users\Windows\.codex\config.toml
```

New Codex sessions on the same Windows user normally discover `ssh-prod`
automatically. Sessions that were already open may not hot-reload the MCP
server; restart Codex or open a new session if the tool is missing.

Once available, ask Codex directly:

```text
Use ssh-prod to connect to the Linux server and run a read-only diagnostic command.
```

## Optional Setup: SSH Alias

You can also define an SSH alias in `C:\Users\Windows\.ssh\config`:

```sshconfig
Host linux-prod
  HostName 47.76.243.147
  User root
  IdentityFile C:\Users\Windows\.ssh\id_ed25519
```

Then register MCP against the alias:

```powershell
codex mcp add ssh-prod -- npx -y ssh-mcp -- --host=linux-prod
```

With this approach, changing the host, user, or key only requires updating the
SSH config.

## Fallback: Direct SSH

If the current Codex session cannot see the MCP tool, direct SSH still works
from PowerShell:

```powershell
ssh -i C:\Users\Windows\.ssh\id_ed25519 -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new root@47.76.243.147 "pwd && hostname && uptime"
```

For multiline diagnostics, pass the script through stdin to avoid quoting
problems:

```powershell
$script = @'
set -e
pwd
hostname
uptime
df -h
'@

$script | ssh -i C:\Users\Windows\.ssh\id_ed25519 -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new root@47.76.243.147 "bash -s"
```

## Safe Remote-Command Rules

- Prefer read-only commands first: `pwd`, `hostname`, `uptime`, `ps`, `df`,
  `systemctl status`, `journalctl`, `ls`, `find`, `grep`, and application
  health checks.
- When inspecting environment variables, print variable names only unless the
  user explicitly asks for values and understands the risk.
- Do not run destructive commands such as `rm -rf`, `git reset --hard`,
  forced overwrites, database migrations, or service restarts unless the user
  requested that exact action.
- For long outputs, limit the result with options such as `-n`, `--no-pager`,
  or explicit filters.
- Put temporary scripts in `/tmp` and remove them after use.
- If a command changes state, state the intended impact before running it.
