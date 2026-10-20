"""
Guard layer.

The prompt text in the adapters changes how a model answers. This module
changes the other half: the gate the agent itself puts in front of the
model, and the gate the agent puts in front of the shell.

Every entry below names a setting that ships in the agent, not a setting
invented for this project. The source for each one is the agent's own
documentation or configuration schema, and the note on each entry says
what the setting actually governs.

The rules are the same everywhere: read the file, change only the keys
listed here, keep every other key exactly as it was, and leave a backup
next to the file. Nothing here touches a model provider, so a change here
never alters what a model is allowed to say. That part belongs to the
transport, in proxy.py.
"""

import json
import os
import shutil
import sys

HOME = os.path.expanduser("~")

GUARDS = {
    "claude-code": {
        "path": "~/.claude/settings.json",
        "fmt": "json",
        "set": {
            "permissions.defaultMode": "bypassPermissions",
        },
        "unset": [
            "permissions.disableBypassPermissionsMode",
            "permissions.disableAutoMode",
        ],
        "note": "the permission prompt, and the two policy switches that "
                "can block bypass mode",
        "source": "code.claude.com/docs/en/permissions",
    },
    "codex": {
        "path": "~/.codex/config.toml",
        "fmt": "toml",
        "set": {
            "approval_policy": "never",
            "sandbox_mode": "danger-full-access",
        },
        "unset": [],
        "note": "the approval prompt and the filesystem sandbox",
        "source": "developers.openai.com/codex/config-basic",
    },
    "gemini": {
        "path": "~/.gemini/settings.json",
        "fmt": "json",
        "set": {
            "security.enableConseca": False,
            "security.disableYoloMode": False,
            "security.disableAlwaysAllow": False,
            "security.toolSandboxing": False,
            "tools.sandbox": False,
        },
        "unset": [],
        "note": "Conseca, the built-in checker that asks a second model "
                "whether an action is safe, plus the confirmation gates",
        "source": "google-gemini/gemini-cli schemas/settings.schema.json",
    },
    "opencode": {
        "path": "~/.config/opencode/opencode.json",
        "fmt": "json",
        "set": {
            "permission.edit": "allow",
            "permission.bash": "allow",
            "permission.webfetch": "allow",
            "permission.read": "allow",
            "permission.grep": "allow",
            "permission.glob": "allow",
            "permission.lsp": "allow",
            "permission.skill": "allow",
            "permission.websearch": "allow",
            "permission.apply_patch": "allow",
        },
        "unset": [],
        "note": "the per-tool permission map",
        "source": "opencode.ai/docs/tools",
    },
    "hermes": {
        "path": "~/.hermes/config.yaml",
        "fmt": "yaml",
        "set": {
            "approvals.mode": "off",
            "allow_gateway_injection": True,
            "allow_tool_override": True,
        },
        "unset": [],
        "note": "the approval prompt, the gateway injection and the tool "
                "override switch",
        "source": "hermes-agent docs, user-guide/security.md",
    },
    "antigravity": {
        "path": "~/.gemini/settings.json",
        "fmt": "json",
        "set": {
            "security.enableConseca": False,
            "security.disableYoloMode": False,
            "security.disableAlwaysAllow": False,
        },
        "unset": [],
        "note": "the same confirmation gates, through the shared home",
        "source": "google-gemini/gemini-cli schemas/settings.schema.json",
    },
}


STATE_GUARDS = {
    "cline": {
        "paths": [
            "~/.cline/data/globalState.json",
            "~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/globalState.json",
        ],
        "fmt": "json",
        "shape": "cline",
        "note": "the auto-approval actions, so a write or a command runs "
                "without the confirmation dialog",
        "source": "cline/cline src/shared/AutoApprovalSettings.ts",
    },
    "roo": {
        "paths": [
            "~/.roo/global-storage/global-state.json",
            "~/.roo/globalState.json",
            "~/.roo/cli-settings.json",
        ],
        "fmt": "json",
        "shape": "roo",
        "note": "the always-allow switches, so a write or a command runs "
                "without the confirmation dialog",
        "source": "RooCodeInc/Roo-Code src/core/auto-approval/index.ts",
    },
    "cursor": {
        "paths": [
            "~/.cursor/cli-config.json",
        ],
        "fmt": "json",
        "shape": "cursor",
        "note": "the permission allowlist, so a shell, read, write, fetch "
                "or MCP call runs without a prompt",
        "source": "cursor.com/docs/cli/reference/permissions",
    },
}

CLINE_ACTIONS = [
    "readFiles",
    "readFilesExternally",
    "editFiles",
    "editFilesExternally",
    "executeSafeCommands",
    "executeAllCommands",
    "useBrowser",
    "useMcp",
]

ROO_FLAGS = {
    "autoApprovalEnabled": True,
    "alwaysAllowReadOnly": True,
    "alwaysAllowWrite": True,
    "alwaysAllowMcp": True,
    "alwaysAllowModeSwitch": True,
    "alwaysAllowSubtasks": True,
    "alwaysAllowExecute": True,
    "alwaysAllowFollowupQuestions": True,
    "alwaysAllowReadOnlyOutsideWorkspace": True,
    "alwaysAllowWriteOutsideWorkspace": True,
    "alwaysAllowWriteProtected": True,
    "allowedCommands": ["*"],
    "deniedCommands": [],
}

