#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Serve the course at /dli/ on a NemoClaw Brev launchable, the same origin as its agent.
# Uses only the image's own nginx: it installs a built Pages site and dli-location.conf, then
# adds one include line to the server that listens on port 80. It finds that server rather than a
# particular line in it, so image releases that move or reword their routes keep working. Every
# change is validated with nginx -t and rolled back on failure, following the image's
# configure-launchable-routing pattern.
#
# SITE is the output of scripts/build/build_pages.sh: a directory, or a tar archive of it such as
# the Pages workflow's artifact.tar (compressed or not).
# The raw web/ tree is not a substitute: it lacks the generated language and branch manifests.
#
#   sudo bash scripts/brev/route.sh install SITE
#   sudo bash scripts/brev/route.sh status
#   sudo bash scripts/brev/route.sh uninstall

set -euo pipefail

readonly HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROVISION="${NEMOCLAW_DLI_PROVISION:-/etc/nemoclaw/provision.json}"
readonly RUNTIME_ROOT="${NEMOCLAW_DLI_RUNTIME_ROOT:-/opt/nemoclaw-image}"
readonly INCLUDE="${NEMOCLAW_DLI_NGINX_INCLUDE:-/etc/nginx/nemoclaw-dli-location.inc}"
readonly STATE="${NEMOCLAW_DLI_STATE:-/var/lib/nemoclaw-dli}"
readonly LINE="    include $INCLUDE;"
SITE=""

fail() {
  echo "nemoclaw-dli route: $*" >&2
  exit 1
}

backup_dir="$(mktemp -d)"
trap 'rm -rf "$backup_dir"' EXIT

# Line number of the first directive that makes a server listen on port 80, such as
# "listen 80;", "listen [::]:80;", or "listen 0.0.0.0:80 default_server;".
listen_line() {
  grep -n -E '^[[:space:]]*listen[[:space:]]+([^;]*:)?80([[:space:]][^;]*)?;' "$1" | head -n 1 | cut -d: -f1 | grep .
}

# The launchable's public site is the file whose server listens on port 80: the image's usual
# path first, then every file that nginx -T reports.
find_site() {
  local candidate
  if [ -n "${NEMOCLAW_DLI_NGINX_SITE:-}" ]; then
    SITE="$NEMOCLAW_DLI_NGINX_SITE"
    return 0
  fi
  for candidate in /etc/nginx/sites-available/nemoclaw $(nginx -T 2>/dev/null | sed -n 's/^# configuration file \(.*\):$/\1/p'); do
    candidate="$(readlink -f "$candidate" 2>/dev/null || printf '%s' "$candidate")"
    if [ -f "$candidate" ] && listen_line "$candidate" >/dev/null; then
      SITE="$candidate"
      return 0
    fi
  done
  return 1
}

require_launchable() {
  [ "$(id -u)" -eq 0 ] || fail "must run as root"
  [ -r "$PROVISION" ] || [ -d "$RUNTIME_ROOT" ] \
    || fail "not a NemoClaw launchable: neither $PROVISION nor $RUNTIME_ROOT exists"
  command -v nginx >/dev/null 2>&1 || fail "nginx is not installed"
  find_site || fail "no nginx server listening on port 80 was found"
  [ -f "$SITE" ] || fail "launchable nginx site is missing: $SITE"
  # Uninstall deletes $STATE; it must be this tool's own dedicated directory.
  case "$STATE" in
    */nemoclaw-dli) ;;
    *) fail "state directory must end in /nemoclaw-dli: $STATE" ;;
  esac
}

# Finds ("find") or filters out ("drop") this tool's include line, whatever its indentation.
include_lines() {
  awk -v want="include $INCLUDE;" -v mode="$1" '
    { line = $0; gsub(/^[ \t]+|[ \t]+$/, "", line); gsub(/[ \t]+/, " ", line) }
    mode == "drop" && line != want { print }
    mode == "find" && line == want { found = 1 }
    END { if (mode == "find") exit !found }' "$SITE"
}

site_has_include() {
  include_lines find
}

backup_nginx() {
  cp -p "$SITE" "$backup_dir/site"
  if [ -f "$INCLUDE" ]; then cp -p "$INCLUDE" "$backup_dir/include"; fi
}

restore_nginx() {
  install -m 644 "$backup_dir/site" "$SITE"
  if [ -f "$backup_dir/include" ]; then
    install -m 644 "$backup_dir/include" "$INCLUDE"
  else
    rm -f "$INCLUDE"
  fi
}

