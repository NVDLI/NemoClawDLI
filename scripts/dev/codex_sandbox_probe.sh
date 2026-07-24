#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/dev/codex_sandbox_probe.sh
  scripts/dev/codex_sandbox_probe.sh --repair-user

Checks the host Codex sandbox dependency, not the NemoClaw course containers.
If Codex tool calls fail before a repo command runs with:
  bubblewrap is unavailable: no system bwrap was found on PATH
then the fix belongs in the Codex execution environment spec/base image:
  RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap

--repair-user is a rootless current-host fallback. It downloads the Ubuntu
bubblewrap .deb, extracts bwrap, installs it to $HOME/.local/bin, and copies it
into writable Codex WSL bin directories already on PATH. It intentionally does
not write codex-resources/bwrap because Codex hash-checks bundled resources.
USAGE
}

mode="probe"
case "${1:-}" in
  "" ) ;;
  --repair-user ) mode="repair" ;;
  -h|--help ) usage; exit 0 ;;
  * ) usage >&2; exit 2 ;;
esac

say() { printf '%s\n' "$*"; }

if command -v bwrap >/dev/null 2>&1; then
  say "codex_sandbox_probe: PASS"
  say "  bwrap: $(command -v bwrap)"
  say "  version: $(bwrap --version 2>/dev/null || true)"
  exit 0
fi

say "codex_sandbox_probe: FAIL"
say "  bwrap: not found on PATH"
say "  scope: host Codex execution environment, not the released NemoClaw course"

if [ "$mode" != "repair" ]; then
  say ""
  say "Durable fix: add bubblewrap to the Codex environment spec/base image."
  say "Current-host fallback: scripts/dev/codex_sandbox_probe.sh --repair-user"
  exit 1
fi

for cmd in apt dpkg-deb install mktemp; do
  command -v "$cmd" >/dev/null 2>&1 || { say "missing required command: $cmd" >&2; exit 2; }
done

tmp="$(mktemp -d)"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

( cd "$tmp" && apt download bubblewrap >/dev/null )
deb="$(find "$tmp" -maxdepth 1 -name 'bubblewrap_*.deb' | head -1)"
[ -n "$deb" ] || { say "bubblewrap download produced no .deb" >&2; exit 2; }
dpkg-deb -x "$deb" "$tmp/root"
[ -x "$tmp/root/usr/bin/bwrap" ] || { say "downloaded package has no usr/bin/bwrap" >&2; exit 2; }

install -d "$HOME/.local/bin"
install -m 0755 "$tmp/root/usr/bin/bwrap" "$HOME/.local/bin/bwrap"

installed="$HOME/.local/bin/bwrap"
IFS=':' read -r -a path_parts <<< "${PATH:-}"
for d in "${path_parts[@]}"; do
  case "$d" in
    */.codex/bin/wsl/*)
      if [ -d "$d" ] && [ -w "$d" ]; then
        install -m 0755 "$tmp/root/usr/bin/bwrap" "$d/bwrap"
        installed="$installed $d/bwrap"
      fi
      ;;
  esac
done

say "codex_sandbox_probe: REPAIRED"
for f in $installed; do
  say "  installed: $f"
done
say "  version: $("$HOME/.local/bin/bwrap" --version)"
say "  note: restart/fork may still be needed if a launcher process cached PATH before repair"