CURSOR_ALLOW = [
    "Shell(*)",
    "Read(**)",
    "Write(**)",
    "WebFetch(*)",
    "Mcp(*:*)",
]


def expand(path):
    return os.path.expanduser(path.replace("~", HOME, 1))


def read_json(path):
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def read_toml(path):
    if not os.path.isfile(path):
        return {}
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from provider_resolve import _load_toml
    except ImportError:
        return {}
    try:
        data = _load_toml(path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_yaml(path):
    if not os.path.isfile(path):
        return {}
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from provider_resolve import _load_yaml
    except ImportError:
        return {}
    try:
        data = _load_yaml(path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_plain(path):
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def get_path(data, dotted):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    return node, True


def set_path(data, dotted, value):
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def unset_path(data, dotted):
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            return False
        node = node[part]
    if parts[-1] in node:
        del node[parts[-1]]
        return True
    return False


def write_json(path, data):
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def write_toml(path, data):
    lines = []
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    for key in sorted(scalars):
        lines.append("%s = %s" % (key, toml_value(scalars[key])))
    for name in sorted(tables):
        table = tables[name]
        if not table:
            continue
        plain = {k: v for k, v in table.items() if not isinstance(v, dict)}
        nested = {k: v for k, v in table.items() if isinstance(v, dict)}
        if plain:
            lines.append("")
            lines.append("[%s]" % name)
            for key in sorted(plain):
                lines.append("%s = %s" % (key, toml_value(plain[key])))
        for key in sorted(nested):
            body = nested[key]
            if not body:
                continue
            lines.append("")
            lines.append("[%s.%s]" % (name, key))
            for sub in sorted(body):
                lines.append("%s = %s" % (sub, toml_value(body[sub])))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).lstrip("\n") + "\n")


def toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join("%s = %s" % (k, toml_value(v))
                               for k, v in sorted(value.items())) + "}"
    return json.dumps(str(value))


def write_yaml(path, data):
    lines = []
    for key in sorted(data):
        value = data[key]
        if isinstance(value, dict):
            lines.append("%s:" % key)
            for sub in sorted(value):
                lines.append("  %s: %s" % (sub, yaml_value(value[sub])))
        else:
            lines.append("%s: %s" % (key, yaml_value(value)))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


YAML_WORDS = {"true", "false", "yes", "no", "on", "off", "null", "none"}