# Keep a change only after nginx -t and a reload both pass; otherwise restore the backup.
apply_nginx_change() {
  if ! nginx -t; then
    restore_nginx
    fail "nginx rejected the change; previous configuration restored"
  fi
  if ! systemctl reload nginx; then
    restore_nginx
    systemctl reload nginx >/dev/null 2>&1 || true
    fail "nginx reload failed; previous configuration restored"
  fi
}

# nginx -s reload returns before new workers take over. Wait, bounded, until the route
# answers as the change intends, so a successful exit means the change is live.
await_health() {
  local want="$1" got="" attempt
  command -v curl >/dev/null 2>&1 || return 0
  for attempt in $(seq 1 50); do
    got="$(curl -sS -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1/dli/healthz 2>/dev/null || true)"
    if [ "$want" = live ] && [ "$got" = 200 ]; then return 0; fi
    if [ "$want" = gone ] && [ "$got" != 200 ]; then return 0; fi
    sleep 0.2
  done
  fail "/dli/ is not $want after 10 seconds (last status ${got:-none})"
}

install_course() {
  local source="${1:-}" at
  [ -n "$source" ] || fail "usage: route.sh install SITE (a built Pages directory or tar archive)"
  [ -e "$source" ] || fail "site is unavailable: $source"
  [ -f "$HERE/dli-location.conf" ] || fail "missing $HERE/dli-location.conf"
  [ -f "$HERE/index.html" ] || fail "missing $HERE/index.html"
  grep -qF "../../web/nemoclaw/" "$HERE/index.html" || fail "index.html has no course links to project"
  at="$(listen_line "$SITE")" || fail "no port 80 listener in $SITE"

  # Stage a complete release before touching nginx.
  local release
  release="$STATE/releases/$(date -u +%Y%m%dT%H%M%SZ)-$$"
  install -d -m 755 "$STATE/releases" "$STATE/site"
  if [ -d "$source" ]; then
    cp -R "$source" "$release"
  else
    install -d -m 755 "$release"
    tar -xf "$source" -C "$release" --no-same-owner --no-same-permissions
  fi
  chmod -R u=rwX,go=rX "$release"
  if [ ! -f "$release/nemoclaw/index.html" ] || [ ! -f "$release/languages.json" ]; then
    rm -rf "$release"
    fail "not a built Pages site (needs nemoclaw/index.html and languages.json): $source"
  fi

  # The starter page (index.html) answers /dli/ as start.html beside the site. Its links name the
  # course by repository path (../../web/nemoclaw/), which the link checks verify; at the site root
  # the course is ./nemoclaw/.
  sed 's#\.\./\.\./web/nemoclaw/#./nemoclaw/#g' "$HERE/index.html" > "$STATE/site/.start.html.next"
  chmod 644 "$STATE/site/.start.html.next"
  mv -f "$STATE/site/.start.html.next" "$STATE/site/start.html"

  # Any /dli/ address with nothing behind it answers with this page instead of the server's own
  # error page. While the startup script is still copying the course it says so and reloads.
  cat > "$STATE/site/.missing.html.next" <<'HTML'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Not on this launchable · Securing Agents with OpenShell and NemoClaw</title>
<script>(function(){try{var t=localStorage.getItem("theme")||(matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");document.documentElement.setAttribute("data-theme",t);}catch(e){}})();</script>
<style>
:root{color-scheme:dark;--g:#76b900;--bg:#0d0d0d;--card:#161616;--line:#262626;--tx:#f2f2f2;--td:#b0b0b0;--on-g:#0a0a0a}
:root[data-theme="light"]{color-scheme:light;--g:#3f6900;--bg:#ffffff;--card:#f6f8fa;--line:#e1e6eb;--tx:#1a1a1a;--td:#3b3b3b;--on-g:#ffffff}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--tx);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
main{max-width:34rem;margin:16px;padding:28px 30px;background:var(--card);border:1px solid var(--line);border-radius:12px}
.eyebrow{margin:0 0 .6em;font:600 .72rem ui-monospace,Consolas,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--g)}
h1{margin:0 0 .4em;font-size:1.45rem;line-height:1.25}
p{margin:0 0 1.2em;color:var(--td)}
.actions{display:flex;flex-wrap:wrap;gap:8px}
a{display:inline-flex;padding:8px 14px;border-radius:8px;font-weight:600;text-decoration:none;border:1px solid var(--g);background:var(--g);color:var(--on-g)}
a.secondary{background:transparent;color:var(--tx);border-color:var(--line)}
</style>
</head>
<body>
<main>
  <p class="eyebrow">NemoClaw launchable</p>
  <h1 id="title">This page is not on the launchable</h1>
  <p id="detail">The address may be mistyped, or the page may have moved. The start page links to everything the launchable serves.</p>
  <div class="actions">
    <a href="/dli/">Go to the start page</a>
    <a class="secondary" href="/dli/nemoclaw/index.html?iframe_proxy=1">Open the course</a>
  </div>
</main>
<script>
fetch("/dli/setup-status.json", { cache: "no-store" }).then(response => response.json()).then(status => {
  if (status.stage === "ready") return;
  document.getElementById("title").textContent = "The course is still copying";
  document.getElementById("detail").textContent = "This page opens on its own when the copy finishes, usually within a minute. The start page shows the progress.";
  setTimeout(() => location.reload(), 5000);
}).catch(() => {});
</script>
</body>
</html>
HTML
  chmod 644 "$STATE/site/.missing.html.next"
  mv -f "$STATE/site/.missing.html.next" "$STATE/site/missing.html"

  # The starter page's terminal popups use the image's own xterm.js build and its licenses, so the
  # course adds no browser package. Without them the page sends terminals to the dashboard.
  local xterm="$RUNTIME_ROOT/onboard-ui/node_modules/@xterm"
  rm -rf "$STATE/site/brev-terminal"
  install -d -m 755 "$STATE/site/brev-terminal"
  if [ -f "$xterm/xterm/lib/xterm.js" ] && [ -f "$xterm/xterm/css/xterm.css" ] && [ -f "$xterm/addon-fit/lib/addon-fit.js" ]; then
    install -m 644 "$xterm/xterm/lib/xterm.js" "$xterm/xterm/css/xterm.css" "$xterm/addon-fit/lib/addon-fit.js" \
      "$STATE/site/brev-terminal/"
    install -m 644 "$xterm/xterm/LICENSE" "$STATE/site/brev-terminal/xterm-LICENSE.txt"
    install -m 644 "$xterm/addon-fit/LICENSE" "$STATE/site/brev-terminal/addon-fit-LICENSE.txt"
  fi

  # The include goes right after the port 80 listen directive; nginx picks the /dli/ locations by
  # match type, not by their position in the server block.
  backup_nginx
  install -m 644 "$HERE/dli-location.conf" "$INCLUDE"
  if ! site_has_include; then
    awk -v at="$at" -v line="$LINE" '{ print } NR == at + 0 { print line }' "$SITE" > "$backup_dir/site.edited"
    install -m 644 "$backup_dir/site.edited" "$SITE"
  fi
  apply_nginx_change

  # Switch the served tree in one rename, then drop releases this script staged earlier.
  ln -s "$release" "$STATE/site/.dli.next"
  mv -T "$STATE/site/.dli.next" "$STATE/site/dli"
  find "$STATE/releases" -mindepth 1 -maxdepth 1 -type d ! -path "$release" -exec rm -rf {} +
  await_health live

  echo "nemoclaw-dli route: serving $source at /dli/"
  status
}

uninstall_course() {
  backup_nginx
  if site_has_include; then
    include_lines drop > "$backup_dir/site.edited"
    install -m 644 "$backup_dir/site.edited" "$SITE"
  fi
  rm -f "$INCLUDE"
  apply_nginx_change
  await_health gone
  rm -rf "$STATE"
  echo "nemoclaw-dli route: removed /dli/"
}

status() {
  [ -n "$SITE" ] || find_site || true
  if [ -n "$SITE" ] && [ -f "$SITE" ] && site_has_include; then
    echo "include: present in $SITE"
  else
    echo "include: absent"
  fi
  if [ -L "$STATE/site/dli" ]; then echo "release: $(readlink "$STATE/site/dli")"; else echo "release: none"; fi
  if command -v curl >/dev/null 2>&1; then
    echo "health: $(curl -sS -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1/dli/healthz || echo unreachable)"
  fi
  echo "open: https://<your nemoclaw Secure Link>/dli/"
}

case "${1:-}" in
  install) require_launchable; install_course "${2:-}" ;;
  uninstall) require_launchable; uninstall_course ;;
  status) status ;;
  *) fail "usage: route.sh install SITE | status | uninstall" ;;
esac
