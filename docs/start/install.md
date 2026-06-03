# Install

RepowirePlus runs on macOS and Linux with Python 3.10+ and tmux. Native Windows
support uses Python 3.10+, PowerShell 7+, and psmux as the tmux-compatible pane
host.

## Recommended

```bash
curl -sSf https://raw.githubusercontent.com/ROHITHGMURALI/repowireplus/main/install.sh | sh
```

On Windows:

```powershell
winget install psmux
irm https://raw.githubusercontent.com/ROHITHGMURALI/repowireplus/main/install.ps1 | iex
```

Without psmux, Repowire can still run the daemon, dashboard, MCP, relay, and
queued-delivery surfaces, but native pane spawn/injection is degraded.

The installer detects `uv`, `pipx`, and `pip` in that order, installs RepowirePlus from the [ROHITHGMURALI/repowireplus](https://github.com/ROHITHGMURALI/repowireplus) fork, then drops you into [setup](setup.md). The installed CLI is still named `repowire`.

## Alternatives

```bash
uv tool install git+https://github.com/ROHITHGMURALI/repowireplus.git
pipx install git+https://github.com/ROHITHGMURALI/repowireplus.git
pip install "git+https://github.com/ROHITHGMURALI/repowireplus.git"
```

Use `uv` for the fastest isolated install. Use `pipx` if you want isolation without uv. Use plain `pip` only inside a virtualenv you control. Installing `repowire` from PyPI may install the upstream package rather than this fork.

## What gets installed

The package ships:

- The `repowire` CLI (`repowire setup`, `repowire serve`, `repowire telegram start`, …).
- The local daemon (HTTP + WebSocket on `127.0.0.1:8377`).
- The MCP server (stdio).
- Hook scripts for every agent runtime the setup step detects.
- The Next.js dashboard, pre-built and served from the daemon at `/dashboard`.

Nothing runs yet. Run [setup](setup.md) to wire the hooks for your agents.

Repowire does not install third-party agent skills. If you want reusable `SKILL.md` packages, use a skills installer such as [Vercel Labs `skills`](https://github.com/vercel-labs/skills) alongside Repowire.

## Uninstall

Remove Repowire's runtime wiring first:

```bash
repowire uninstall
```

This removes installed hooks, MCP entries, channel transport config, OpenCode
plugin files, and the daemon service. On Windows, the daemon service is the
per-user Task Scheduler entry named `RepowireDaemon`.

Then remove the installed CLI with the package manager you used:

```bash
uv tool uninstall repowire
pipx uninstall repowire
python -m pip uninstall repowire
```

If you only want to remove the daemon service and keep hooks/config installed:

```bash
repowire service uninstall
```

Optional local state cleanup:

```bash
rm -rf ~/.repowire
```

On Windows, remove `%USERPROFILE%\.repowire` instead. This deletes local config,
events, attachments, relay keys, and SQLite state.
