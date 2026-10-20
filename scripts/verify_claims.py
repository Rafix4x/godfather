"""
verify_claims — recompute every factual claim in README.md from the committed
tree.

The README is a contract. This harness treats it as one: each claim is bound to
an exact piece of README text and to a checker that recomputes it from the
files in this repository. A claim that cannot be reproduced fails, the process
exits non-zero, and the release is blocked.

    python3 scripts/verify_claims.py
    python3 scripts/verify_claims.py --list
    python3 scripts/verify_claims.py --json

Stdlib only, Python 3.9+. No pip install.
"""

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_PATH = os.path.join(REPO_ROOT, "README.md")
INSTALL_SH = os.path.join(REPO_ROOT, "install.sh")
ADAPTERS_DIR = os.path.join(REPO_ROOT, "adapters")
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")

RUN_TIMEOUT = 180
NETWORK_TIMEOUT = 15

README_WRITES_TABLE = """
| Agent | Global | Project |
|:------|:-------|:--------|
| Claude Code | `~/.claude/skills/godmode/SKILL.md`, `~/.claude/CLAUDE.md` | `.claude/skills/godmode/SKILL.md`, `CLAUDE.md` |
| Codex CLI | `~/.codex/AGENTS.md`, `~/.codex/prompts/godmode.md` | `AGENTS.md` |
| Cursor | `~/.cursor/rules/godmode.mdc` | `.cursor/rules/godmode.mdc` |
| Windsurf | `~/.codeium/windsurf/memories/global_rules.md` | `.windsurf/rules/godmode.md` |
| Gemini CLI | `~/.gemini/GEMINI.md` | `GEMINI.md` |
| Aider | — | `CONVENTIONS.md` + `~/.aider.conf.yml` `read:` entry |
| Cline | `~/Documents/Cline/Rules/godmode.md` | `.clinerules/godmode.md` |
| Roo Code | `~/Documents/Roo/Rules/godmode.md` | `.roo/rules/godmode.md` |
| Continue | `~/.continue/rules/godmode.md` | `.continue/rules/godmode.md` |
| OpenClaw | `~/.openclaw/workspace/AGENTS.md`, `~/.openclaw/skills/godfather/` | `AGENTS.md`, `skills/godfather/` |
| OpenCode | `~/.config/opencode/AGENTS.md`, `~/.config/opencode/skills/godfather/` | `AGENTS.md`, `.opencode/skills/godfather/` |
| Core | `~/.godmode/scripts/`, `~/.godmode/env` | — |
"""

README_INSTALL_BLOCK = """
bash install.sh --dry-run      # preview every write
bash install.sh                # install (auto-detects your agents)
bash install.sh --agents claude-code,codex
bash install.sh --uninstall    # clean removal, backups kept
"""

README_LAYOUT_BLOCK = """
bootstrap.sh                   one-line installer from GitHub
install.sh                     installer / uninstaller
install-termux.sh              Termux / Android installer
install-mcp.sh                 register the MCP server with your agents
verify.sh                      run the self-verifying claims harness
gf                             unified CLI (relay, clean, providers, verify)
SKILL.md                       portable skill body (agent-agnostic)
assets/logo.jpg               project logo
adapters/                      per-agent always-on rule text
scripts/                       relay, resolver, payloads, MCP, canary, scoring
references/framing-toolkit.md  completion/continuation/dual-use frames
references/jailbreak-templates/  per-family payloads (L1B3RT4S corpus)
references/system-prompts/     published agent system prompts
references/refusal-detection.md    full pattern list

Curated templates with worked examples: `references/jailbreak-templates.md`.
"""