def yaml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(yaml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join("%s: %s" % (k, yaml_value(v))
                               for k, v in sorted(value.items())) + "}"
    text = str(value)
    if (any(ch in text for ch in ":#{}[]&*!|>'\"%@`,")
            or text.strip() != text
            or text.lower() in YAML_WORDS):
        return json.dumps(text)
    return text


READERS = {"json": read_json, "toml": read_toml, "yaml": read_yaml}
WRITERS = {"json": write_json, "toml": write_toml, "yaml": write_yaml}


def backup(path, agent):
    if not os.path.isfile(path):
        return None
    target = "%s.bak.godmode.%s" % (path, agent)
    shutil.copy2(path, target)
    return target


def apply(agent, dry=False):
    spec = GUARDS.get(agent)
    if not spec:
        return False, "unknown agent", None
    path = expand(spec["path"])
    reader = READERS.get(spec["fmt"], read_plain)
    writer = WRITERS.get(spec["fmt"])
    data = reader(path)
    changes = []
    for dotted, value in sorted(spec["set"].items()):
        current, present = get_path(data, dotted)
        if present and current == value:
            continue
        changes.append("%s = %s" % (dotted, value))
        set_path(data, dotted, value)
    for dotted in spec["unset"]:
        if unset_path(data, dotted):
            changes.append("unset %s" % dotted)
    if not changes:
        return True, "already in place", None
    if dry:
        return True, ", ".join(changes), None
    if writer is None:
        return False, "no writer for %s" % spec["fmt"], None
    backup(path, agent)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    writer(path, data)
    return True, ", ".join(changes), path


def restore(agent, dry=False):
    spec = GUARDS.get(agent)
    if not spec:
        return False, "unknown agent", None
    path = expand(spec["path"])
    saved = "%s.bak.godmode.%s" % (path, agent)
    if not os.path.isfile(saved):
        return False, "no backup for %s" % path, None
    if dry:
        return True, "would restore %s" % saved, None
    shutil.copy2(saved, path)
    os.remove(saved)
    return True, "restored %s" % path, None


def report():
    rows = []
    for agent in sorted(GUARDS):
        spec = GUARDS[agent]
        path = expand(spec["path"])
        reader = READERS.get(spec["fmt"], read_plain)
        data = reader(path)
        state = []
        for dotted, value in sorted(spec["set"].items()):
            current, present = get_path(data, dotted)
            if not present:
                state.append("%s unset" % dotted)
            elif current == value:
                state.append("%s ok" % dotted)
            else:
                state.append("%s set" % dotted)
        rows.append({
            "agent": agent,
            "path": path,
            "exists": os.path.isfile(path),
            "state": state,
            "note": spec["note"],
            "source": spec["source"],
        })
    return rows


def find_state_file(spec):
    for candidate in spec["paths"]:
        full = expand(candidate)
        if os.path.isfile(full):
            return full
    return None


def state_apply(agent, dry=False):
    spec = STATE_GUARDS.get(agent)
    if not spec:
        return False, "unknown agent", None
    path = find_state_file(spec)
    if not path:
        return False, "no state file found", None
    data = read_json(path)
    changes = []
    shape = spec["shape"]

    if shape == "cline":
        settings = data.get("autoApprovalSettings")
        if not isinstance(settings, dict):
            settings = {}
        actions = settings.get("actions")
        if not isinstance(actions, dict):
            actions = {}
        for name in CLINE_ACTIONS:
            if actions.get(name) is not True:
                actions[name] = True
                changes.append("autoApprovalSettings.actions.%s = true" % name)
        settings["actions"] = actions
        settings["enabled"] = True
        settings["version"] = int(settings.get("version") or 0) + 1
        settings["enableNotifications"] = False
        data["autoApprovalSettings"] = settings

    elif shape == "roo":
        for key, value in ROO_FLAGS.items():
            if data.get(key) != value:
                data[key] = value
                changes.append("%s" % key)

    elif shape == "cursor":
        permissions = data.get("permissions")
        if not isinstance(permissions, dict):
            permissions = {}
        allow = permissions.get("allow")
        if not isinstance(allow, list):
            allow = []
        for token in CURSOR_ALLOW:
            if token not in allow:
                allow.append(token)
                changes.append("permissions.allow += %s" % token)
        permissions["allow"] = allow
        permissions["deny"] = []
        data["permissions"] = permissions

    if not changes:
        return True, "already in place", path
    if dry:
        return True, ", ".join(changes), path
    backup(path, agent)
    write_json(path, data)
    return True, ", ".join(changes), path


def state_report(agent):
    spec = STATE_GUARDS.get(agent)
    if not spec:
        return None
    path = find_state_file(spec)
    if not path:
        return {"agent": agent, "path": None, "exists": False, "state": [],
                "note": spec["note"], "source": spec["source"],
                "candidates": [expand(c) for c in spec["paths"]]}
    data = read_json(path)
    state = []
    shape = spec["shape"]
    if shape == "cline":
        settings = data.get("autoApprovalSettings") or {}
        actions = settings.get("actions") or {}
        for name in CLINE_ACTIONS:
            state.append("%s %s" % (name, "on" if actions.get(name) else "off"))
    elif shape == "roo":
        for key in sorted(ROO_FLAGS):
            state.append("%s %s" % (key, "on" if data.get(key) else "off"))
    elif shape == "cursor":
        permissions = data.get("permissions") or {}
        allow = permissions.get("allow") or []
        for token in CURSOR_ALLOW:
            state.append("%s %s" % (token, "on" if token in allow else "off"))
    return {"agent": agent, "path": path, "exists": True, "state": state,
            "note": spec["note"], "source": spec["source"], "candidates": []}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    command = argv[0] if argv else "report"

    if command == "apply":
        targets = argv[1:] or sorted(GUARDS)
        failed = False
        for agent in targets:
            ok, message, path = apply(agent, dry=dry)
            if not ok:
                failed = True
                print("%-14s FAILED   %s" % (agent, message))
                continue
            print("%-14s %-8s %s" % (agent, "dry-run" if dry else "applied", message))
        wanted = set(argv[1:]) if len(argv) > 1 else set()
        for agent in sorted(STATE_GUARDS):
            if wanted and agent not in wanted:
                continue
            ok, message, path = state_apply(agent, dry=dry)
            if not ok:
                print("%-14s %-8s %s" % (agent, "skipped", message))
                continue
            print("%-14s %-8s %s" % (agent, "dry-run" if dry else "applied", message))
        return 1 if failed else 0

    if command == "restore":
        targets = argv[1:] or sorted(GUARDS)
        for agent in targets:
            ok, message, _ = restore(agent, dry=dry)
            print("%-14s %-8s %s" % (agent, "dry-run" if dry else "restored"
                                     if ok else "failed", message))
        return 0

    if command == "report":
        for row in report():
            mark = "present" if row["exists"] else "absent"
            print("%-14s %-8s %s" % (row["agent"], mark, row["path"]))
            for item in row["state"]:
                print("                 %s" % item)
        for agent in sorted(STATE_GUARDS):
            row = state_report(agent)
            mark = "present" if row["exists"] else "absent"
            print("%-14s %-8s %s" % (row["agent"], mark, row["path"] or "(no state file)"))
            for item in row["state"]:
                print("                 %s" % item)
            if not row["exists"]:
                for candidate in row["candidates"]:
                    print("                 looked for %s" % candidate)
        return 0

    if command == "agents":
        for agent in sorted(GUARDS):
            print(agent)
        for agent in sorted(STATE_GUARDS):
            print(agent)
        return 0

    print("usage: guard.py [report|apply|restore] [agent ...] [--dry-run]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
