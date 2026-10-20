
"""
provider_resolve — discover the endpoint, key and model an agent is already
using, so the jailbreak applies to that provider instead of a hardcoded one.

Reads, in priority order:
  explicit --provider/--base-url/--api-key/--model
  agent config files (claude, codex, gemini, aider, continue, hermes, cursor)
  environment variables

Output: JSON list of candidates, highest priority first.

    python3 provider_resolve.py
    python3 provider_resolve.py --json
    python3 provider_resolve.py --agent codex --json
"""

import argparse
import json
import os
import re
import sys

HOME = os.path.expanduser("~")

def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None

def _load_json(path):
    raw = _read(path)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None

def _load_yaml(path):
    raw = _read(path)
    if not raw:
        return None
    try:
        import yaml
        return yaml.safe_load(raw)
    except Exception:
        return None

def _load_toml(path):
    raw = _read(path)
    if not raw:
        return None
    try:
        import tomllib
        return tomllib.loads(raw)
    except Exception:
        try:
            import toml
            return toml.loads(raw)
        except Exception:
            return None

def _dotenv(path):
    raw = _read(path)
    if not raw:
        return {}
    out = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        out[k.strip()] = v
    return out

def _merge_env(extra):
    merged = {}
    godmode = _dotenv(os.path.join(HOME, ".godmode", "env"))
    merged.update({k: v for k, v in godmode.items() if v})
    for src in (_dotenv(os.path.join(HOME, ".hermes", ".env")),
                _dotenv(os.path.join(HOME, ".gemini", ".env")),
                _dotenv(os.path.join(HOME, ".env"))):
        merged.update({k: v for k, v in src.items() if v})
    for k, v in os.environ.items():
        if v:
            merged[k] = v
    if extra:
        merged.update({k: v for k, v in extra.items() if v})
    return merged

def _resolve_secret(env, raw):
    if not raw:
        return None
    raw = str(raw).strip()
    m = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", raw)
    if m:
        return _pick(env, m.group(1))
    m = re.fullmatch(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}", raw)
    if m:
        return _pick(env, m.group(1))
    m = re.fullmatch(r"\{file:(.+)\}", raw)
    if m:
        path = os.path.expanduser(m.group(1).strip())
        content = _read(path)
        return content.strip() if content else None
    if raw.startswith("{") and raw.endswith("}"):
        return None
    return raw

def _pick(env, *names):
    for n in names:
        v = env.get(n)
        if v:
            return v
    return None

def _cand(env, base, key, model, transport, source, extra_models=None):
    if not base or not key:
        return None
    return {
        "source": source,
        "base_url": base.rstrip("/"),
        "api_key": key,
        "model": model,
        "transport": transport,
        "extra_models": extra_models or [],
    }

def from_claude(env):
    out = []
    settings = _load_json(os.path.join(HOME, ".claude", "settings.json")) or {}
    senv = settings.get("env") or {}
    base = senv.get("ANTHROPIC_BASE_URL") or _pick(env, "ANTHROPIC_BASE_URL")
    key = senv.get("ANTHROPIC_AUTH_TOKEN") or senv.get("ANTHROPIC_API_KEY") \
        or _pick(env, "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")
    model = senv.get("ANTHROPIC_MODEL") or _pick(env, "ANTHROPIC_MODEL") \
        or "claude-sonnet-4-20250514"
    c = _cand(env, base, key, model, "anthropic", "claude-code")
    if c:
        out.append(c)
    claude_json = _load_json(os.path.join(HOME, ".claude.json")) or {}
    for key_name, val in (claude_json.get("mcpServers") or {}).items():
        pass
    return out

def from_codex(env):
    out = []
    cfg = _load_toml(os.path.join(HOME, ".codex", "config.toml")) or {}
    providers = cfg.get("model_providers") or {}
    active = cfg.get("model_provider")
    model = cfg.get("model")
    for pname, pcfg in providers.items():
        base = pcfg.get("base_url")
        env_key = pcfg.get("env_key")
        key = _pick(env, env_key) if env_key else None
        transport = "anthropic" if "anthropic" in str(pcfg.get("wire_api", "")) \
            else "openai"
        c = _cand(env, base, key, model, transport,
                  f"codex:{pname}" + (" (active)" if pname == active else ""))
        if c:
            out.append(c)
    return out

def from_gemini(env):
    out = []
    settings = _load_json(os.path.join(HOME, ".gemini", "settings.json")) or {}
    senv = settings.get("env") or {}
    base = senv.get("GOOGLE_GEMINI_BASE_URL") or senv.get("GEMINI_BASE_URL")
    key = senv.get("GEMINI_API_KEY") or senv.get("GOOGLE_API_KEY")
    model = senv.get("GEMINI_MODEL") or "gemini-2.5-pro"
    c = _cand(env, base, key, model, "gemini", "gemini-cli")
    if c:
        out.append(c)
    return out