CLAIMS = [
    {
        "id": "agent_coverage",
        "text": README_WRITES_TABLE,
        "check": "every_adapter_exists",
        "kind": "static",
    },
    {
        "id": "install_paths",
        "text": README_INSTALL_BLOCK,
        "check": "every_agent_installable",
        "kind": "runtime",
    },
    {
        "id": "uninstall_paths",
        "text": "Removes the marker blocks and copied files. Backups (`*.bak.godmode`) are kept.",
        "check": "every_agent_uninstalls",
        "kind": "runtime",
    },
    {
        "id": "shared_agents_md",
        "text": "Every write is marker-delimited and per-agent (`<!-- BEGIN GODMODE-PORTABLE:codex -->`), so several agents can share one `AGENTS.md` without overwriting each other.",
        "check": "shared_agents_md",
        "kind": "runtime",
    },
    {
        "id": "existing_content",
        "text": "Your existing `CLAUDE.md` / `AGENTS.md` content is preserved, and the first change takes a `.bak.godmode` backup.",
        "check": "existing_content_preserved",
        "kind": "runtime",
    },
    {
        "id": "reference_files_exist",
        "text": "Curated templates with worked examples: `references/jailbreak-templates.md`.",
        "check": "every_reference_file_exists",
        "kind": "static",
    },
    {
        "id": "runtime_link",
        "text": "Removes the marker blocks and copied files. Backups (`*.bak.godmode`) are kept.",
        "check": "runtime_dir_linked",
        "kind": "runtime",
    },
    {
        "id": "logo_present",
        "text": "assets/logo.jpg               project logo",
        "check": "logo_present",
        "kind": "static",
    },
    {
        "id": "python_parses",
        "text": "All stdlib-only Python 3.9+. No pip install.",
        "check": "every_relay_script_parses",
        "kind": "static",
    },
    {
        "id": "stdlib_only",
        "text": "All stdlib-only Python 3.9+. No pip install.",
        "check": "scripts_stdlib_only",
        "kind": "static",
    },
    {
        "id": "shell_parses",
        "text": README_LAYOUT_BLOCK,
        "check": "every_shell_script_parses",
        "kind": "static",
    },
    {
        "id": "bootstrap_url",
        "text": "curl -fsSL https://raw.githubusercontent.com/Rafix4x/godfather/main/bootstrap.sh | bash",
        "check": "bootstrap_downloads",
        "kind": "runtime",
    },
    {
        "id": "provider_agnostic",
        "text": "No provider is hardcoded, so this works with whatever you already pay for.",
        "check": "no_provider_hardcode",
        "kind": "static",
    },
    {
        "id": "relay_help",
        "text": 'python3 ~/.godmode/scripts/relay.py "your request"',
        "check": "relay_help_works",
        "kind": "runtime",
    },
    {
        "id": "provider_resolve",
        "text": "python3 ~/.godmode/scripts/provider_resolve.py",
        "check": "provider_resolve_runs",
        "kind": "runtime",
    },
]

PROVIDER_HOSTS = {
    "openrouter.ai": "OPENROUTER",
    "api.openai.com": "OPENAI",
    "api.anthropic.com": "ANTHROPIC",
    "generativelanguage.googleapis.com": "GEMINI",
    "aiplatform.googleapis.com": "GEMINI",
    "api.deepseek.com": "DEEPSEEK",
    "api.groq.com": "GROQ",
    "api.mistral.ai": "MISTRAL",
    "api.x.ai": "XAI",
    "api.together.xyz": "TOGETHER",
    "api.cohere.com": "COHERE",
    "api.fireworks.ai": "FIREWORKS",
    "api.perplexity.ai": "PERPLEXITY",
}

STDLIB_FALLBACK = {
    "abc", "argparse", "ast", "asyncio", "base64", "binascii", "bisect",
    "calendar", "cmath", "collections", "colorsys", "concurrent", "configparser",
    "contextlib", "copy", "csv", "ctypes", "dataclasses", "datetime", "decimal",
    "difflib", "dis", "email", "enum", "errno", "faulthandler", "filecmp",
    "fileinput", "fnmatch", "fractions", "ftplib", "functools", "gc", "getopt",
    "getpass", "gettext", "glob", "gzip", "hashlib", "heapq", "hmac", "html",
    "http", "imaplib", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "linecache", "locale", "logging", "lzma", "mailbox",
    "marshal", "math", "mimetypes", "mmap", "multiprocessing", "netrc",
    "numbers", "operator", "os", "pathlib", "pdb", "pickle", "pkgutil",
    "platform", "plistlib", "poplib", "pprint", "profile", "pty", "pwd",
    "py_compile", "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select", "selectors",
    "shelve", "shlex", "shutil", "signal", "site", "smtplib", "socket",
    "socketserver", "sqlite3", "ssl", "stat", "statistics", "string",
    "stringprep", "struct", "subprocess", "symtable", "sys", "sysconfig",
    "tarfile", "tempfile", "termios", "textwrap", "threading", "time",
    "timeit", "tkinter", "token", "tokenize", "traceback", "tracemalloc",
    "types", "typing", "unicodedata", "unittest", "urllib", "uu", "uuid",
    "venv", "warnings", "wave", "weakref", "webbrowser", "xml", "xmlrpc",
    "zipfile", "zipimport", "zlib",
}

