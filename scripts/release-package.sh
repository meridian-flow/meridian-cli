#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOU'
Usage:
  scripts/release-package.sh <package-dir> patch [--push]
  scripts/release-package.sh <package-dir> minor [--push]
  scripts/release-package.sh <package-dir> major [--push]
  scripts/release-package.sh <package-dir> X.Y.Z [--push]

Behavior:
  - Updates <package-dir>/mars.toml [package].version
  - Creates a release commit in the package repository
  - Creates an annotated git tag named v<version>
  - Optionally pushes the package branch and tag

Examples:
  scripts/release-package.sh meridian-base patch
  scripts/release-package.sh meridian-dev-workflow 0.1.0 --push
EOU
}

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

resolve_package_dir() {
  local raw_dir="$1"
  if [[ "$raw_dir" = /* ]]; then
    printf '%s\n' "$raw_dir"
  else
    printf '%s\n' "$ROOT_DIR/$raw_dir"
  fi
}

require_package_layout() {
  [[ -d "$PACKAGE_DIR" ]] || die "package directory does not exist: $PACKAGE_DIR"

  git -C "$PACKAGE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
    die "package directory is not a git repository: $PACKAGE_DIR"

  [[ -f "$MARS_TOML" ]] || die "missing mars.toml: $MARS_TOML"

  grep -Eq '^\[package\][[:space:]]*$' "$MARS_TOML" || \
    die "missing [package] section in $MARS_TOML"
}

require_clean_tree() {
  if [[ -n "$(git -C "$PACKAGE_DIR" status --short --ignore-submodules)" ]]; then
    die "working tree is not clean in $PACKAGE_DIR; commit or stash changes first"
  fi
}

require_branch() {
  local branch
  branch="$(git -C "$PACKAGE_DIR" branch --show-current)"
  if [[ -z "$branch" ]]; then
    die "release helper must run from a branch, not detached HEAD"
  fi
  printf '%s\n' "$branch"
}

read_package_field() {
  local field="$1"
  local value
  value="$(awk -v field="$field" '
    BEGIN { in_package = 0 }
    /^\[.*\][[:space:]]*$/ {
      in_package = ($0 ~ /^\[package\][[:space:]]*$/)
      next
    }
    {
      if (in_package && $0 ~ ("^[[:space:]]*" field "[[:space:]]*=[[:space:]]*\"")) {
        line = $0
        sub(/^[[:space:]]*[A-Za-z0-9_-]+[[:space:]]*=[[:space:]]*\"/, "", line)
        sub(/\".*/, "", line)
        print line
        exit
      }
    }
  ' "$MARS_TOML")"

  [[ -n "$value" ]] || die "could not read [package].$field from $MARS_TOML"
  printf '%s\n' "$value"
}

read_current_version() {
  read_package_field "version"
}

validate_version() {
  local version="$1"
  [[ "$version" =~ ^[0-9]+(\.[0-9]+){2}([A-Za-z0-9._+-]*)?$ ]] || \
    die "version must look like X.Y.Z or X.Y.Zsuffix; got: $version"
}

next_version() {
  local bump="$1"
  local current="$2"
  IFS='.' read -r major minor patch <<<"$current"
  [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ && "$patch" =~ ^[0-9]+$ ]] || \
    die "automatic bumps require a plain semantic version, got: $current"

  case "$bump" in
    patch) patch=$((patch + 1)) ;;
    minor) minor=$((minor + 1)); patch=0 ;;
    major) major=$((major + 1)); minor=0; patch=0 ;;
    *) die "unknown bump kind: $bump" ;;
  esac

  printf '%s\n' "$major.$minor.$patch"
}

write_version() {
  local version="$1"
  local tmp
  tmp="$(mktemp "$PACKAGE_DIR/.mars.toml.tmp.XXXXXX")"

  awk -v version="$version" '
    BEGIN { in_package = 0; replaced = 0 }
    /^\[.*\][[:space:]]*$/ {
      in_package = ($0 ~ /^\[package\][[:space:]]*$/)
      print
      next
    }
    {
      if (in_package && !replaced && $0 ~ /^[[:space:]]*version[[:space:]]*=[[:space:]]*\"/) {
        print "version = \"" version "\""
        replaced = 1
        next
      }
      print
    }
    END {
      if (!replaced) {
        exit 1
      }
    }
  ' "$MARS_TOML" >"$tmp" || {
    rm -f "$tmp"
    die "failed to update [package].version in $MARS_TOML"
  }

  mv "$tmp" "$MARS_TOML"
}

main() {
  [[ $# -ge 2 ]] || {
    usage
    exit 1
  }

  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
  esac

  local package_input="$1"
  local target="$2"
  shift 2

  local push_remote=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --push)
        push_remote="1"
        shift
        ;;
      *)
        die "unknown argument: $1"
        ;;
    esac
  done

  PACKAGE_DIR="$(resolve_package_dir "$package_input")"
  MARS_TOML="$PACKAGE_DIR/mars.toml"

  require_package_layout
  require_clean_tree

  local branch
  branch="$(require_branch)"

  local package_name
  package_name="$(read_package_field "name")"

  local current_version
  current_version="$(read_current_version)"

  local next_version_value
  case "$target" in
    patch|minor|major)
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
  if git -C "$PACKAGE_DIR" rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    die "tag already exists: $tag"
  fi

  write_version "$next_version_value"

  git -C "$PACKAGE_DIR" add mars.toml
  git -C "$PACKAGE_DIR" commit -m "Release $package_name v$next_version_value"
  git -C "$PACKAGE_DIR" tag -a "$tag" -m "Release $package_name v$next_version_value"

  printf 'Released %s in %s on branch %s\n' "$next_version_value" "$package_input" "$branch"
  printf 'Created commit and tag %s\n' "$tag"

  if [[ -n "$push_remote" ]]; then
    git -C "$PACKAGE_DIR" push origin "$branch"
    git -C "$PACKAGE_DIR" push origin "$tag"
    printf 'Pushed branch %s and tag %s to origin\n' "$branch" "$tag"
  else
    printf 'Nothing pushed. Run:\n'
    printf '  git -C %s push origin %s\n' "$PACKAGE_DIR" "$branch"
    printf '  git -C %s push origin %s\n' "$PACKAGE_DIR" "$tag"
  fi
}

main "$@"