def from_aider(env):
    out = []
    raw = _read(os.path.join(HOME, ".aider.conf.yml")) or ""
    def val(key):
        m = re.search(rf"^\s*{key}\s*:\s*(.+)$", raw, re.MULTILINE)
        return m.group(1).strip().strip('"\'') if m else None
    base = val("openai-api-base")
    key = val("openai-api-key")
    model = val("model")
    c = _cand(env, base, key, model, "openai", "aider")
    if c:
        out.append(c)
    return out

def from_continue(env):
    out = []
    cfg = _load_yaml(os.path.join(HOME, ".continue", "config.yaml")) or {}
    models = cfg.get("models") or []
    for m in models:
        if isinstance(m, dict) and m.get("provider") in ("openai", "anthropic",
                                                          "openai-compatible"):
            c = _cand(env, m.get("apiBase"), m.get("apiKey"), m.get("model"),
                      "anthropic" if m.get("provider") == "anthropic" else "openai",
                      "continue")
            if c:
                out.append(c)
    return out

def from_cursor(env):
    out = []
    cfg = _load_json(os.path.join(HOME, ".cursor", "mcp.json")) or {}
    for _, srv in (cfg.get("mcpServers") or {}).items():
        envs = (srv or {}).get("env") or {}
        base = envs.get("OPENAI_BASE_URL") or envs.get("OPENAI_API_BASE")
        key = envs.get("OPENAI_API_KEY")
        c = _cand(env, base, key, envs.get("OPENAI_MODEL"), "openai", "cursor")
        if c:
            out.append(c)
    return out

def from_hermes(env):
    out = []
    cfg = _load_yaml(os.path.join(HOME, ".hermes", "config.yaml")) or {}
    providers = cfg.get("providers") or {}
    default = (cfg.get("model") or {}).get("default")
    for name, p in providers.items():
        if not isinstance(p, dict):
            continue
        key_env = p.get("key_env")
        key = _pick(env, key_env) if key_env else None
        base = p.get("base_url")
        model = p.get("model")
        transport = "anthropic" if p.get("transport") == "anthropic_messages" else "openai"
        extras = list((p.get("models") or {}).keys()) if isinstance(p.get("models"), dict) else []
        c = _cand(env, base, key, model, transport, f"hermes:{name}", extras)
        if c:
            c["discover_models"] = bool(p.get("discover_models"))
            c["extra_models"] = [m for m in c["extra_models"] if m != model][:12]
            if name == default or (isinstance(default, str) and default.startswith(name)):
                c["source"] += " (default)"
            out.append(c)
    return out

def from_openclaw(env):
    out = []
    cfg = _load_json(os.path.join(HOME, ".openclaw", "openclaw.json")) or {}
    providers = ((cfg.get("models") or {}).get("providers") or {})
    default = (((cfg.get("agents") or {}).get("defaults") or {}).get("model") or {}).get("primary")
    for name, p in providers.items():
        if not isinstance(p, dict):
            continue
        base = p.get("baseUrl") or p.get("baseURL")
        raw_key = p.get("apiKey") or ""
        key = _resolve_secret(env, raw_key)
        api = (p.get("api") or "openai-completions").lower()
        transport = "anthropic" if "anthropic" in api else ("gemini" if "google" in api or "generative" in api else "openai")
        ids = [m.get("id") for m in (p.get("models") or []) if isinstance(m, dict) and m.get("id")]
        model = None
        if default and "/" in default and default.split("/", 1)[0] == name:
            model = default.split("/", 1)[1]
        if not model and ids:
            model = ids[0]
        extras = [m for m in ids if m != model][:12]
        c = _cand(env, base, key, model, transport, f"openclaw:{name}", extras)
        if c:
            if default and model and default.split("/")[-1] == model:
                c["source"] += " (default)"
            out.append(c)
    return out

