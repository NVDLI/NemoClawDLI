#!/usr/bin/env bash
# Install the repo's git hooks into .git/hooks/. Idempotent.
#
# Installs a small dispatcher for every hook in this directory's git-hooks/. The
# dispatcher resolves the active worktree at invocation time, so linked worktrees run
# their own branch's hook implementation instead of a stale sibling checkout.
set -e

# Anchor on this script's directory only for installation-time source validation.
HERE="$(cd "$(dirname "$0")/.." && pwd)"
# `REPO_ROOT/.git` is a file in a linked worktree. Ask Git for the real hooks
# path so installation works in ordinary clones and worktrees alike.
HOOK_DIR="$(git rev-parse --git-path hooks)"
mkdir -p "$HOOK_DIR"

for name in pre-commit pre-push; do
    src="$HERE/git-hooks/$name"
    dst="$HOOK_DIR/$name"
    if [ ! -f "$src" ]; then
        echo "error: $src not found"
        exit 1
    fi
    chmod +x "$src"
    if [ -L "$dst" ]; then
        rm "$dst"
    elif [ -f "$dst" ] && ! grep -q "nemoclaw-worktree-dispatch" "$dst"; then
        echo "warning: $dst already exists; moving to ${dst}.bak"
        mv "$dst" "${dst}.bak"
    fi
    {
        echo '#!/usr/bin/env bash'
        echo '# nemoclaw-worktree-dispatch'
        echo 'set -euo pipefail'
        printf 'name=%q\n' "$name"
        cat <<'DISPATCH'
root="$(git rev-parse --show-toplevel)"
content_root="$root"
[ -d "$root/task1/scripts/git-hooks" ] && content_root="$root/task1"
hook="$content_root/scripts/git-hooks/$name"
if [ ! -x "$hook" ]; then
    echo "git hook dispatcher: missing executable $hook" >&2
    exit 1
fi
exec "$hook" "$@"
DISPATCH
    } > "$dst"
    chmod +x "$dst"
    echo "installed dispatcher: $dst -> active worktree scripts/git-hooks/$name"
done

echo ""
echo "Verify:"
echo "  ls -la $HOOK_DIR"
echo "  python3 $HERE/validation/contribution_safety_audit.py"
echo "  python3 $HERE/validation/validate_layout.py --quiet"