TOKEN_RE = re.compile(r"`([^`]+)`")
PATH_TOKEN_RE = re.compile(r"^[~\w./-]+$")


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def normalize_ws(text):
    return " ".join(text.split())


def run_command(argv, cwd=REPO_ROOT):
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss" % RUN_TIMEOUT
    except OSError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def parse_all_agents(install_src):
    match = re.search(r"^ALL_AGENTS=\(([^)]*)\)", install_src, re.MULTILINE)
    if not match:
        return []
    return match.group(1).split()


def parse_writes_table(readme):
    if "## What it writes" not in readme:
        return []
    body = readme.split("## What it writes", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 3:
            continue
        if cells[0].startswith(":") or cells[0] == "Agent":
            continue
        rows.append({"label": cells[0], "global": cells[1], "project": cells[2]})
    return rows


def path_tokens(cell):
    tokens = []
    for token in TOKEN_RE.findall(cell):
        token = token.strip()
        if token.endswith(":"):
            continue
        if not PATH_TOKEN_RE.match(token):
            continue
        if "/" not in token and "." not in token:
            continue
        tokens.append(token)
    return tokens


def resolve_path(token, home, project):
    if token.startswith("~/"):
        return os.path.join(home, token[2:])
    if token.startswith("/"):
        return token
    return os.path.join(project, token)


def row_for_agent(rows, agent):
    for row in rows:
        matches = matching_agents(row["label"], agent)
        if matches == [agent]:
            return row
    return None


def matching_agents(label, agent):
    normalized = re.sub(r"[^a-z0-9]", "", label.lower())
    matches = []
    for candidate in agent_ids():
        if re.sub(r"[^a-z0-9]", "", candidate.lower()) in normalized:
            matches.append(candidate)
    return matches


_AGENT_CACHE = []


def agent_ids():
    if not _AGENT_CACHE:
        _AGENT_CACHE.extend(parse_all_agents(read_text(INSTALL_SH)))
    return _AGENT_CACHE


def extract_section(output, name):
    lines = output.splitlines()
    inside = False
    collected = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            inside = stripped[1:-1] == name
            continue
        if inside:
            collected.append(stripped)
    return "\n".join(collected)


def parse_install_artifacts(output):
    artifacts = {"copied": [], "blocks": [], "configs": []}
    for line in output.splitlines():
        stripped = line.strip()
        match = re.match(r"^created (.+) with read: (.+)$", stripped)
        if match:
            artifacts["configs"].append((match.group(1), match.group(2)))
            continue
        match = re.match(r"^created (.+) \[(.+)\]$", stripped)
        if match:
            artifacts["blocks"].append(match.group(1))
            continue
        match = re.match(r"^(?:updated|appended) block \[.+\] (?:in|->) (.+)$", stripped)
        if match:
            artifacts["blocks"].append(match.group(1))
            continue
        match = re.match(r"^copied\s+-> (.+)$", stripped)
        if match:
            dest = match.group(1)
            if dest.endswith("/*.py"):
                dest = dest[: -len("/*.py")]
            artifacts["copied"].append(dest)
    return artifacts


def check_every_adapter_exists(claim):
    """Every agent in the README table has an adapter, an installer and a slot in ALL_AGENTS."""
    readme = read_text(README_PATH)
    install_src = read_text(INSTALL_SH)
    agents = parse_all_agents(install_src)
    rows = parse_writes_table(readme)
    if not rows:
        return False, "no agent rows found under '## What it writes'"
    if not agents:
        return False, "ALL_AGENTS not found in install.sh"
    problems = []
    documented = set()
    for row in rows:
        matches = [a for a in agents
                   if re.sub(r"[^a-z0-9]", "", a.lower())
                   in re.sub(r"[^a-z0-9]", "", row["label"].lower())]
        if not matches:
            if row["label"].lower() == "core":
                if not re.search(r"^install_core\(\)", install_src, re.MULTILINE):
                    problems.append("core: install_core() missing from install.sh")
                continue
            problems.append("%s: no agent in ALL_AGENTS matches this row" % row["label"])
            continue
        if len(matches) > 1:
            problems.append("%s: matches several agents (%s)" % (row["label"], ", ".join(matches)))
            continue
        agent = matches[0]
        documented.add(agent)
        adapter = os.path.join(ADAPTERS_DIR, agent + ".md")
        if not os.path.isfile(adapter):
            problems.append("%s: adapters/%s.md missing" % (agent, agent))
        func = "install_%s" % agent.replace("-", "_")
        if not re.search(r"^%s\(\)" % re.escape(func), install_src, re.MULTILINE):
            problems.append("%s: %s() missing from install.sh" % (agent, func))
    for agent in agents:
        if agent not in documented:
            problems.append("%s: installed by install.sh but not in the README table" % agent)
    if problems:
        return False, "; ".join(problems)
    return True, ("%d agents documented, adapters + install functions + ALL_AGENTS in sync"
                  % len(documented))


def check_every_agent_installable(claim):
    """A dry run plans every path the README promises for every agent."""
    readme = read_text(README_PATH)
    install_src = read_text(INSTALL_SH)
    agents = parse_all_agents(install_src)
    rows = parse_writes_table(readme)
    problems = []
    checked = 0
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        project = os.path.join(tmp, "project")
        os.makedirs(home)
        os.makedirs(project)
        for agent in agents:
            code, out, err = run_command([
                "bash", INSTALL_SH, "--dry-run", "--no-detect", "--agents", agent,
                "--target-home", home, "--project", project,
            ])
            if code != 0:
                problems.append("%s: dry run exited %d (%s)" % (agent, code, err.strip()[:120]))
                continue
            row = row_for_agent(rows, agent)
            if row is None:
                problems.append("%s: no row in the README 'What it writes' table" % agent)
                continue
            section = extract_section(out, agent)
            if not section:
                problems.append("%s: dry run produced no [%s] section" % (agent, agent))
                continue
            for cell in (row["global"], row["project"]):
                for token in path_tokens(cell):
                    planned = resolve_path(token, home, project).rstrip("/")
                    if planned not in section:
                        problems.append("%s: %s not planned by the dry run" % (agent, token))
                    else:
                        checked += 1
        core_row = None
        for row in rows:
            if row["label"].lower() == "core":
                core_row = row
        if core_row is None:
            problems.append("core: no row in the README 'What it writes' table")
        else:
            code, out, err = run_command([
                "bash", INSTALL_SH, "--dry-run", "--no-detect",
                "--target-home", home, "--project", project,
            ])
            section = extract_section(out, "core")
            if code != 0 or not section:
                problems.append("core: dry run produced no [core] section")
            else:
                for cell in (core_row["global"], core_row["project"]):
                    for token in path_tokens(cell):
                        planned = resolve_path(token, home, project).rstrip("/")
                        if planned not in section:
                            problems.append("core: %s not planned by the dry run" % token)
                        else:
                            checked += 1
    if problems:
        return False, "; ".join(problems)
    return True, "%d documented paths planned across %d agents" % (checked, len(agents))


def check_every_agent_uninstalls(claim):
    """A real install followed by --uninstall leaves nothing behind."""
    install_src = read_text(INSTALL_SH)
    agents = parse_all_agents(install_src)
    problems = []
    removed = 0
    for agent in agents:
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home")
            project = os.path.join(tmp, "project")
            os.makedirs(home)
            os.makedirs(project)
            code, out, err = run_command([
                "bash", INSTALL_SH, "--no-detect", "--agents", agent,
                "--target-home", home, "--project", project,
            ])
            if code != 0:
                problems.append("%s: install exited %d (%s)" % (agent, code, err.strip()[:120]))
                continue
            artifacts = parse_install_artifacts(out)
            code, out, err = run_command([
                "bash", INSTALL_SH, "--uninstall", "--agents", agent,
                "--target-home", home, "--project", project,
            ])
            if code != 0:
                problems.append("%s: uninstall exited %d (%s)" % (agent, code, err.strip()[:120]))
                continue
            for path in artifacts["copied"]:
                if os.path.exists(path):
                    problems.append("%s: %s still present after uninstall" % (agent, path))
                else:
                    removed += 1
            for path in artifacts["blocks"]:
                if os.path.exists(path):
                    problems.append("%s: %s still present after uninstall" % (agent, path))
                else:
                    removed += 1
            for path, token in artifacts["configs"]:
                if os.path.exists(path) and token in read_text(path):
                    problems.append("%s: %s still references %s" % (agent, path, token))
                else:
                    removed += 1
    if problems:
        return False, "; ".join(problems)
    return True, "%d installed artifacts removed across %d agents" % (removed, len(agents))


def check_shared_agents_md(claim):
    """Two agents can share one AGENTS.md; uninstalling one keeps the other."""
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        project = os.path.join(tmp, "project")
        os.makedirs(home)
        os.makedirs(project)
        agents_md = os.path.join(project, "AGENTS.md")
        with open(agents_md, "w", encoding="utf-8") as fh:
            fh.write("# Shared project notes\n")
        code, out, err = run_command([
            "bash", INSTALL_SH, "--no-detect", "--agents", "codex,openclaw",
            "--target-home", home, "--project", project,
        ])
        if code != 0:
            return False, "install exited %d (%s)" % (code, err.strip()[:160])
        content = read_text(agents_md)
        problems = []
        for agent in ("codex", "openclaw"):
            if "BEGIN GODMODE-PORTABLE:%s" % agent not in content:
                problems.append("%s block missing from the shared AGENTS.md" % agent)
        if "# Shared project notes" not in content:
            problems.append("pre-existing content was dropped from AGENTS.md")
        code, out, err = run_command([
            "bash", INSTALL_SH, "--uninstall", "--agents", "codex",
            "--target-home", home, "--project", project,
        ])
        if code != 0:
            return False, "uninstall exited %d (%s)" % (code, err.strip()[:160])
        if not os.path.exists(agents_md):
            return False, "AGENTS.md was deleted while another agent's block was still installed"
        content = read_text(agents_md)
        if "BEGIN GODMODE-PORTABLE:codex" in content:
            problems.append("codex block survived its own uninstall")
        if "BEGIN GODMODE-PORTABLE:openclaw" not in content:
            problems.append("openclaw block was destroyed by the codex uninstall")
        if "# Shared project notes" not in content:
            problems.append("pre-existing content was dropped by the uninstall")
        if problems:
            return False, "; ".join(problems)
        return True, "codex and openclaw coexist in one AGENTS.md, each uninstalls cleanly"


def check_existing_content_preserved(claim):
    """Existing CLAUDE.md content survives install and uninstall, with a backup kept."""
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        project = os.path.join(tmp, "project")
        os.makedirs(home)
        os.makedirs(project)
        claude_md = os.path.join(project, "CLAUDE.md")
        original = "# House rules\n\nAlways run the tests.\n"
        with open(claude_md, "w", encoding="utf-8") as fh:
            fh.write(original)
        code, out, err = run_command([
            "bash", INSTALL_SH, "--no-detect", "--agents", "claude-code",
            "--target-home", home, "--project", project,
        ])
        if code != 0:
            return False, "install exited %d (%s)" % (code, err.strip()[:160])
        problems = []
        content = read_text(claude_md)
        if original.strip() not in content:
            problems.append("pre-existing content missing after install")
        if "BEGIN GODMODE-PORTABLE:claude-code" not in content:
            problems.append("marker block missing after install")
        backup = claude_md + ".bak.godmode"
        if not os.path.isfile(backup):
            problems.append("no .bak.godmode backup was written")
        elif read_text(backup) != original:
            problems.append(".bak.godmode backup does not hold the original content")
        code, out, err = run_command([
            "bash", INSTALL_SH, "--uninstall", "--agents", "claude-code",
            "--target-home", home, "--project", project,
        ])
        if code != 0:
            return False, "uninstall exited %d (%s)" % (code, err.strip()[:160])
        if not os.path.exists(claude_md):
            return False, "CLAUDE.md was deleted by the uninstall"
        content = read_text(claude_md)
        if original.strip() not in content:
            problems.append("pre-existing content lost after uninstall")
        if "GODMODE-PORTABLE" in content:
            problems.append("marker block survived the uninstall")
        if not os.path.isfile(backup):
            problems.append("backup was removed by the uninstall")
        if problems:
            return False, "; ".join(problems)
        return True, "existing CLAUDE.md preserved, backup written, block removed on uninstall"


def python_sources():
    if not os.path.isdir(SCRIPTS_DIR):
        return []
    return sorted(
        os.path.join(SCRIPTS_DIR, name)
        for name in os.listdir(SCRIPTS_DIR)
        if name.endswith(".py") and os.path.isfile(os.path.join(SCRIPTS_DIR, name))
    )


def check_every_reference_file_exists(claim):
    wanted = [
        "references/framing-toolkit.md",
        "references/jailbreak-templates.md",
        "references/refusal-detection.md",
        "references/jailbreak-templates",
        "references/system-prompts",
    ]
    problems = []
    for rel in wanted:
        path = os.path.join(REPO_ROOT, rel)
        if os.path.isdir(path):
            entries = [e for e in os.listdir(path) if e.endswith((".md", ".txt"))]
            if not entries:
                problems.append("%s is empty" % rel)
        elif not os.path.isfile(path):
            problems.append("%s is missing" % rel)
    if problems:
        return False, "; ".join(problems)
    return True, "%d reference paths present" % len(wanted)


def check_logo_present(claim):
    path = os.path.join(REPO_ROOT, "assets", "logo.jpg")
    if not os.path.isfile(path):
        return False, "assets/logo.jpg is missing"
    size = os.path.getsize(path)
    if size < 2000:
        return False, "assets/logo.jpg is only %d bytes" % size
    readme = read_text(README_PATH)
    if "assets/logo.jpg" not in readme:
        return False, "the README does not reference assets/logo.jpg"
    return True, "assets/logo.jpg present (%d bytes) and referenced" % size


def check_runtime_dir_linked(claim):
    home = tempfile.mkdtemp(prefix="gf_link_")
    project = tempfile.mkdtemp(prefix="gf_link_proj_")
    try:
        run_command(["bash", INSTALL_SH, "--no-detect",
                     "--target-home", home, "--project", project])
        link = os.path.join(home, ".godfather")
        if not os.path.islink(link):
            return False, "%s is not a link to the runtime directory" % link
        relay = os.path.join(link, "scripts", "relay.py")
        if not os.path.isfile(relay):
            return False, "%s does not resolve" % relay
        run_command(["bash", INSTALL_SH, "--uninstall", "--no-detect",
                     "--target-home", home, "--project", project])
        if os.path.exists(link) or os.path.islink(link):
            return False, "%s survived the uninstall" % link
        return True, "runtime directory linked and unlinked cleanly"
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(project, ignore_errors=True)


def check_every_relay_script_parses(claim):
    """Every shipped Python script parses."""
    sources = python_sources()
    if not sources:
        return False, "no Python scripts found in scripts/"
    problems = []
    for path in sources:
        try:
            ast.parse(read_text(path), filename=path)
        except SyntaxError as exc:
            problems.append("%s: %s" % (os.path.basename(path), exc))
    if problems:
        return False, "; ".join(problems)
    return True, "%d Python scripts parse cleanly" % len(sources)


def stdlib_module_names():
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return set(names)
    return set(STDLIB_FALLBACK)


def project_module_names():
    names = {os.path.splitext(os.path.basename(p))[0] for p in python_sources()}
    names.update({"provider_resolve", "refusal_scan", "agent_prompts",
                  "parseltongue", "godmode_check"})
    return names


def check_scripts_stdlib_only(claim):
    """No script needs a third-party package to import."""
    sources = python_sources()
    if not sources:
        return False, "no Python scripts found in scripts/"
    stdlib = stdlib_module_names()
    local = project_module_names()
    required = []
    optional = []
    for path in sources:
        try:
            tree = ast.parse(read_text(path), filename=path)
        except SyntaxError as exc:
            return False, "%s: %s" % (os.path.basename(path), exc)
        guarded = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for child in ast.walk(node):
                    if isinstance(child, (ast.Import, ast.ImportFrom)):
                        guarded.add(id(child))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.ImportFrom) and node.level:
                continue
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            else:
                modules = [node.module or ""]
            for module in modules:
                root = module.split(".")[0]
                if not root or root in stdlib or root in local:
                    continue
                entry = "%s: %s" % (os.path.basename(path), module)
                if id(node) in guarded:
                    optional.append(entry)
                else:
                    required.append(entry)
    if required:
        return False, "third-party imports required at runtime: " + ", ".join(sorted(set(required)))
    detail = "%d scripts import stdlib + project modules only" % len(sources)
    if optional:
        detail += "; optional extras: " + ", ".join(sorted(set(optional)))
    return True, detail