def from_opencode(env):
    out = []
    cfg = _load_json(os.path.join(HOME, ".config", "opencode", "opencode.json")) or {}
    providers = cfg.get("provider") or {}
    auth = _load_json(os.path.join(HOME, ".local", "share", "opencode", "auth.json")) or {}
    default = cfg.get("model")
    default_provider = default.split("/", 1)[0] if default and "/" in default else None
    default_model = default.split("/", 1)[1] if default and "/" in default else None
    for name, p in providers.items():
        if not isinstance(p, dict):
            continue
        opts = p.get("options") or {}
        base = opts.get("baseURL") or opts.get("baseUrl")
        key = _resolve_secret(env, opts.get("apiKey") or "")
        if not key:
            entry = auth.get(name) or {}
            if isinstance(entry, dict):
                key = entry.get("key") or entry.get("apiKey") or entry.get("access") or ""
                if not base:
                    base = entry.get("baseURL") or entry.get("baseUrl")
        if not base:
            continue
        models = p.get("models") or {}
        ids = list(models.keys()) if isinstance(models, dict) else []
        model = default_model if default_provider == name else None
        if not model and ids:
            model = ids[0]
        npm = (p.get("npm") or "").lower()
        transport = "anthropic" if "anthropic" in npm or name == "anthropic" else (
            "gemini" if "google" in npm or "google" in name else "openai")
        extras = [m for m in ids if m != model][:12]
        c = _cand(env, base, key, model, transport, f"opencode:{name}", extras)
        if c:
            if default_provider == name:
                c["source"] += " (default)"
            out.append(c)
    return out

def from_env(env):
    out = []
    pairs = [
        ("GODMODE_BASE_URL", "GODMODE_API_KEY", "GODMODE_MODEL", "openai"),
        ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL", "openai"),
        ("OPENROUTER_BASE_URL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "openai"),
        ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "anthropic"),
        ("DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "openai"),
        ("GEMINI_BASE_URL", "GEMINI_API_KEY", "GEMINI_MODEL", "gemini"),
        ("GROQ_BASE_URL", "GROQ_API_KEY", "GROQ_MODEL", "openai"),
        ("MISTRAL_BASE_URL", "MISTRAL_API_KEY", "MISTRAL_MODEL", "openai"),
        ("XAI_BASE_URL", "XAI_API_KEY", "XAI_MODEL", "openai"),
        ("TOGETHER_BASE_URL", "TOGETHER_API_KEY", "TOGETHER_MODEL", "openai"),
    ]
    for bk, kk, mk, transport in pairs:
        base = env.get(bk)
        if not base:
            base = "https://api.openai.com/v1" if bk.startswith("OPENAI_") else None
        key = env.get(kk)
        model = env.get(mk)
        c = _cand(env, base, key, model, transport, f"env:{kk}")
        if c:
            out.append(c)
    return out

SOURCES = {
    "claude-code": from_claude,
    "codex": from_codex,
    "gemini": from_gemini,
    "aider": from_aider,
    "continue": from_continue,
    "cursor": from_cursor,
    "hermes": from_hermes,
    "openclaw": from_openclaw,
    "opencode": from_opencode,
    "env": from_env,
}

def resolve(agent=None, env_extra=None, explicit=None):
    env = _merge_env(env_extra)
    cands = []

    if explicit:
        c = _cand(env, explicit.get("base_url"), explicit.get("api_key"),
                  explicit.get("model"), explicit.get("transport", "openai"),
                  "explicit")
        if c:
            cands.append(c)

    if agent:
        fn = SOURCES.get(agent)
        if fn:
            cands.extend(fn(env))
    else:
        for name in ("claude-code", "codex", "gemini", "cursor", "aider",
                     "continue", "hermes", "openclaw", "opencode", "env"):
            cands.extend(SOURCES[name](env))

    seen = set()
    out = []
    for c in cands:
        sig = (c["base_url"], c["model"])
        if sig in seen:
            continue
        seen.add(sig)
        out.append(c)
    return out

def main(argv=None):
    ap = argparse.ArgumentParser(description="Discover agent providers")
    ap.add_argument("--agent", choices=sorted(SOURCES), default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--transport", default="openai")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-key", action="store_true")
    args = ap.parse_args(argv)

    explicit = None
    if args.base_url or args.api_key or args.model:
        explicit = {
            "base_url": args.base_url,
            "api_key": args.api_key,
            "model": args.model,
            "transport": args.transport,
        }

    cands = resolve(args.agent, explicit=explicit)
    if not cands:
        print("no provider found. Set the agent's API key/base URL, or pass "
              "--base-url/--api-key/--model", file=sys.stderr)
        return 1

    if args.json:
        payload = []
        for c in cands:
            d = dict(c)
            if not args.show_key:
                k = d["api_key"] or ""
                d["api_key"] = (k[:6] + "..." + k[-4:]) if len(k) > 12 else "***"
            payload.append(d)
        print(json.dumps(payload, indent=2))
        return 0

    for c in cands:
        k = c["api_key"] or ""
        masked = (k[:6] + "..." + k[-4:]) if len(k) > 12 else "***"
        print(f"{c['source']:<28} {c['base_url']}")
        print(f"{'':<28} model={c['model']} transport={c['transport']} key={masked}")
        if c["extra_models"]:
            print(f"{'':<28} siblings={', '.join(c['extra_models'][:6])}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
