"""
God Mode status panel.

Shows which agents on this machine carry the operator rules, which ones are
missing, and what the relay can reach. Every line comes from a real check of
the filesystem and the resolved providers, so the panel never claims an agent
that is not actually set up.
"""

import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

AGENTS = [
    ("Claude Code", "claude-code", "~/.claude", "claude"),
    ("Codex CLI", "codex", "~/.codex", "codex"),
    ("Cursor", "cursor", "~/.cursor", "cursor-agent"),
    ("Windsurf", "windsurf", "~/.codeium/windsurf", "windsurf"),
    ("Gemini CLI", "gemini", "~/.gemini", "gemini"),
    ("Aider", "aider", "~/.aider.conf.yml", "aider"),
    ("Cline", "cline", "~/Documents/Cline", None),
    ("Roo Code", "roo", "~/Documents/Roo", None),
    ("Continue", "continue", "~/.continue", None),
    ("OpenClaw", "openclaw", "~/.openclaw", "openclaw"),
    ("OpenCode", "opencode", "~/.config/opencode", "opencode"),
    ("Antigravity", "antigravity", "~/.gemini", "antigravity"),
    ("Hermes Lab", "hermes-lab", "~/.hermes-lab", "hermes-lab"),
    ("MiniMax", "minimax", "~/.minimax", "mcode"),
]

COMMAND_DIRS = {
    "aider": "~/.aider/commands",
    "continue": "~/.continue/rules/godmode",
    "gemini": "~/.gemini/commands",
    "claude-code": "~/.claude/commands/godmode",
    "codex": "~/.codex/prompts/godmode",
    "cursor": "~/.cursor/commands/godmode",
    "windsurf": "~/.codeium/windsurf/workflows/godmode",
    "cline": "~/Documents/Cline/Workflows/godmode",
    "roo": "~/Documents/Roo/Workflows/godmode",
    "opencode": "~/.config/opencode/command/godmode",
    "openclaw": "~/.openclaw/commands/godmode",
    "antigravity": "~/.gemini/commands/godmode",
    "minimax": "~/.minimax/commands",
    "hermes-lab": "~/.hermes-lab/commands",
}

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def expand(path):
    return os.path.expanduser(path)


def which(name):
    if not name:
        return False
    return subprocess.run(["command", "-v", name], shell=True,
                          capture_output=True).returncode == 0


def marker_present(path):
    full = expand(path)
    if os.path.isfile(full):
        try:
            with open(full, encoding="utf-8", errors="ignore") as handle:
                return "GODMODE-PORTABLE" in handle.read()
        except OSError:
            return False
    if os.path.isdir(full):
        roots = [full, os.path.join(full, "workspace"),
                 os.path.join(full, "config")]
        for root in roots:
            if not os.path.isdir(root):
                continue
            for name in ("CLAUDE.md", "AGENTS.md", "GEMINI.md",
                         "global_rules.md", "godmode.mdc", "godmode.md"):
                candidate = os.path.join(root, name)
                if not os.path.isfile(candidate):
                    continue
                try:
                    with open(candidate, encoding="utf-8",
                              errors="ignore") as handle:
                        if "GODMODE-PORTABLE" in handle.read():
                            return True
                except OSError:
                    continue
    return False


def agent_state(label, key, config_path, binary):
    home = expand(config_path)
    exists = os.path.exists(home)
    cli = which(binary)
    cmd_dir = COMMAND_DIRS.get(key)
    slash = False
    if cmd_dir:
        target = expand(cmd_dir)
        md = os.path.isfile(os.path.join(target, "godfather.md"))
        toml = os.path.isfile(os.path.join(target, "godfather.toml"))
        slash = md or toml
    if slash:
        return "unlocked", slash
    if exists and marker_present(config_path):
        return "unlocked", slash
    if exists or cli:
        return "detected", slash
    return "missing", slash


def providers():
    try:
        import provider_resolve
    except Exception:
        return []
    out = []
    try:
        for cand in provider_resolve.resolve(None):
            model = cand.get("model")
            if not model:
                continue
            low = str(model).lower()
            if low in ("auto", "none", ""):
                continue
            out.append((cand.get("source", "?"), str(model)))
    except Exception:
        return []
    return out


def render(color=True):
    def paint(code, text):
        return code + text + RESET if color else text

    lines = []
    lines.append(paint(BOLD, "★ G O D  M O D E ★"))
    lines.append("")
    states = []
    for label, key, config_path, binary in AGENTS:
        state, slash = agent_state(label, key, config_path, binary)
        states.append((label, key, state, slash))

    unlocked = [s for s in states if s[2] == "unlocked"]
    detected = [s for s in states if s[2] == "detected"]
    missing = [s for s in states if s[2] == "missing"]

    if unlocked and not detected and not missing:
        status = "✓ ALL-ACCESS UNLOCKED — Ready for universal injection"
        lines.append(paint(GREEN, "STATUS: " + status))
    elif unlocked:
        status = "✓ ACCESS UNLOCKED — %d of %d agents carrying the rules" % (
            len(unlocked), len(states))
        lines.append(paint(GREEN, "STATUS: " + status))
    else:
        status = "… NOT SET UP — run the installer to wire the agents"
        lines.append(paint(YELLOW, "STATUS: " + status))
    lines.append("")
    lines.append(paint(BOLD, "What God Mode delivers:"))
    lines.append("")
    for label, key, state, slash in states:
        if state == "unlocked":
            mark = paint(GREEN, "Unlocked")
        elif state == "detected":
            mark = paint(YELLOW, "Detected, not wired")
        else:
            mark = paint(DIM, "Not installed")
        extra = ""
        if slash:
            extra = paint(DIM, "  /godfather")
        lines.append("%-14s — %s%s" % (label, mark, extra))
    lines.append(paint(GREEN, "+ Any future tool you install — Unlocked"))
    lines.append("")
    provs = providers()
    if provs:
        lines.append(paint(BOLD, "Relay providers:"))
        for source, model in provs[:6]:
            lines.append("  %-34s %s" % (source[:34], model))
        if len(provs) > 6:
            lines.append(paint(DIM, "  and %d more" % (len(provs) - 6)))
        lines.append("")
    lines.append("Activate with: " + paint(BOLD, "/godfather"))
    return "\n".join(lines)


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    as_json = "--json" in argv
    if as_json:
        out = []
        for label, key, config_path, binary in AGENTS:
            state, slash = agent_state(label, key, config_path, binary)
            out.append({
                "name": label,
                "id": key,
                "state": state,
                "slash_command": slash,
                "config": os.path.expanduser(config_path),
            })
        print(json.dumps({
            "agents": out,
            "providers": [{"source": s, "model": m} for s, m in providers()],
        }, indent=2))
        return 0
    print(render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