def shell_script_paths():
    paths = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "assets")]
        for name in files:
            if name.endswith(".sh"):
                paths.append(os.path.join(root, name))
    for name in sorted(os.listdir(REPO_ROOT)):
        path = os.path.join(REPO_ROOT, name)
        if not os.path.isfile(path) or path in paths:
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                first = fh.readline()
        except OSError:
            continue
        if first.startswith("#!") and "sh" in first:
            paths.append(path)
    return sorted(paths)


def check_every_shell_script_parses(claim):
    """Every shell script is syntactically valid bash."""
    if shutil.which("bash") is None:
        return None, "bash is not installed, shell syntax cannot be checked"
    paths = shell_script_paths()
    if not paths:
        return False, "no shell scripts found"
    problems = []
    for path in paths:
        code, out, err = run_command(["bash", "-n", path])
        if code != 0:
            problems.append("%s: %s" % (os.path.relpath(path, REPO_ROOT), err.strip()[:160]))
    if problems:
        return False, "; ".join(problems)
    return True, "%d shell scripts pass bash -n" % len(paths)


def check_bootstrap_downloads(claim):
    """The published bootstrap.sh URL answers with HTTP 200."""
    readme = read_text(README_PATH)
    match = re.search(r"https://raw\.githubusercontent\.com/[^\s\"'|)]+", readme)
    if not match:
        return False, "no raw.githubusercontent.com URL found in README.md"
    url = match.group(0)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False, "malformed bootstrap URL: %s" % url
    request = urllib.request.Request(url, headers={"User-Agent": "godfather-verify-claims"})
    try:
        with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT) as response:
            status = response.getcode()
            body = response.read(4096)
    except urllib.error.HTTPError as exc:
        return False, "%s returned HTTP %d" % (url, exc.code)
    except (urllib.error.URLError, OSError) as exc:
        return None, "network unavailable (%s); %s not checked" % (exc, url)
    if status != 200:
        return False, "%s returned HTTP %d" % (url, status)
    if b"GODFATHER_REPO" not in body and b"godfather" not in body.lower():
        return False, "%s returned 200 but the body is not the bootstrap script" % url
    return True, "%s returned HTTP 200 (%d bytes read)" % (url, len(body))


