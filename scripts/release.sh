#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_FILE="$ROOT_DIR/src/meridian/__init__.py"

usage() {
  cat <<'EOF'
Usage:
  scripts/release.sh patch [--push] [--remote origin]
  scripts/release.sh minor [--push] [--remote origin]
  scripts/release.sh major [--push] [--remote origin]
  scripts/release.sh rc [--push] [--remote origin]
  scripts/release.sh X.Y.Z [--push] [--remote origin]
  scripts/release.sh X.Y.Z-rc.N [--push] [--remote origin]

Bump types:
  patch   0.0.33 → 0.0.34
  minor   0.0.33 → 0.1.0
  major   0.0.33 → 1.0.0
  rc      0.0.33 → 0.0.34-rc.1, or 0.0.34-rc.1 → 0.0.34-rc.2

Behavior:
  - Updates src/meridian/__init__.py
  - Creates a release commit
  - Creates an annotated git tag named v<version>
  - Optionally pushes the branch and tag

Examples:
  scripts/release.sh patch
  scripts/release.sh rc                    # Create release candidate
  scripts/release.sh rc --push             # Create and push RC
  scripts/release.sh 0.1.0 --push          # Explicit version
  scripts/release.sh 0.1.0-rc.1            # Explicit RC version
EOF
}

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

require_clean_tree() {
  if [[ -n "$(git -C "$ROOT_DIR" status --short --ignore-submodules)" ]]; then
    die "working tree is not clean; commit or stash changes first"
  fi
}

require_branch() {
  local branch
  branch="$(git -C "$ROOT_DIR" branch --show-current)"
  if [[ -z "$branch" ]]; then
    die "release helper must run from a branch, not detached HEAD"
  fi
  printf '%s\n' "$branch"
}

read_current_version() {
  local line
  line="$(grep -E '^__version__ = "[^"]+"' "$VERSION_FILE" || true)"
  [[ -n "$line" ]] || die "could not read __version__ from $VERSION_FILE"
  printf '%s\n' "${line#*\"}" | sed 's/"$//'
}

validate_version() {
  local version="$1"
  [[ "$version" =~ ^[0-9]+(\.[0-9]+){2}(-rc\.[0-9]+)?$ ]] || \
    die "version must look like X.Y.Z or X.Y.Z-rc.N; got: $version"
}

next_version() {
  local bump="$1"
  local current="$2"
  
  # Strip any -rc.N suffix for base version parsing
  local base_version="${current%-rc.*}"
  IFS='.' read -r major minor patch <<<"$base_version"
  [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ && "$patch" =~ ^[0-9]+$ ]] || \
    die "automatic bumps require a plain semantic version base, got: $current"

  case "$bump" in
    patch) 
      patch=$((patch + 1))
      printf '%s\n' "$major.$minor.$patch"
      ;;
    minor) 
      minor=$((minor + 1)); patch=0 
      printf '%s\n' "$major.$minor.$patch"
      ;;
    major) 
      major=$((major + 1)); minor=0; patch=0 
      printf '%s\n' "$major.$minor.$patch"
      ;;
    rc)
      # If already an RC, increment RC number
      if [[ "$current" =~ -rc\.([0-9]+)$ ]]; then
        local rc_num="${BASH_REMATCH[1]}"
        rc_num=$((rc_num + 1))
        printf '%s\n' "$base_version-rc.$rc_num"
      else
        # New RC: bump patch and add -rc.1
        patch=$((patch + 1))
        printf '%s\n' "$major.$minor.$patch-rc.1"
      fi
      ;;
    *) 
      die "unknown bump kind: $bump" 
      ;;
  esac
}

write_version() {
  local version="$1"
  sed -i -E "s/^__version__ = \"[^\"]+\"/__version__ = \"$version\"/" "$VERSION_FILE"
}

main() {
  [[ $# -ge 1 ]] || {
    usage
    exit 1
  }

  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
  esac

  local target="$1"
  shift

  local push_remote=""
  local remote="origin"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --push)
        push_remote="1"
        shift
        ;;
      --remote)
        [[ $# -ge 2 ]] || die "--remote requires a value"
        remote="$2"
        shift 2
        ;;
      *)
        die "unknown argument: $1"
        ;;
    esac
  done

  # No clean-tree check — concurrent agents routinely leave untracked/dirty
  # files, and this script only stages the version file explicitly.
  local branch
  branch="$(require_branch)"

  # Pre-release checks
  printf 'Running pre-release checks...\n'
  printf '  ruff... '
  uv run ruff check . >/dev/null 2>&1 || die "ruff check failed — fix lint errors first"
  printf 'pass\n'
  printf '  pyright... '
  uv run pyright >/dev/null 2>&1 || die "pyright failed — fix type errors first"
  printf 'pass\n'
  printf '  tests... '
  uv run python -m pytest -x -q >/dev/null 2>&1 || die "tests failed — fix failing tests first"
  printf 'pass\n'

  local current_version
  current_version="$(read_current_version)"

  local next_version_value
  case "$target" in
    patch|minor|major|rc)
      next_version_value="$(next_version "$target" "$current_version")"
      ;;
    *)
      next_version_value="$target"
      ;;
  esac

  validate_version "$next_version_value"
  [[ "$next_version_value" != "$current_version" ]] || \
    die "next version matches current version ($current_version)"

  local tag="v$next_version_value"
  if git -C "$ROOT_DIR" rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    die "tag already exists: $tag"
  fi

  write_version "$next_version_value"

  local commit_msg
  if [[ "$next_version_value" =~ -rc\. ]]; then
    commit_msg="Release candidate $next_version_value"
  else
    commit_msg="Release $next_version_value"
  fi

  git -C "$ROOT_DIR" add "$VERSION_FILE"
  git -C "$ROOT_DIR" commit -m "$commit_msg"
  git -C "$ROOT_DIR" tag -a "$tag" -m "$commit_msg"

  printf 'Released %s on branch %s\n' "$next_version_value" "$branch"
  printf 'Created commit and tag %s\n' "$tag"

  if [[ -n "$push_remote" ]]; then
    git -C "$ROOT_DIR" push "$remote" "$branch"
    git -C "$ROOT_DIR" push "$remote" "$tag"
    printf 'Pushed branch %s and tag %s to %s\n' "$branch" "$tag" "$remote"
  else
    printf 'Nothing pushed. Run:\n'
    printf '  git push %s %s\n' "$remote" "$branch"
    printf '  git push %s %s\n' "$remote" "$tag"
  fi
}

main "$@"
