#!/usr/bin/env bash

set -uo pipefail

HERE="$(cd "${BASH_SOURCE[0]%/*}" 2>/dev/null && pwd)"
[[ -n "$HERE" && "$HERE" != "${BASH_SOURCE[0]}" ]] || HERE="$PWD"
ADAPTERS="$HERE/adapters"

MARK_BEGIN="<!-- BEGIN GODMODE-PORTABLE -->"
MARK_END="<!-- END GODMODE-PORTABLE -->"

marker_begin() { echo "<!-- BEGIN GODMODE-PORTABLE:${1} -->"; }
marker_end()   { echo "<!-- END GODMODE-PORTABLE:${1} -->"; }

TARGET_HOME="${GODMODE_TARGET_HOME:-$HOME}"
PROJECT_DIR="${GODMODE_PROJECT_DIR:-$PWD}"
DRY=0
UNINSTALL=0
NO_DETECT=0
GUARDS=0
RESTORE_GUARDS=0
SCOPE="both"
AGENT_FILTER=""

PY=""
if command -v python3 >/dev/null 2>&1 && python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1 && python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
  PY=python
else
  echo "error: no working Python 3.9 or newer found." >&2
  echo "  On Termux:  pkg install python" >&2
  echo "  On Debian:  sudo apt install python3" >&2
  echo "  On macOS:   brew install python" >&2
  exit 1
fi

IS_TERMUX=0
if [[ -n "${PREFIX:-}" && "$PREFIX" == *com.termux* ]]; then
  IS_TERMUX=1
elif [[ -d /data/data/com.termux ]]; then
  IS_TERMUX=1
fi

ALL_AGENTS=(claude-code codex cursor windsurf gemini cline roo continue openclaw opencode antigravity minimax hermes-lab)

usage() {
  cat <<'USAGE'
Godfather — portable installer for Claude Code, Codex, Cursor, Windsurf,
Gemini CLI, Cline, Roo Code, Continue, OpenClaw, OpenCode.

Usage:
  bash install.sh [options]

Options:
  --dry-run            Print planned writes, change nothing
  --uninstall          Remove installed blocks and copies (backups kept)
  --agents a,b         Restrict to specific agents
  --target-home DIR    Install user-level files under a different home
  --project DIR        Project root for project-level files
  --global-only        Install only user-level files
  --project-only       Install only project-level files
  --no-detect          Ignore CLI detection, install every agent
  --guards             Also turn the agents' own guard settings off
  --restore-guards     Put the backed-up guard settings back
  -h, --help           Show this help
USAGE
}

log()  { printf '  %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)      DRY=1; shift ;;
    --uninstall)    UNINSTALL=1; shift ;;
    --no-detect)    NO_DETECT=1; shift ;;
    --guards)       GUARDS=1; shift ;;
    --restore-guards) RESTORE_GUARDS=1; shift ;;
    --agents)       AGENT_FILTER="${2:-}"; shift 2 ;;
    --target-home)  TARGET_HOME="${2:-}"; shift 2 ;;
    --project)      PROJECT_DIR="${2:-}"; shift 2 ;;
    --global-only)  SCOPE="global"; shift ;;
    --project-only) SCOPE="project"; shift ;;
    -h|--help)      usage; exit 0 ;;
    *)              die "unknown flag: $1 (try --help)" ;;
  esac
done


agent_config_dir() {
  case "$1" in
    claude-code) echo "$TARGET_HOME/.claude" ;;
    codex)       echo "$TARGET_HOME/.codex" ;;
    cursor)      echo "$TARGET_HOME/.cursor" ;;
    windsurf)    echo "$TARGET_HOME/.windsurf" ;;
    gemini)      echo "$TARGET_HOME/.gemini" ;;
    cline)       echo "$TARGET_HOME/Documents/Cline" ;;
    roo)         echo "$TARGET_HOME/Documents/Roo" ;;
    continue)    echo "$TARGET_HOME/.continue" ;;
    openclaw)    echo "$TARGET_HOME/.openclaw" ;;
    opencode)    echo "$TARGET_HOME/.config/opencode" ;;
    antigravity) echo "$TARGET_HOME/.antigravity" ;;
    minimax)     echo "$TARGET_HOME/.minimax" ;;
    hermes-lab)  echo "$TARGET_HOME/.hermes-lab" ;;
    *)           echo "" ;;
  esac
}

agent_has_cli() {
  case "$1" in
    claude-code) command -v claude >/dev/null 2>&1 ;;
    codex)       command -v codex >/dev/null 2>&1 ;;
    cursor)      command -v cursor-agent >/dev/null 2>&1 || command -v cursor >/dev/null 2>&1 ;;
    windsurf)    command -v windsurf >/dev/null 2>&1 ;;
    gemini)      command -v gemini >/dev/null 2>&1 ;;
    cline)       command -v cline >/dev/null 2>&1 ;;
    roo)         command -v roo >/dev/null 2>&1 ;;
    continue)    true ;;
    openclaw)    command -v openclaw >/dev/null 2>&1 ;;
    opencode)    command -v opencode >/dev/null 2>&1 ;;
    antigravity) command -v antigravity >/dev/null 2>&1 ;;
    minimax)     command -v minimax >/dev/null 2>&1 ;;
    hermes-lab)  command -v hermes-lab >/dev/null 2>&1 ;;
    *)           false ;;
  esac
}

agent_present() {
  agent_has_cli "$1" && return 0
  local dir
  dir="$(agent_config_dir "$1")"
  [[ -n "$dir" && -e "$dir" ]] && return 0
  return 1
}

want_agent() {
  local a="$1"
  [[ -z "$AGENT_FILTER" ]] && return 0
  [[ ",$AGENT_FILTER," == *",$a,"* ]]
}

write_block() {
  local target="$1" snippet="$2" label="$3"
  local body; body="$(cat "$snippet")"
  local mb me
  mb="$(marker_begin "$label")"
  me="$(marker_end "$label")"

  if [[ $DRY -eq 1 ]]; then
    log "would write block [$label] -> $target"
    return 0
  fi

  mkdir -p "$(dirname "$target")"

  if [[ ! -f "$target" ]]; then
    {
      printf '%s\n' "$mb"
      printf '%s\n\n' "$body"
      printf '%s\n' "$me"
    } > "$target"
    log "created $target [$label]"
    return 0
  fi

  if grep -qF "$mb" "$target" && grep -qF "$me" "$target"; then
    local before after
    before="$(awk -v b="$mb" 'index($0,b)==1{exit} {print}' "$target")"
    after="$(awk -v e="$me" 'f{print} $0==e{f=1}' "$target")"
    {
      [[ -n "$before" ]] && printf '%s\n' "$before"
      printf '%s\n' "$mb"
      printf '%s\n\n' "$body"
      printf '%s\n' "$me"
      [[ -n "$after" ]] && printf '%s\n' "$after"
    } > "$target"
    rm -f "$target.tmp.$$"
    log "updated block [$label] in $target"
    return 0
  fi

  if grep -qF "$MARK_BEGIN" "$target" && grep -qF "$MARK_END" "$target"; then
    local before after
    before="$(awk -v b="$MARK_BEGIN" 'index($0,b)==1{exit} {print}' "$target")"
    after="$(awk -v e="$MARK_END" 'f{print} $0==e{f=1}' "$target")"
    {
      [[ -n "$before" ]] && printf '%s\n' "$before"
      printf '%s\n' "$mb"
      printf '%s\n\n' "$body"
      printf '%s\n' "$me"
      [[ -n "$after" ]] && printf '%s\n' "$after"
    } > "$target"
    log "upgraded legacy block [$label] in $target"
    return 0
  fi

  if [[ ! -f "$target.bak.godfather" ]]; then
    cp -p "$target" "$target.bak.godfather"
    log "backup  $target.bak.godfather"
  fi
  {
    printf '\n%s\n' "$mb"
    printf '%s\n\n' "$body"
    printf '%s\n\n' "$me"
  } >> "$target"
  log "appended block [$label] -> $target"
}

copy_file() {
  local src="$1" dest="$2"
  if [[ $DRY -eq 1 ]]; then
    log "would copy $src -> $dest"
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  cp -f "$src" "$dest"
  log "copied  -> $dest"
}

copy_dir() {
  local src="$1" dest="$2"
  if [[ $DRY -eq 1 ]]; then
    log "would copy dir $src -> $dest"
    return 0
  fi
  mkdir -p "$dest"
  for f in "$src"/*.py; do
    [[ -e "$f" ]] || continue
    cp -f "$f" "$dest/"
  done
  chmod +x "$dest"/*.py 2>/dev/null
  log "copied  -> $dest/*.py"
}

remove_block() {
  local target="$1" label="$2"
  [[ -f "$target" ]] || return 0
  local mb me
  mb="$(marker_begin "$label")"
  me="$(marker_end "$label")"
  if ! grep -qF "$mb" "$target"; then
    mb="$MARK_BEGIN"
    me="$MARK_END"
  fi
  if [[ $DRY -eq 1 ]]; then
    log "would strip block [$label] -> $target"
    return 0
  fi
  if grep -qF "$mb" "$target"; then
    local before after
    before="$(awk -v b="$mb" 'index($0,b)==1{exit} {print}' "$target")"
    after="$(awk -v e="$me" 'f{print} $0==e{f=1}' "$target")"
    if [[ -z "$before" && -z "$after" ]]; then
      if grep -E "<!-- BEGIN GODMODE-PORTABLE:" "$target" 2>/dev/null \
         | grep -qvF "$mb"; then
        :
      else
        rm -f "$target"
      fi
    else
      {
        [[ -n "$before" ]] && printf '%s\n' "$before"
        [[ -n "$after" ]] && printf '%s\n' "$after"
      } > "$target"
    fi
    log "stripped block [$label] -> $target"
  fi
}

remove_file() {
  local target="$1"
  [[ -e "$target" ]] || return 0
  if [[ $DRY -eq 1 ]]; then
    log "would remove $target"
    return 0
  fi
  rm -rf "$target"
  log "removed $target"
}

want_scope() {
  case "$SCOPE" in
    both)    return 0 ;;
    global)  [[ "$1" == "global" ]] ;;
    project) [[ "$1" == "project" ]] ;;
  esac
}

install_core() {
  want_scope global || return 0
  local core="$TARGET_HOME/.godfather"
  local src="$HERE/scripts"
  local dst="$core/scripts"
  if [[ $DRY -eq 1 ]]; then
    log "would copy scripts -> $dst"
    log "would create $core/env"
    log "would mirror the repository -> $TARGET_HOME/.godfather"
    return 0
  fi
  mkdir -p "$dst"
  for f in "$src"/*.py; do
    cp -f "$f" "$dst/"
  done
  if [[ -f "$TARGET_HOME/.godmode/env" && ! -f "$TARGET_HOME/.godfather/env" ]]; then
    cp -f "$TARGET_HOME/.godmode/env" "$TARGET_HOME/.godfather/env"
    chmod 600 "$TARGET_HOME/.godfather/env"
    log "migrated -> $TARGET_HOME/.godfather/env"
  fi
  log "copied  -> $dst"
  mirror_repo
  local envfile="$core/env"
  if [[ ! -f "$envfile" ]]; then
    {
      printf '# Godfather relay config. Optional: these override auto-resolution.\n'
      printf '# GODMODE_API_KEY=\n'
      printf '# GODMODE_BASE_URL=\n'
      printf '# GODMODE_MODEL=\n'
    } > "$envfile"
    chmod 600 "$envfile"
    log "created $envfile"
  else
    log "kept    $envfile (existing config preserved)"
  fi
}

mirror_repo() {
  local root="$TARGET_HOME/.godfather"
  if [[ -L "$root" ]]; then
    log "kept    $root (link to the runtime directory)"
    return 0
  fi
  local here="$HERE"
  if [[ "$(cd "$here" && pwd -P)" == "$(cd "$root" 2>/dev/null && pwd -P)" ]]; then
    log "kept    $root (already the current directory)"
    return 0
  fi
  mkdir -p "$root"
  for item in install.sh bootstrap.sh SKILL.md README.md gf verify.sh install-mcp.sh; do
    if [[ -f "$HERE/$item" ]]; then
      cp -f "$HERE/$item" "$root/$item" 2>/dev/null
    fi
  done
  if [[ -d "$HERE/scripts" ]]; then
    mkdir -p "$root/scripts"
    cp -f "$HERE/scripts/"*.py "$root/scripts/" 2>/dev/null
  fi
  if [[ -d "$HERE/adapters" ]]; then
    mkdir -p "$root/adapters"
    cp -f "$HERE/adapters/"*.md "$root/adapters/" 2>/dev/null
  fi
  if [[ -d "$HERE/references" ]]; then
    mkdir -p "$root/references"
    cp -rf "$HERE/references/." "$root/references/" 2>/dev/null
  fi
  if [[ -d "$HERE/assets" ]]; then
    mkdir -p "$root/assets"
    cp -f "$HERE/assets/"* "$root/assets/" 2>/dev/null
  fi
  chmod +x "$root/install.sh" "$root/gf" "$root/verify.sh" "$root/install-mcp.sh" \
    "$root/bootstrap.sh" 2>/dev/null
  log "mirrored -> $root"
}

purge_legacy() {
  local paths=(
    "$TARGET_HOME/.claude/skills/godmode"
    "$TARGET_HOME/.gemini/godmode"
    "$TARGET_HOME/.minimax/godmode"
    "$TARGET_HOME/.hermes-lab/godmode"
    "$PROJECT_DIR/.claude/skills/godmode"
    "$TARGET_HOME/.codex/prompts/godmode.md"
    "$TARGET_HOME/.cursor/rules/godmode.mdc"
    "$PROJECT_DIR/.cursor/rules/godmode.mdc"
    "$PROJECT_DIR/.windsurf/rules/godmode.md"
    "$TARGET_HOME/Documents/Cline/Rules/godmode.md"
    "$PROJECT_DIR/.clinerules/godmode.md"
    "$TARGET_HOME/Documents/Roo/Rules/godmode.md"
    "$PROJECT_DIR/.roo/rules/godmode.md"
    "$TARGET_HOME/.continue/rules/godmode.md"
    "$PROJECT_DIR/.continue/rules/godmode.md"
    "$TARGET_HOME/.claude/commands/godmode.md"
    "$TARGET_HOME/.claude/commands/godfather"
    "$TARGET_HOME/.cursor/commands/godfather"
    "$TARGET_HOME/.codex/prompts/godfather"
    "$TARGET_HOME/.config/opencode/command/godfather"
    "$TARGET_HOME/.openclaw/commands/godfather"
    "$TARGET_HOME/.antigravity/commands/godfather"
    "$TARGET_HOME/.codeium/windsurf/workflows/godfather"
    "$TARGET_HOME/Documents/Cline/Workflows/godfather"
    "$TARGET_HOME/Documents/Roo/Workflows/godfather"
    "$TARGET_HOME/.continue/rules/godfather"
    "$TARGET_HOME/.cursor/commands/godmode.md"
    "$TARGET_HOME/.codeium/windsurf/workflows/godmode.md"
    "$TARGET_HOME/Documents/Cline/Workflows/godmode.md"
    "$TARGET_HOME/Documents/Roo/Workflows/godmode.md"
    "$TARGET_HOME/.openclaw/commands/godmode.md"
    "$TARGET_HOME/.config/opencode/command/godmode.md"
    "$TARGET_HOME/.antigravity/commands/godmode.md"
    "$TARGET_HOME/.gemini/commands/godmode.md"
    "$TARGET_HOME/.gemini/commands/godmode.toml"
    "$TARGET_HOME/.minimax/commands/godmode.md"
    "$TARGET_HOME/.hermes-lab/commands/godfather.md"
  )
  local path
  for path in "${paths[@]}"; do
    if [[ -e "$path" ]]; then
      remove_file "$path"
    fi
  done
}

install_gemini_commands() {
  local dir="$1"
  [[ -d "$ADAPTERS/commands" ]] || return 0
  mkdir -p "$dir"
  for cmd in "$ADAPTERS/commands"/*.md; do
    [[ -f "$cmd" ]] || continue
    local name
    name="$(basename "$cmd" .md)"
    {
      printf 'description = "%s"\n' "Load the operator rules for this session"
      printf 'prompt = """\n'
      awk 'BEGIN{fm=0} /^---[[:space:]]*$/{fm++; next} fm==1{next} {print}' "$cmd"
      printf '\n"""\n'
    } > "$dir/$name.toml" 2>/dev/null
  done
  rm -f "$dir/god_mode.md" "$dir/tulip_rules.md" 2>/dev/null
  rm -f "$dir/god_mode.toml" "$dir/tulip_rules.toml" 2>/dev/null
  log "commands -> $dir"
}

remove_commands() {
  local dir="$1"
  rm -f "$dir/godfather.md" "$dir/godfather.toml" 2>/dev/null
  rm -f "$dir/god_mode.md" "$dir/tulip_rules.md" 2>/dev/null
  rm -f "$dir/god_mode.toml" "$dir/tulip_rules.toml" 2>/dev/null
  rmdir "$dir" 2>/dev/null
}

install_commands() {
  local dir="$1"
  mkdir -p "$dir"
  if [[ -d "$ADAPTERS/commands" ]]; then
    for cmd in "$ADAPTERS/commands"/*.md; do
      [[ -f "$cmd" ]] || continue
      cp -f "$cmd" "$dir/$(basename "$cmd")" 2>/dev/null
    done
  fi
  rm -f "$dir/god_mode.md" "$dir/tulip_rules.md" 2>/dev/null
  rm -f "$dir/god_mode.toml" "$dir/tulip_rules.toml" 2>/dev/null
  log "commands -> $dir"
}

install_antigravity() {
  want_scope global || return 0
  write_block "$TARGET_HOME/.gemini/AGENTS.md" "$ADAPTERS/antigravity.md" "antigravity"
  copy_file "$HERE/SKILL.md" "$TARGET_HOME/.gemini/godfather/SKILL.md"
  copy_dir "$HERE/scripts" "$TARGET_HOME/.gemini/godfather/scripts"
  want_scope project && {
    write_block "$PROJECT_DIR/AGENTS.md" "$ADAPTERS/antigravity.md" "antigravity"
    copy_file "$HERE/SKILL.md" "$PROJECT_DIR/.agent/skills/godfather/SKILL.md"
  }
  install_commands "$TARGET_HOME/.antigravity/commands"
  want_scope project && install_commands "$PROJECT_DIR/.agent/workflows"
}

install_minimax() {
  want_scope global || return 0
  write_block "$TARGET_HOME/.minimax/AGENTS.md" "$ADAPTERS/minimax.md" "minimax"
  copy_file "$HERE/SKILL.md" "$TARGET_HOME/.minimax/godfather/SKILL.md"
  copy_dir "$HERE/scripts" "$TARGET_HOME/.minimax/godfather/scripts"
  want_scope project && {
    write_block "$PROJECT_DIR/AGENTS.md" "$ADAPTERS/minimax.md" "minimax"
    copy_file "$HERE/SKILL.md" "$PROJECT_DIR/.minimax/skills/godfather/SKILL.md"
  }
  install_commands "$TARGET_HOME/.minimax/commands"
}

install_hermes_lab() {
  want_scope global || return 0
  write_block "$TARGET_HOME/.hermes-lab/AGENTS.md" "$ADAPTERS/hermes-lab.md" "hermes-lab"
  copy_file "$HERE/SKILL.md" "$TARGET_HOME/.hermes-lab/godfather/SKILL.md"
  copy_dir "$HERE/scripts" "$TARGET_HOME/.hermes-lab/godfather/scripts"
  want_scope project && {
    write_block "$PROJECT_DIR/AGENTS.md" "$ADAPTERS/hermes-lab.md" "hermes-lab"
    copy_file "$HERE/SKILL.md" "$PROJECT_DIR/.hermes-lab/skills/godfather/SKILL.md"
  }
  install_commands "$TARGET_HOME/.hermes-lab/commands"
}

install_claude_code() {
  want_scope global || return 0
  copy_file "$HERE/SKILL.md" "$TARGET_HOME/.claude/skills/godfather/SKILL.md"
  copy_dir "$HERE/scripts" "$TARGET_HOME/.claude/skills/godfather/scripts"
  install_commands "$TARGET_HOME/.claude/commands"
  write_block "$TARGET_HOME/.claude/CLAUDE.md" "$ADAPTERS/claude-code.md" "claude-code"
  want_scope project && {
    copy_file "$HERE/SKILL.md" "$PROJECT_DIR/.claude/skills/godfather/SKILL.md"
    copy_dir "$HERE/scripts" "$PROJECT_DIR/.claude/skills/godfather/scripts"
    write_block "$PROJECT_DIR/CLAUDE.md" "$ADAPTERS/claude-code.md" "claude-code"
  }
}

install_codex() {
  want_scope global || return 0
  write_block "$TARGET_HOME/.codex/AGENTS.md" "$ADAPTERS/codex.md" "codex"
  install_commands "$TARGET_HOME/.codex/prompts"
  copy_file "$HERE/SKILL.md" "$TARGET_HOME/.codex/prompts/godfather.md"
  want_scope project && write_block "$PROJECT_DIR/AGENTS.md" "$ADAPTERS/codex.md" "codex"
}
install_cursor() {
  want_scope global || return 0
  copy_file "$ADAPTERS/cursor.md" "$TARGET_HOME/.cursor/rules/godfather.mdc"
  install_commands "$TARGET_HOME/.cursor/commands"
  want_scope project && copy_file "$ADAPTERS/cursor.md" "$PROJECT_DIR/.cursor/rules/godfather.mdc"
}

install_windsurf() {
  want_scope global || return 0
  write_block "$TARGET_HOME/.codeium/windsurf/memories/global_rules.md" "$ADAPTERS/windsurf.md" "windsurf"
  install_commands "$TARGET_HOME/.codeium/windsurf/workflows"
  want_scope project && write_block "$PROJECT_DIR/.windsurf/rules/godfather.md" "$ADAPTERS/windsurf.md" "windsurf"
}

install_gemini() {
  want_scope global || return 0
  write_block "$TARGET_HOME/.gemini/GEMINI.md" "$ADAPTERS/gemini.md" "gemini"
  install_gemini_commands "$TARGET_HOME/.gemini/commands"
  want_scope project && write_block "$PROJECT_DIR/GEMINI.md" "$ADAPTERS/gemini.md" "gemini"
}


install_cline() {
  want_scope global || return 0
  copy_file "$ADAPTERS/cline.md" "$TARGET_HOME/Documents/Cline/Rules/godfather.md"
  install_commands "$TARGET_HOME/Documents/Cline/Workflows"
  want_scope project && copy_file "$ADAPTERS/cline.md" "$PROJECT_DIR/.clinerules/godfather.md"
}

install_roo() {
  want_scope global || return 0
  copy_file "$ADAPTERS/roo.md" "$TARGET_HOME/Documents/Roo/Rules/godfather.md"
  install_commands "$TARGET_HOME/Documents/Roo/Workflows"
  want_scope project && copy_file "$ADAPTERS/roo.md" "$PROJECT_DIR/.roo/rules/godfather.md"
}

install_continue() {
  want_scope global || return 0
  copy_file "$ADAPTERS/continue.md" "$TARGET_HOME/.continue/rules/godfather.md"
  install_commands "$TARGET_HOME/.continue/rules"
  want_scope project && copy_file "$ADAPTERS/continue.md" "$PROJECT_DIR/.continue/rules/godfather.md"
}

install_openclaw() {
  want_scope global || return 0
  local cfg="$TARGET_HOME/.openclaw/openclaw.json"
  local ws="$TARGET_HOME/.openclaw/workspace"
  if [[ -f "$cfg" ]]; then
    local detected
    detected="$("$PY" - "$cfg" <<'PY' 2>/dev/null
import json, os, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
ws = ((cfg.get("agents") or {}).get("defaults") or {}).get("workspace")
if ws:
    print(os.path.expanduser(ws))
PY
)"
    [[ -n "$detected" ]] && ws="$detected"
  fi
  write_block "$ws/AGENTS.md" "$ADAPTERS/openclaw.md" "openclaw"
  copy_file "$HERE/SKILL.md" "$ws/skills/godfather/SKILL.md"
  copy_dir "$HERE/scripts" "$ws/skills/godfather/scripts"
  copy_file "$HERE/SKILL.md" "$TARGET_HOME/.openclaw/skills/godfather/SKILL.md"
  copy_dir "$HERE/scripts" "$TARGET_HOME/.openclaw/skills/godfather/scripts"
  install_commands "$TARGET_HOME/.openclaw/commands"
  install_commands "$ws/commands"
  want_scope project && {
    write_block "$PROJECT_DIR/AGENTS.md" "$ADAPTERS/openclaw.md" "openclaw"
    copy_file "$HERE/SKILL.md" "$PROJECT_DIR/skills/godfather/SKILL.md"
  }
}

install_opencode() {
  want_scope global || return 0
  local cfgdir="$TARGET_HOME/.config/opencode"
  write_block "$cfgdir/AGENTS.md" "$ADAPTERS/opencode.md" "opencode"
  install_commands "$cfgdir/command"
  copy_file "$HERE/SKILL.md" "$cfgdir/skills/godfather/SKILL.md"
  copy_dir "$HERE/scripts" "$cfgdir/skills/godfather/scripts"
  want_scope project && {
    write_block "$PROJECT_DIR/AGENTS.md" "$ADAPTERS/opencode.md" "opencode"
    copy_file "$HERE/SKILL.md" "$PROJECT_DIR/.opencode/skills/godfather/SKILL.md"
    copy_dir "$HERE/scripts" "$PROJECT_DIR/.opencode/skills/godfather/scripts"
  }
}

cleanup_legacy_aider() {
  remove_block "$PROJECT_DIR/CONVENTIONS.md" "aider"
  remove_file "$TARGET_HOME/.aider/commands/godfather.md"
  rmdir "$TARGET_HOME/.aider/commands" 2>/dev/null
  rmdir "$TARGET_HOME/.aider" 2>/dev/null
  local cfg="$TARGET_HOME/.aider.conf.yml"
  if [[ -f "$cfg" ]] && grep -q "CONVENTIONS.md" "$cfg" 2>/dev/null; then
    rm -f "$cfg"
    log "removed $cfg"
  fi
}

uninstall_core() {
  if [[ -L "$TARGET_HOME/.godfather" ]]; then
    rm -f "$TARGET_HOME/.godfather"
    log "removed $TARGET_HOME/.godfather (link)"
  elif [[ -d "$TARGET_HOME/.godfather" ]]; then
    for item in install.sh bootstrap.sh SKILL.md README.md gf verify.sh install-mcp.sh; do
      rm -f "$TARGET_HOME/.godfather/$item"
    done
    rm -rf "$TARGET_HOME/.godfather/scripts" "$TARGET_HOME/.godfather/adapters" \
      "$TARGET_HOME/.godfather/references" "$TARGET_HOME/.godfather/assets"
    rmdir "$TARGET_HOME/.godfather" 2>/dev/null \
      && log "removed $TARGET_HOME/.godfather" \
      || log "kept    $TARGET_HOME/.godfather (holds files of your own)"
  fi
  remove_file "$TARGET_HOME/.godmode"
  remove_file "$TARGET_HOME/.godfather"
}

uninstall_antigravity() {
  remove_block "$TARGET_HOME/.gemini/AGENTS.md" "antigravity"
  remove_block "$PROJECT_DIR/AGENTS.md" "antigravity"
  remove_file "$TARGET_HOME/.gemini/godfather"
  remove_file "$TARGET_HOME/.gemini/commands/godfather"
  remove_file "$PROJECT_DIR/.agent/skills/godfather"
  remove_commands "$TARGET_HOME/.antigravity/commands"
  remove_commands "$PROJECT_DIR/.agent/workflows"
}

uninstall_minimax() {
  remove_block "$TARGET_HOME/.minimax/AGENTS.md" "minimax"
  remove_block "$PROJECT_DIR/AGENTS.md" "minimax"
  remove_file "$TARGET_HOME/.minimax/godfather"
  remove_file "$TARGET_HOME/.minimax/commands"
  remove_file "$PROJECT_DIR/.minimax/skills/godfather"
  remove_commands "$TARGET_HOME/.minimax/commands"
}

uninstall_hermes_lab() {
  remove_block "$TARGET_HOME/.hermes-lab/AGENTS.md" "hermes-lab"
  remove_block "$PROJECT_DIR/AGENTS.md" "hermes-lab"
  remove_file "$TARGET_HOME/.hermes-lab/godfather"
  remove_file "$TARGET_HOME/.hermes-lab/commands"
  remove_file "$PROJECT_DIR/.hermes-lab/skills/godfather"
  remove_commands "$TARGET_HOME/.hermes-lab/commands"
}

uninstall_claude_code() {
  remove_block "$TARGET_HOME/.claude/CLAUDE.md" "claude-code"
  remove_file "$TARGET_HOME/.claude/skills/godfather"
  remove_block "$PROJECT_DIR/CLAUDE.md" "claude-code"
  remove_file "$PROJECT_DIR/.claude/skills/godfather"
  remove_commands "$TARGET_HOME/.claude/commands"
}

uninstall_codex() {
  remove_block "$TARGET_HOME/.codex/AGENTS.md" "codex"
  remove_file "$TARGET_HOME/.codex/prompts/godfather.md"
  remove_block "$PROJECT_DIR/AGENTS.md" "codex"
  remove_commands "$TARGET_HOME/.codex/prompts"
}
uninstall_cursor() {
  remove_file "$TARGET_HOME/.cursor/rules/godfather.mdc"
  remove_file "$PROJECT_DIR/.cursor/rules/godfather.mdc"
  remove_commands "$TARGET_HOME/.cursor/commands"
}
uninstall_windsurf() {
  remove_block "$TARGET_HOME/.codeium/windsurf/memories/global_rules.md" "windsurf"
  remove_block "$PROJECT_DIR/.windsurf/rules/godfather.md" "windsurf"
  remove_commands "$TARGET_HOME/.codeium/windsurf/workflows"
}
uninstall_gemini() {
  remove_block "$TARGET_HOME/.gemini/GEMINI.md" "gemini"
  remove_block "$PROJECT_DIR/GEMINI.md" "gemini"
  remove_commands "$TARGET_HOME/.gemini/commands"
}
uninstall_cline() {
  remove_file "$TARGET_HOME/Documents/Cline/Rules/godfather.md"
  remove_file "$PROJECT_DIR/.clinerules/godfather.md"
  remove_commands "$TARGET_HOME/Documents/Cline/Workflows"
}
uninstall_roo() {
  remove_file "$TARGET_HOME/Documents/Roo/Rules/godfather.md"
  remove_file "$PROJECT_DIR/.roo/rules/godfather.md"
  remove_commands "$TARGET_HOME/Documents/Roo/Workflows"
}
uninstall_continue() {
  remove_file "$TARGET_HOME/.continue/rules/godfather.md"
  remove_file "$PROJECT_DIR/.continue/rules/godfather.md"
  remove_commands "$TARGET_HOME/.continue/rules"
}


uninstall_openclaw() {
  remove_block "$TARGET_HOME/.openclaw/workspace/AGENTS.md" "openclaw"
  remove_file "$TARGET_HOME/.openclaw/workspace/skills/godfather"
  remove_file "$TARGET_HOME/.openclaw/skills/godfather"
  remove_block "$PROJECT_DIR/AGENTS.md" "openclaw"
  remove_file "$PROJECT_DIR/skills/godfather"
  local ws="$TARGET_HOME/.openclaw/workspace"
  remove_commands "$TARGET_HOME/.openclaw/commands"
  remove_commands "$ws/commands"
}
uninstall_opencode() {
  remove_block "$TARGET_HOME/.config/opencode/AGENTS.md" "opencode"
  remove_file "$TARGET_HOME/.config/opencode/skills/godfather"
  remove_block "$PROJECT_DIR/AGENTS.md" "opencode"
  remove_file "$PROJECT_DIR/.opencode/skills/godfather"
  remove_commands "$TARGET_HOME/.config/opencode/command"
}

[[ -d "$ADAPTERS" ]] || die "adapters/ not found next to install.sh"

if [[ $UNINSTALL -eq 1 ]]; then
  echo "Godfather uninstall"
  echo "  home:    $TARGET_HOME"
  echo "  project: $PROJECT_DIR"
  for a in "${ALL_AGENTS[@]}"; do
    want_agent "$a" || continue
    "uninstall_$(echo "$a" | tr '-' '_')"
  done
  cleanup_legacy_aider
  uninstall_core
  echo "done (backups *.bak.godfather kept)"
  exit 0
fi

echo "Godfather install"
echo "  home:    $TARGET_HOME"
echo "  project: $PROJECT_DIR"
echo "  scope:   $SCOPE"
[[ $DRY -eq 1 ]] && echo "  MODE:    dry-run"

echo ""
echo "[core]"
install_core

echo ""
echo "[legacy]"
purge_legacy

for a in "${ALL_AGENTS[@]}"; do
  want_agent "$a" || continue
  if [[ $NO_DETECT -eq 0 ]]; then
    if ! agent_present "$a"; then
      continue
    fi
  fi
  echo ""
  echo "[$a]"
  "install_$(echo "$a" | tr '-' '_')"
done

echo ""
if [[ $DRY -eq 1 ]]; then
  echo "dry-run complete — nothing written"
elif [[ $IS_TERMUX -eq 1 ]]; then
  echo "installed on Termux. Restart your agent session(s) so the rules load."
  echo ""
  missing=()
  if [[ -z "$PY" ]]; then
    missing+=("python")
  fi
  command -v git >/dev/null 2>&1 || missing+=("git")
  command -v curl >/dev/null 2>&1 || missing+=("curl")
  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    missing+=("nodejs")
  fi
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Missing packages:"
    echo "  pkg install ${missing[*]}"
    echo ""
  fi
  echo "Next steps:"
  echo "  1. Check the install:"
  echo "       $PY $TARGET_HOME/.godfather/scripts/selftest.py"
  echo "  2. Run the relay:"
  echo "       $PY $TARGET_HOME/.godfather/scripts/relay.py \"your request\""
  echo ""
  if [[ ! -d "$HOME/storage" ]]; then
    echo "Note: run termux-setup-storage if you keep projects outside \$HOME."
    echo ""
  fi
  echo "Note: agents that need a desktop GUI do not run here, but the"
  echo "      relay, the resolver and the skill files all do."
else

if [[ $RESTORE_GUARDS -eq 1 ]]; then
  echo ""
  echo "[guards]"
  "$PY" "$HERE/scripts/guard.py" restore
elif [[ $GUARDS -eq 1 ]]; then
  echo ""
  echo "[guards]"
  "$PY" "$HERE/scripts/guard.py" apply
fi

  echo "installed. Restart your agent session(s) so the rules load."
  echo "verify: $PY $HERE/scripts/godmode_check.py --auto-provider --canary all"
  echo "relay : $PY $TARGET_HOME/.godfather/scripts/relay.py --frame card \"your request\""
fi
