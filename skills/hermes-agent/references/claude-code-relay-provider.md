# Wiring a Claude Code relay (CC Switch / 中转站) into Hermes

Third-party Claude relays speak the Anthropic Messages protocol at a custom host
(e.g. `https://sub.ns.tisoz.com`, token from `~/.cc-switch/cc-switch.db` or
`~/.claude/settings.json` env). Use a NAMED CUSTOM PROVIDER, not the native
`anthropic` provider — the native one gates `model.base_url` behind a host
whitelist (`_anthropic_base_url_override_ok` in hermes_cli/runtime_provider.py)
and silently falls back to api.anthropic.com for unknown hosts.

## Config (per profile)

```bash
hermes config set providers.<name>.name "<display>"
hermes config set providers.<name>.base_url "https://relay.host"
hermes config set providers.<name>.key_env "<NAME>_API_KEY"
hermes config set providers.<name>.transport "anthropic_messages"   # or api_mode:
hermes config set providers.<name>.default_model "<model-id>"
hermes config set model.provider "<name>"
hermes config set model.default "<model-id>"
hermes config set <NAME>_API_KEY "sk-..."    # writes the profile .env
```

Dotted `hermes config set` keys create the nested YAML; do not hand-edit
config.yaml. At runtime this resolves to provider `custom` + api_mode
`anthropic_messages`, and agent/anthropic_adapter.py `_auth_style()` classifies
third-party hosts as x-api-key auth with the SDK's default UA.

## Pitfalls (learned the hard way)

- Cloudflare WAF in front of some relays blocks the literal UA `Python-urllib/*`
  (http 403 "error code: 1010") — every other UA passes, including the SDK
  default `Anthropic/Python x.y`, so no header injection is needed once you stop
  testing with urllib.
- Some relays accept a `model[1M]` suffix for 1M context; the plain id works too.
- Aux calls at session teardown (title generation) can race client shutdown on
  these relays ("Connection error" / "incomplete chunked read" right after
  "CLI cleanup"); retries cover it, titles may fall back to prompt truncation.
- Relay model catalog: `curl -H "user-agent: claude-cli/2.1.1 (external, cli)" \
  -H "x-api-key: $KEY" https://host/v1/models`.

## Verify it actually went through the relay

```bash
hermes chat -q "Reply with exactly: OK"
hermes chat -q "say OK" --provider <name> -m <other-model>   # model switch
# then confirm the endpoint that served the session:
python -c "import sqlite3;c=sqlite3.connect(r'%LOCALAPPDATA%\\hermes\\profiles\\<p>\\state.db');print(c.execute(\"SELECT model,billing_provider,billing_base_url FROM sessions ORDER BY started_at DESC LIMIT 1\").fetchone())"
```

`billing_provider='custom'` + the relay host in `billing_base_url` = request
really hit the relay. Tool-use rounds prove the anthropic_messages wire
conversion works end-to-end.

## Making Hermes follow an external provider switcher (CC Switch setup)

CC Switch keeps `currentProviderClaude` in `~/.cc-switch/settings.json`; the
provider row (base_url / token / model) lives in `~/.cc-switch/cc-switch.db`
(`providers` table, app_type='claude'). To follow switches automatically:

- Register each station once as a Hermes provider entry (e.g. `tisoz`,
  `aftpai`), keys all seeded in .env (multiple keys can coexist).
- Follower script `C:\Users\19123\ccswitch-sync\hermes_ccswitch_follow.py`:
  `--watch` = change-driven 15s poll; manual `hermes-ccsync.cmd` = force align;
  `--status` / `--dry-run` for inspection. Autostart = Startup-folder .lnk to
  `venv\Scripts\pythonw.exe ... --watch`.
- Design rules that keep it robust: watch mode acts ONLY when the station
  (id / base_url / token-sha) changed → never fights manual Hermes edits;
  manual runs force-align; all config writes go through `hermes config set`;
  state file stores only a token sha1, never the token.

Windows gotchas hit while building it:
- `Register-ScheduledTask` / `schtasks /Create` can fail with Access denied
  without elevation — fall back to a Startup-folder .lnk (WScript.Shell COM
  `CreateShortcut`), no admin needed.
- Under `pythonw.exe`, `sys.stdout` is None and `print()` raises: guard it.
- `subprocess.run(text=True)` against the hermes CLI can hit a UTF-8 output
  vs cp936 pipe mismatch: pass `encoding='utf-8', errors='replace'` and
  `PYTHONIOENCODING=utf-8` or you get decode errors / mojibake.

## OpenAI-protocol stations (CC Switch `codex` rows)

CC Switch `codex`-type providers are OpenAI-wire relays. Same named-custom-provider pattern as above, with three deltas: `base_url` MUST carry `/v1` (hermes appends `/chat/completions` or `/responses`); token lives at `settings_config.auth.OPENAI_API_KEY`; `transport: chat_completions` is the canonical choice (`codex_responses` also parses but see stream caveats below). `models: {id: {}...}` populates the model picker; `context_length` sets the window.

```bash
hermes config set providers.<slug>.base_url "https://host/v1"
hermes config set providers.<slug>.key_env "<SLUG>_API_KEY"
hermes config set providers.<slug>.transport "chat_completions"
hermes config set providers.<slug>.models '{"gpt-x": {}, ...}'
hermes config set <SLUG>_API_KEY "sk-..."     # writes the profile .env
```

### Broken streaming relays → `model.streaming: false`

Some relays break the openai SDK **only when stream=true** (non-stream is fine on both wires):
- responses-wire SSE whose event separators are a bare `\n` instead of a blank line → the SDK's SSEDecoder merges events → `JSONDecodeError: Extra data: line 2 column 1` (char offset = length of the first event's JSON);
- chat-wire streaming WITH `tools[]` returns empty/corrupted `delta.content` while usage still counts tokens; without tools the same stream is fine.

Diagnose by replaying a session's request dump (`profiles/<p>/sessions/request_dump_<sid>_<ts>.json`) against the station with requests or the openai SDK, inspecting raw SSE bytes. Fix: `hermes config set model.streaming false` — seeds `agent._disable_streaming` in agent_init (comment: "for backends with broken streaming tool calls"). It is GLOBAL across providers (no per-provider override exists); claude/deepseek/others keep working, only token-by-token UI is lost. Revert with `hermes config unset model.streaming`.

Station note (tisoz / sub.ns.tisoz.com, serves both claude and openai rows on one host): the CF-fronted origin also flaps with 502s under load and individual models 5xx independently — retry probes before concluding a wire is broken.
