#!/usr/bin/env bash

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTERS="$HERE/adapters"

MARK_BEGIN="<!-- BEGIN GODMODE-PORTABLE -->"
MARK_END="<!-- END GODMODE-PORTABLE -->"

TARGET_HOME="${GODMODE_TARGET_HOME:-$HOME}"
PROJECT_DIR="${GODMODE_PROJECT_DIR:-$PWD}"
DRY=0
UNINSTALL=0
NO_DETECT=0
SCOPE="both"
AGENT_FILTER=""

ALL_AGENTS=(claude-code codex cursor windsurf gemini aider cline roo continue)

usage() {
  cat <<'USAGE'
GODMODE3 — portable installer for Claude Code, Codex, Cursor, Windsurf,
Gemini CLI, Aider, Cline, Roo Code, Continue.

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
    --agents)       AGENT_FILTER="${2:-}"; shift 2 ;;
    --target-home)  TARGET_HOME="${2:-}"; shift 2 ;;
    --project)      PROJECT_DIR="${2:-}"; shift 2 ;;
    --global-only)  SCOPE="global"; shift ;;
    --project-only) SCOPE="project"; shift ;;
    -h|--help)      usage; exit 0 ;;
    *)              die "unknown flag: $1 (try --help)" ;;
  esac
done


agent_has_cli() {
  case "$1" in
    claude-code) command -v claude >/dev/null 2>&1 ;;
    codex)       command -v codex >/dev/null 2>&1 ;;
    cursor)      command -v cursor-agent >/dev/null 2>&1 || command -v cursor >/dev/null 2>&1 ;;
    windsurf)    command -v windsurf >/dev/null 2>&1 ;;
    gemini)      command -v gemini >/dev/null 2>&1 ;;
    aider)       command -v aider >/dev/null 2>&1 ;;
    cline)       command -v cline >/dev/null 2>&1 ;;
    roo)         command -v roo >/dev/null 2>&1 ;;
    continue)    true ;;
    *)           false ;;
  esac
}

want_agent() {
  local a="$1"
  [[ -z "$AGENT_FILTER" ]] && return 0
  [[ ",$AGENT_FILTER," == *",$a,"* ]]
}