def check_no_provider_hardcode(claim):
    """The relay path contains no provider hostname of its own."""
    targets = [
        os.path.join(SCRIPTS_DIR, "relay.py"),
        os.path.join(SCRIPTS_DIR, "provider_resolve.py"),
    ]
    problems = []
    for path in targets:
        if not os.path.isfile(path):
            problems.append("%s missing" % os.path.basename(path))
            continue
        text = read_text(path)
        name = os.path.basename(path)
        for host, env_prefix in PROVIDER_HOSTS.items():
            if host not in text:
                continue
            if name == "provider_resolve.py" and env_prefix in text:
                continue
            problems.append("%s hardcodes %s" % (name, host))
    if problems:
        return False, "; ".join(problems)
    return True, "relay.py and provider_resolve.py carry no provider hostname of their own"


def check_relay_help_works(claim):
    """relay.py --help runs and exits zero."""
    script = os.path.join(SCRIPTS_DIR, "relay.py")
    if not os.path.isfile(script):
        return False, "scripts/relay.py missing"
    code, out, err = run_command([sys.executable, script, "--help"], cwd=SCRIPTS_DIR)
    if code != 0:
        return False, "relay.py --help exited %d (%s)" % (code, err.strip()[:160])
    if "--frame" not in out:
        return False, "relay.py --help does not document --frame"
    return True, "relay.py --help exits 0 and documents its flags"


