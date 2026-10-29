#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Serve the course at /dli/ on a NemoClaw Brev launchable, the same origin as its agent.
# Uses only the image's own nginx: it installs a built Pages site and dli-location.conf, then
# adds one include line to the image's site. Every change is validated with nginx -t and rolled
# back on failure, following the image's configure-launchable-routing pattern.
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
readonly SITE="${NEMOCLAW_DLI_NGINX_SITE:-/etc/nginx/sites-available/nemoclaw}"
readonly INCLUDE="${NEMOCLAW_DLI_NGINX_INCLUDE:-/etc/nginx/nemoclaw-dli-location.inc}"
readonly STATE="${NEMOCLAW_DLI_STATE:-/var/lib/nemoclaw-dli}"
readonly ANCHOR="    include /etc/nginx/nemoclaw-agent-routes.inc;"
readonly LINE="    include $INCLUDE;"

fail() {
  echo "nemoclaw-dli route: $*" >&2
  exit 1
}

backup_dir="$(mktemp -d)"
trap 'rm -rf "$backup_dir"' EXIT

require_launchable() {
  [ "$(id -u)" -eq 0 ] || fail "must run as root"
  [ -r "$PROVISION" ] || fail "not a NemoClaw launchable: $PROVISION is missing"
  [ -f "$SITE" ] || fail "launchable nginx site is missing: $SITE"
  command -v nginx >/dev/null 2>&1 || fail "nginx is not installed"
  # Uninstall deletes $STATE; it must be this tool's own dedicated directory.
  case "$STATE" in
    */nemoclaw-dli) ;;
    *) fail "state directory must end in /nemoclaw-dli: $STATE" ;;
  esac
}

site_has_include() {
  grep -qxF "$LINE" "$SITE"
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
  local source="${1:-}"
  [ -n "$source" ] || fail "usage: route.sh install SITE (a built Pages directory or tar archive)"
  [ -e "$source" ] || fail "site is unavailable: $source"
  [ -f "$HERE/dli-location.conf" ] || fail "missing $HERE/dli-location.conf"
  [ -f "$HERE/start.html" ] || fail "missing $HERE/start.html"
  grep -qxF "$ANCHOR" "$SITE" || fail "launchable site has no agent-routes include to anchor on"

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

  # The starter page answers /dli/ beside the site.
  install -m 644 "$HERE/start.html" "$STATE/site/.start.html.next"
  mv -f "$STATE/site/.start.html.next" "$STATE/site/start.html"

  backup_nginx
  install -m 644 "$HERE/dli-location.conf" "$INCLUDE"
  if ! site_has_include; then
    awk -v anchor="$ANCHOR" -v line="$LINE" \
      '$0 == anchor { print line } { print }' "$SITE" > "$backup_dir/site.edited"
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
    grep -vxF "$LINE" "$SITE" > "$backup_dir/site.edited" || true
    install -m 644 "$backup_dir/site.edited" "$SITE"
  fi
  rm -f "$INCLUDE"
  apply_nginx_change
  await_health gone
  rm -rf "$STATE"
  echo "nemoclaw-dli route: removed /dli/"
}

status() {
  if site_has_include; then echo "include: present in $SITE"; else echo "include: absent"; fi
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
