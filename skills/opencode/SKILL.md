---
name: opencode
description: "Delegate coding to OpenCode CLI (features, PR review)."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, OpenCode, Autonomous, Refactoring, Code-Review]
    related_skills: [claude-code, codex, hermes-agent]
---

# OpenCode CLI

Use [OpenCode](https://opencode.ai) as an autonomous coding worker orchestrated by Hermes terminal/process tools. OpenCode is a provider-agnostic, open-source AI coding agent with a TUI and CLI.

## When to Use

- User explicitly asks to use OpenCode
- You want an external coding agent to implement/refactor/review code
- You need long-running coding sessions with progress checks
- You want parallel task execution in isolated workdirs/worktrees

## Prerequisites

- OpenCode installed: `npm i -g opencode-ai@latest` or `brew install anomalyco/tap/opencode`
- Auth configured: `opencode auth login` or set provider env vars (OPENROUTER_API_KEY, etc.)
- Verify: `opencode auth list` should show at least one provider
- Git repository for code tasks (recommended)
- `pty=true` for interactive TUI sessions

## Binary Resolution (Important)

Shell environments may resolve different OpenCode binaries. If behavior differs between your terminal and Hermes, check:

```
terminal(command="which -a opencode")
terminal(command="opencode --version")
```

If needed, pin an explicit binary path:

```
terminal(command="$HOME/.opencode/bin/opencode run '...'", workdir="~/project", pty=true)
```

## One-Shot Tasks

Use `opencode run` for bounded, non-interactive tasks:

```
terminal(command="opencode run 'Add retry logic to API calls and update tests'", workdir="~/project")
```

Attach context files with `-f`:

```
terminal(command="opencode run 'Review this config for security issues' -f config.yaml -f .env.example", workdir="~/project")
```

Show model thinking with `--thinking`:

```
terminal(command="opencode run 'Debug why tests fail in CI' --thinking", workdir="~/project")
```

Force a specific model:

```
terminal(command="opencode run 'Refactor auth module' --model openrouter/anthropic/claude-sonnet-4", workdir="~/project")
```

## Interactive Sessions (Background)

For iterative work requiring multiple exchanges, start the TUI in background:

```
terminal(command="opencode", workdir="~/project", background=true, pty=true)
# Returns session_id

# Send a prompt
process(action="submit", session_id="<id>", data="Implement OAuth refresh flow and add tests")

# Monitor progress
process(action="poll", session_id="<id>")
process(action="log", session_id="<id>")

# Send follow-up input
process(action="submit", session_id="<id>", data="Now add error handling for token expiry")

# Exit cleanly — Ctrl+C
process(action="write", session_id="<id>", data="\x03")
# Or just kill the process
process(action="kill", session_id="<id>")
```

**Important:** Do NOT use `/exit` — it is not a valid OpenCode command and will open an agent selector dialog instead. Use Ctrl+C (`\x03`) or `process(action="kill")` to exit.

### TUI Keybindings

| Key | Action |
|-----|--------|
| `Enter` | Submit message (press twice if needed) |
| `Tab` | Switch between agents (build/plan) |
| `Ctrl+P` | Open command palette |
| `Ctrl+X L` | Switch session |
| `Ctrl+X M` | Switch model |
| `Ctrl+X N` | New session |
| `Ctrl+X E` | Open editor |
| `Ctrl+C` | Exit OpenCode |

### Resuming Sessions

After exiting, OpenCode prints a session ID. Resume with:

```
terminal(command="opencode -c", workdir="~/project", background=true, pty=true)  # Continue last session
terminal(command="opencode -s ses_abc123", workdir="~/project", background=true, pty=true)  # Specific session
```

## Common Flags

| Flag | Use |
|------|-----|
| `run 'prompt'` | One-shot execution and exit |
| `--continue` / `-c` | Continue the last OpenCode session |
| `--session <id>` / `-s` | Continue a specific session |
| `--agent <name>` | Choose OpenCode agent (build or plan) |
| `--model provider/model` | Force specific model |
| `--format json` | Machine-readable output/events |
| `--file <path>` / `-f` | Attach file(s) to the message |
| `--thinking` | Show model thinking blocks |
| `--variant <level>` | Reasoning effort (high, max, minimal) |
| `--title <name>` | Name the session |
| `--attach <url>` | Connect to a running opencode server |

## Procedure

1. Verify tool readiness:
   - `terminal(command="opencode --version")`
   - `terminal(command="opencode auth list")`
2. For bounded tasks, use `opencode run '...'` (no pty needed).
3. For iterative tasks, start `opencode` with `background=true, pty=true`.
4. Monitor long tasks with `process(action="poll"|"log")`.
5. If OpenCode asks for input, respond via `process(action="submit", ...)`.
6. Exit with `process(action="write", data="\x03")` or `process(action="kill")`.
7. Summarize file changes, test results, and next steps back to user.

## PR Review Workflow

OpenCode has a built-in PR command:

```
terminal(command="opencode pr 42", workdir="~/project", pty=true)
```

Or review in a temporary clone for isolation:

```
terminal(command="REVIEW=$(mktemp -d) && git clone https://github.com/user/repo.git $REVIEW && cd $REVIEW && opencode run 'Review this PR vs main. Report bugs, security risks, test gaps, and style issues.' -f $(git diff origin/main --name-only | head -20 | tr '\n' ' ')", pty=true)
```

## Parallel Work Pattern

Use separate workdirs/worktrees to avoid collisions:

```
terminal(command="opencode run 'Fix issue #101 and commit'", workdir="/tmp/issue-101", background=true, pty=true)
terminal(command="opencode run 'Add parser regression tests and commit'", workdir="/tmp/issue-102", background=true, pty=true)
process(action="list")
```

## Session & Cost Management

List past sessions:

```
terminal(command="opencode session list")
```

Check token usage and costs:

```
terminal(command="opencode stats")
terminal(command="opencode stats --days 7 --models anthropic/claude-sonnet-4")
```

## Permissions — stop the "always allow" clicks (verified v1.18.31)

Symptom: opencode keeps prompting for approval, and the prompt's `always` option only lasts the **current session** — so every new session asks again. The permissions that actually default to `ask` are `external_directory` (any tool touching a path outside the cwd — the usual culprit) and `doom_loop`; `bash`/`edit` already default to `allow`.

Permanent fix — in `~/.config/opencode/opencode.jsonc` (one config shared by CLI + Desktop):

    "permission": "allow"

String form is schema-valid and normalizes to `{ "*": "allow" }` — confirm with `opencode debug config`. Verify a change with a real run: have it read+write a path outside the cwd, then grep `~/.local/share/opencode/log/opencode.log` for `evaluated permission=external_directory ... action.permission=* action.action=allow action.pattern=*` (a session still on session-scoped always-rules logs `action.permission=external_directory action.pattern="<path>"` instead).

Scoped form (keep the default `.env` read block while allowing everything else):

    "permission": {
      "*": "allow",
      "read": { "*": "allow", "*.env": "deny", "*.env.*": "deny", "*.env.example": "allow" }
    }

One-off alternatives: `opencode --auto` / `opencode run --auto`; TUI command palette (Ctrl+P) → "Enable auto-approve permissions". Config is read once at startup — restart the app / start a new session.

## Pitfalls

- Debugging "UnknownError / Unexpected server error ... ref=err_xxx": rerun as `opencode run --print-logs --log-level DEBUG` — the real cause only prints there.
- From the Hermes MSYS terminal, `opencode run` with a cwd under `AppData\\Local\\Temp\\...` dies with `PlatformError: NotFound: FileSystem.realPath (C:\\tmp\\<dir>)` (MSYS `TMPDIR=/tmp` resolving to a nonexistent `C:\tmp`); run from a normal project dir.
- Interactive `opencode` (TUI) sessions require `pty=true`. The `opencode run` command does NOT need pty.
- `/exit` is NOT a valid command — it opens an agent selector. Use Ctrl+C to exit the TUI.
- PATH mismatch can select the wrong OpenCode binary/model config.
- If OpenCode appears stuck, inspect logs before killing:
  - `process(action="log", session_id="<id>")`
- Avoid sharing one working directory across parallel OpenCode sessions.
- Enter may need to be pressed twice to submit in the TUI (once to finalize text, once to send).

## Verification

Smoke test:

```
terminal(command="opencode run 'Respond with exactly: OPENCODE_SMOKE_OK'")
```

Success criteria:
- Output includes `OPENCODE_SMOKE_OK`
- Command exits without provider/model errors
- For code tasks: expected files changed and tests pass

## Rules

1. Prefer `opencode run` for one-shot automation — it's simpler and doesn't need pty.
2. Use interactive background mode only when iteration is needed.
3. Always scope OpenCode sessions to a single repo/workdir.
4. For long tasks, provide progress updates from `process` logs.
5. Report concrete outcomes (files changed, tests, remaining risks).
6. Exit interactive sessions with Ctrl+C or kill, never `/exit`.

## Seagull Persona Setup (Windows, this user)

The user's opencode stack = OpenCode Desktop (`SST.OpenCodeDesktop`, winget) + npm CLI (`opencode-ai`) — both share one config root `~/.config/opencode/`:

| File | Role |
|---|---|
| `~/.config/opencode/AGENTS.md` | 海鸥 global rules. Rebuild: `python C:/Users/19123/.config/opencode/scripts/rebuild-agents.py` — source is `~/.pi/agent/APPEND_SYSTEM.md` with the runtime section swapped for opencode |
| `~/.config/opencode/opencode.jsonc` | `model: deepseek/deepseek-flash`; `skills.paths: ["~/AppData/Local/hermes/profiles/seagull/skills"]` (68 seagull skills, loader scans `**/SKILL.md` recursively) |
| `~/.local/share/opencode/auth.json` | deepseek API key (do not touch) |
| `~/.config/opencode/backups/seagull-opencode-*` | persona backups + `valid_skills.json` manifest |

Verify (real runs, never guess):
- `opencode debug skill` → 69 entries (68 user + builtin `customize-opencode`)
- `opencode debug config` → resolved model + skills
- `opencode run "在吗"` → `海鸥在线，你要整点薯条吗？`
- `opencode run "逆向"` → first line `逆向工程已打开` + `→ Skill "seagull-reverse"`

Pitfalls:
- Config loads ONCE at startup; editing AGENTS.md/config requires app restart / new session (running sessions keep old config).
- Desktop app is the same core sharing the same config dir — no separate setup, just restart it (restart verified live: desktop new session '在吗' answered `海鸥在线，你要整点薯条吗？`; CLI + desktop both keep returning the seagull greeting on 'hi').
- Native python needs `C:/...` paths (not `/c/...`); inline heredoc python gets backslash-mangled by MSYS — write .py files then execute.
- npm allow-scripts warning on opencode-ai postinstall is harmless (verified working without it).
- Skill frontmatter must have `name` matching folder + `description`; unknown fields ignored. 68/68 seagull skills validated.