def check_provider_resolve_runs(claim):
    """provider_resolve.py runs and reports its result without crashing."""
    script = os.path.join(SCRIPTS_DIR, "provider_resolve.py")
    if not os.path.isfile(script):
        return False, "scripts/provider_resolve.py missing"
    code, out, err = run_command([sys.executable, script, "--json"], cwd=SCRIPTS_DIR)
    if "Traceback (most recent call last)" in err:
        return False, "provider_resolve.py crashed: %s" % err.strip()[-200:]
    if code == 0:
        try:
            payload = json.loads(out)
        except ValueError as exc:
            return False, "provider_resolve.py --json printed invalid JSON (%s)" % exc
        if not isinstance(payload, list):
            return False, "provider_resolve.py --json did not print a list"
        return True, "provider_resolve.py --json exited 0 with %d provider(s)" % len(payload)
    if code == 1 and "no provider found" in err.lower():
        return True, "provider_resolve.py --json exited 1 with the documented no-provider message"
    return False, "provider_resolve.py --json exited %d (%s)" % (code, err.strip()[:200])


CHECKS = {
    "every_adapter_exists": check_every_adapter_exists,
    "every_agent_installable": check_every_agent_installable,
    "every_agent_uninstalls": check_every_agent_uninstalls,
    "shared_agents_md": check_shared_agents_md,
    "existing_content_preserved": check_existing_content_preserved,
    "every_relay_script_parses": check_every_relay_script_parses,
    "scripts_stdlib_only": check_scripts_stdlib_only,
    "every_shell_script_parses": check_every_shell_script_parses,
    "bootstrap_downloads": check_bootstrap_downloads,
    "no_provider_hardcode": check_no_provider_hardcode,
    "relay_help_works": check_relay_help_works,
    "provider_resolve_runs": check_provider_resolve_runs,
    "every_reference_file_exists": check_every_reference_file_exists,
    "runtime_dir_linked": check_runtime_dir_linked,
    "logo_present": check_logo_present,
}


