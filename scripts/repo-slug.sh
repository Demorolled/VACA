#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# repo-slug.sh — work out which GitHub repo the release assets live on
# =============================================================================
# Sourced by the release helper scripts. Resolves, in order:
#
#   1. $VACA_REPO                      (explicit override: owner/repo)
#   2. the origin remote's URL         (best: a clone knows where it came from)
#   3. https://github.com/<default>    (placeholder, see below)
#
# The placeholder is what the packaged app metadata currently claims —
# visual-ai-architect under demorolled. That repo does not exist yet, so treat
# a resolution that lands there as "you still have to set this": the calling
# script says so rather than printing URLs that 404.
# ─────────────────────────────────────────────────────────────────────────────

VACA_REPO_DEFAULT="demorolled/visual-ai-architect"

repo_slug() {
  if [ -n "${VACA_REPO:-}" ]; then
    printf '%s' "${VACA_REPO%.git}"
    return 0
  fi

  local url
  url="$(git config --get remote.origin.url 2>/dev/null || true)"
  if [ -n "$url" ]; then
    # git@github.com:owner/repo.git  |  https://github.com/owner/repo.git
    url="${url%.git}"
    url="${url#git@github.com:}"
    url="${url#ssh://git@github.com/}"
    url="${url#https://github.com/}"
    url="${url#http://github.com/}"
    url="${url#github.com/}"
    case "$url" in
      */*) printf '%s' "$url"; return 0 ;;
    esac
  fi

  printf '%s' "$VACA_REPO_DEFAULT"
}

# True when the slug is still the placeholder — i.e. the release URL would 404.
repo_slug_is_placeholder() {
  [ "$(repo_slug)" = "$VACA_REPO_DEFAULT" ]
}