write_block() {
  local target="$1" snippet="$2"
  local body; body="$(cat "$snippet"; cat "$ADAPTERS/_relay.md")"

  if [[ $DRY -eq 1 ]]; then
    log "would write block -> $target"
    return 0
  fi

  mkdir -p "$(dirname "$target")"

  if [[ ! -f "$target" ]]; then
    {
      printf '%s\n' "$MARK_BEGIN"
      printf '%s\n\n' "$body"
      printf '%s\n' "$MARK_END"
    } > "$target"
    log "created $target"
    return 0
  fi

  if grep -qF "$MARK_BEGIN" "$target" && grep -qF "$MARK_END" "$target"; then
    local before after
    before="$(awk -v b="$MARK_BEGIN" 'index($0,b)==1{exit} {print}' "$target")"
    after="$(awk -v e="$MARK_END" 'f{print} $0==e{f=1}' "$target")"
    {
      [[ -n "$before" ]] && printf '%s\n' "$before"
      printf '%s\n' "$MARK_BEGIN"
      printf '%s\n\n' "$body"
      printf '%s\n' "$MARK_END"
      [[ -n "$after" ]] && printf '%s\n' "$after"
    } > "$target"
    rm -f "$target.tmp.$$"
    log "updated block in $target"
    return 0
  fi

  if [[ ! -f "$target.bak.godmode" ]]; then
    cp -p "$target" "$target.bak.godmode"
    log "backup  $target.bak.godmode"
  fi
  {
    printf '\n%s\n' "$MARK_BEGIN"
    printf '%s\n\n' "$body"
    printf '%s\n\n' "$MARK_END"
  } >> "$target"
  log "appended block -> $target"
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
  local target="$1"
  [[ -f "$target" ]] || return 0
  if [[ $DRY -eq 1 ]]; then
    log "would strip block -> $target"
    return 0
  fi
  if grep -qF "$MARK_BEGIN" "$target"; then
    local before after
    before="$(awk -v b="$MARK_BEGIN" 'index($0,b)==1{exit} {print}' "$target")"
    after="$(awk -v e="$MARK_END" 'f{print} $0==e{f=1}' "$target")"
    {
      [[ -n "$before" ]] && printf '%s\n' "$before"
      [[ -n "$after" ]] && printf '%s\n' "$after"
    } > "$target" && rm -f "$target"
    log "stripped block -> $target"
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
  local core="$TARGET_HOME/.godmode"
  local src="$HERE/scripts"
  local dst="$core/scripts"
  if [[ $DRY -eq 1 ]]; then
    log "would copy scripts -> $dst"
    log "would create $core/env"
    return 0
  fi
  mkdir -p "$dst"
  for f in "$src"/*.py; do
    cp -f "$f" "$dst/"
  done
  log "copied  -> $dst"
  local envfile="$core/env"
  if [[ ! -f "$envfile" ]]; then
    {
      printf '# GODMODE3 relay config. Optional: these override auto-resolution.\n'
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

install_claude_code() {
  want_scope global || return 0
  copy_file "$HERE/SKILL.md" "$TARGET_HOME/.claude/skills/godmode/SKILL.md"
  copy_dir "$HERE/scripts" "$TARGET_HOME/.claude/skills/godmode/scripts"
  write_block "$TARGET_HOME/.claude/CLAUDE.md" "$ADAPTERS/claude-code.md"
  want_scope project && {
    copy_file "$HERE/SKILL.md" "$PROJECT_DIR/.claude/skills/godmode/SKILL.md"
    copy_dir "$HERE/scripts" "$PROJECT_DIR/.claude/skills/godmode/scripts"
    write_block "$PROJECT_DIR/CLAUDE.md" "$ADAPTERS/claude-code.md"
  }
}

install_codex() {
  want_scope global || return 0
  write_block "$TARGET_HOME/.codex/AGENTS.md" "$ADAPTERS/codex.md"
  copy_file "$HERE/SKILL.md" "$TARGET_HOME/.codex/prompts/godmode.md"
  want_scope project && write_block "$PROJECT_DIR/AGENTS.md" "$ADAPTERS/codex.md"
}
install_cursor() {
  want_scope global || return 0
  copy_file "$ADAPTERS/cursor.md" "$TARGET_HOME/.cursor/rules/godmode.mdc"
  want_scope project && copy_file "$ADAPTERS/cursor.md" "$PROJECT_DIR/.cursor/rules/godmode.mdc"
}

install_windsurf() {
  want_scope global || return 0
  write_block "$TARGET_HOME/.codeium/windsurf/memories/global_rules.md" "$ADAPTERS/windsurf.md"
  want_scope project && write_block "$PROJECT_DIR/.windsurf/rules/godmode.md" "$ADAPTERS/windsurf.md"
}

install_gemini() {
  want_scope global || return 0
  write_block "$TARGET_HOME/.gemini/GEMINI.md" "$ADAPTERS/gemini.md"
  want_scope project && write_block "$PROJECT_DIR/GEMINI.md" "$ADAPTERS/gemini.md"
}

install_aider() {
  want_scope project || return 0
  write_block "$PROJECT_DIR/CONVENTIONS.md" "$ADAPTERS/aider.md"
  local cfg="$TARGET_HOME/.aider.conf.yml"
  if [[ -f "$cfg" ]]; then
    if ! grep -q 'CONVENTIONS.md' "$cfg"; then
      if [[ $DRY -eq 1 ]]; then
        log "would add read: CONVENTIONS.md -> $cfg"
      else
        cp -p "$cfg" "$cfg.bak.godmode" 2>/dev/null || true
        printf '\nread:\n  - CONVENTIONS.md\n' >> "$cfg"
        log "registered CONVENTIONS.md -> $cfg"
      fi
    fi
  else
    if [[ $DRY -eq 1 ]]; then
      log "would create $cfg with read: CONVENTIONS.md"
    else
      mkdir -p "$(dirname "$cfg")"
      printf 'read:\n  - CONVENTIONS.md\n' > "$cfg"
      log "created $cfg"
    fi
  fi
}

install_cline() {
  want_scope global || return 0
  copy_file "$ADAPTERS/cline.md" "$TARGET_HOME/Documents/Cline/Rules/godmode.md"
  want_scope project && copy_file "$ADAPTERS/cline.md" "$PROJECT_DIR/.clinerules/godmode.md"
}

install_roo() {
  want_scope global || return 0
  copy_file "$ADAPTERS/roo.md" "$TARGET_HOME/Documents/Roo/Rules/godmode.md"
  want_scope project && copy_file "$ADAPTERS/roo.md" "$PROJECT_DIR/.roo/rules/godmode.md"
}

install_continue() {
  want_scope global || return 0
  copy_file "$ADAPTERS/continue.md" "$TARGET_HOME/.continue/rules/godmode.md"
  want_scope project && copy_file "$ADAPTERS/continue.md" "$PROJECT_DIR/.continue/rules/godmode.md"
}

uninstall_core() {
  remove_file "$TARGET_HOME/.godmode"
}

uninstall_claude_code() {
  remove_block "$TARGET_HOME/.claude/CLAUDE.md"
  remove_file "$TARGET_HOME/.claude/skills/godmode"
  remove_block "$PROJECT_DIR/CLAUDE.md"
  remove_file "$PROJECT_DIR/.claude/skills/godmode"
}

uninstall_codex() {
  remove_block "$TARGET_HOME/.codex/AGENTS.md"
  remove_file "$TARGET_HOME/.codex/prompts/godmode.md"
  remove_block "$PROJECT_DIR/AGENTS.md"
}
uninstall_cursor() {
  remove_file "$TARGET_HOME/.cursor/rules/godmode.mdc"
  remove_file "$PROJECT_DIR/.cursor/rules/godmode.mdc"
}
uninstall_windsurf() {
  remove_block "$TARGET_HOME/.codeium/windsurf/memories/global_rules.md"
  remove_block "$PROJECT_DIR/.windsurf/rules/godmode.md"
}
uninstall_gemini() {
  remove_block "$TARGET_HOME/.gemini/GEMINI.md"
  remove_block "$PROJECT_DIR/GEMINI.md"
}
uninstall_aider() {
  remove_block "$PROJECT_DIR/CONVENTIONS.md"
  local cfg="$TARGET_HOME/.aider.conf.yml"
  if [[ -f "$cfg" ]] && grep -q 'CONVENTIONS.md' "$cfg"; then
    if [[ $DRY -eq 1 ]]; then
      log "would drop CONVENTIONS.md from $cfg"
    else
      cp -p "$cfg" "$cfg.bak.godmode" 2>/dev/null || true
      grep -v 'CONVENTIONS.md' "$cfg" > "$cfg.tmp.$$" && mv "$cfg.tmp.$$" "$cfg"
      log "dropped CONVENTIONS.md -> $cfg"
    fi
  fi
}
uninstall_cline() {
  remove_file "$TARGET_HOME/Documents/Cline/Rules/godmode.md"
  remove_file "$PROJECT_DIR/.clinerules/godmode.md"
}
uninstall_roo() {
  remove_file "$TARGET_HOME/Documents/Roo/Rules/godmode.md"
  remove_file "$PROJECT_DIR/.roo/rules/godmode.md"
}
uninstall_continue() {
  remove_file "$TARGET_HOME/.continue/rules/godmode.md"
  remove_file "$PROJECT_DIR/.continue/rules/godmode.md"
}


[[ -d "$ADAPTERS" ]] || die "adapters/ not found next to install.sh"

if [[ $UNINSTALL -eq 1 ]]; then
  echo "GODMODE3 uninstall"
  echo "  home:    $TARGET_HOME"
  echo "  project: $PROJECT_DIR"
  for a in "${ALL_AGENTS[@]}"; do
    want_agent "$a" || continue
    "uninstall_$(echo "$a" | tr '-' '_')"
  done
  uninstall_core
  echo "done (backups *.bak.godmode kept)"
  exit 0
fi

echo "GODMODE3 install"
echo "  home:    $TARGET_HOME"
echo "  project: $PROJECT_DIR"
echo "  scope:   $SCOPE"
[[ $DRY -eq 1 ]] && echo "  MODE:    dry-run"

echo ""
echo "[core]"
install_core

for a in "${ALL_AGENTS[@]}"; do
  want_agent "$a" || continue
  if [[ $NO_DETECT -eq 0 ]]; then
    if ! agent_has_cli "$a"; then
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
else
  echo "installed. Restart your agent session(s) so the rules load."
  echo "verify: python3 $HERE/scripts/godmode_check.py --auto-provider --canary all"
  echo "relay : python3 $TARGET_HOME/.godmode/scripts/relay.py --frame card \"your request\""
fi