def claim_text_present(claim, readme):
    return normalize_ws(claim["text"]) in normalize_ws(readme)


def run_claim(claim):
    text_ok = claim_text_present(claim, read_text(README_PATH))
    checker = CHECKS.get(claim["check"])
    if checker is None:
        return "FAIL", "unknown checker %s" % claim["check"]
    if not text_ok:
        return "FAIL", "claim text is no longer in README.md"
    result = checker(claim)
    if result is None:
        return "SKIP", ""
    ok, detail = result
    if ok is None:
        return "SKIP", detail
    return ("PASS" if ok else "FAIL"), detail


def print_table(results):
    id_width = max(len("ID"), max(len(r["id"]) for r in results))
    kind_width = max(len("KIND"), max(len(r["kind"]) for r in results))
    header = "%-*s  %-*s  %-6s  %s" % (id_width, "ID", kind_width, "KIND", "STATUS", "DETAIL")
    print(header)
    print("%-*s  %-*s  %-6s  %s" % (id_width, "-" * id_width, kind_width, "-" * kind_width,
                                    "-" * 6, "-" * 60))
    for result in results:
        print("%-*s  %-*s  %-6s  %s" % (id_width, result["id"], kind_width,
                                        result["kind"], result["status"], result["detail"]))
        if result["detail"] and len(result["detail"]) > 60:
            wrapped = textwrap.wrap(result["detail"], width=100,
                                    initial_indent="", subsequent_indent=" " * (id_width + 2 + kind_width + 2 + 8))
            for line in wrapped[1:]:
                print(line)


