#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# repo-slug.sh — work out which GitHub repo the release assets live on
# =============================================================================
# Sourced by the release helper scripts. Resolves, in order:
#
#   1. $VACA_REPO                      (explicit override: owner/repo)
#   2. the origin remote's URL         (best: a clone knows where it came from)
#   3. $VACA_REPO_DEFAULT              (this project's canonical repo)
#
# A fork resolves to the fork, because origin wins over the default — which is
# what you want when you are testing a release you published yourself.
# ─────────────────────────────────────────────────────────────────────────────

VACA_REPO_DEFAULT="demorolled/vaca"

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

# Print the repo URL, for docs and error messages.
repo_url() { printf 'https://github.com/%s' "$(repo_slug)"; }