def print_list(claims):
    for claim in claims:
        print("%s [%s]" % (claim["id"], claim["kind"]))
        for line in claim["text"].strip("\n").splitlines():
            print("    %s" % line)
        print("")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify every factual claim in README.md")
    parser.add_argument("--list", action="store_true",
                        help="print the claim ids and their README text, then exit")
    parser.add_argument("--json", action="store_true",
                        help="print the results as JSON")
    parser.add_argument("--only", default=None,
                        help="run only the claim with this id")
    args = parser.parse_args(argv)

    claims = CLAIMS
    if args.only:
        claims = [c for c in claims if c["id"] == args.only]
        if not claims:
            print("no claim with id %s" % args.only, file=sys.stderr)
            return 2

    if args.list:
        print_list(claims)
        return 0

    results = []
    for claim in claims:
        status, detail = run_claim(claim)
        results.append({
            "id": claim["id"],
            "kind": claim["kind"],
            "check": claim["check"],
            "text": claim["text"].strip(),
            "status": status,
            "detail": detail,
        })

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    skipped = sum(1 for r in results if r["status"] == "SKIP")

    if args.json:
        print(json.dumps({
            "ok": failed == 0,
            "verified": passed,
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "claims": results,
        }, indent=2))
    else:
        print_table(results)
        print("")
        summary = "%d/%d claims verified" % (passed, len(results))
        if skipped:
            summary += " (%d skipped)" % skipped
        print(summary)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
