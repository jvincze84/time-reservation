#!/usr/bin/env bash
# Create an annotated release tag from the current commit and push it.
#
# Usage:
#   scripts/release.sh               # bump patch: v1.2.3 -> v1.2.4 (first release: v0.1.0)
#   scripts/release.sh minor         # v1.2.3 -> v1.3.0
#   scripts/release.sh major         # v1.2.3 -> v2.0.0
#   scripts/release.sh v1.5.0        # explicit version
#   scripts/release.sh minor -m "Duplicate finder"   # custom tag message
#   scripts/release.sh -n            # dry run: show what would happen
#   scripts/release.sh -y            # no confirmation prompt (non-interactive use)
set -euo pipefail

cd "$(dirname "$0")/.."

bump="patch"
message=""
dry_run=0
assume_yes=0
remote="origin"

while [[ $# -gt 0 ]]; do
  case "$1" in
    major|minor|patch) bump="$1" ;;
    v[0-9]*.[0-9]*.[0-9]*) bump="$1" ;;
    -m|--message) message="${2:?missing message}"; shift ;;
    -n|--dry-run) dry_run=1 ;;
    -y|--yes) assume_yes=1 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown argument: $1 (see --help)" >&2; exit 1 ;;
  esac
  shift
done

die() { echo "Error: $*" >&2; exit 1; }

# --- sanity checks -----------------------------------------------------------
git rev-parse --git-dir >/dev/null 2>&1 || die "not a git repository"

branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "$branch" != "HEAD" ]] || die "detached HEAD - check out a branch first"

if [[ -n "$(git status --porcelain)" ]]; then
  git status --short
  die "uncommitted changes - commit or stash them first (the tag would not include them)"
fi

git fetch --quiet --tags "$remote" || die "cannot fetch from '$remote'"

# --- work out the new version ------------------------------------------------
last="$(git tag --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -n1)"

if [[ "$bump" == v* ]]; then
  new="$bump"
elif [[ -z "$last" ]]; then
  new="v0.1.0"
else
  IFS=. read -r major minor patch <<<"${last#v}"
  case "$bump" in
    major) new="v$((major + 1)).0.0" ;;
    minor) new="v${major}.$((minor + 1)).0" ;;
    patch) new="v${major}.${minor}.$((patch + 1))" ;;
  esac
fi

git rev-parse -q --verify "refs/tags/$new" >/dev/null && die "tag $new already exists"

if [[ -n "$last" ]] && [[ "$(git rev-list -n1 "$last")" == "$(git rev-parse HEAD)" ]]; then
  die "HEAD is already tagged as $last - nothing new to release"
fi

# --- changelog for the tag message -------------------------------------------
range="${last:+$last..}HEAD"
changes="$(git log --no-merges --pretty='- %s' "$range")"
[[ -n "$message" ]] || message="Release $new"
tag_msg="$message

Changes since ${last:-the beginning}:
$changes"

echo "Branch:   $branch"
echo "Previous: ${last:-(none)}"
echo "New tag:  $new"
echo
echo "$tag_msg"
echo

if [[ $dry_run -eq 1 ]]; then
  echo "(dry run - nothing created)"
  exit 0
fi

if [[ $assume_yes -eq 0 ]]; then
  [[ -t 0 ]] || die "no terminal to ask for confirmation - use -y to skip it"
  read -r -p "Create and push $new? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }
fi

# --- tag + push ----------------------------------------------------------------
git tag -a "$new" -m "$tag_msg"
git push "$remote" "$branch"
git push "$remote" "$new"

url="$(git remote get-url "$remote" | sed -E 's#^git@github.com:#https://github.com/#; s#\.git$##')"
echo
echo "Done: $new pushed."
if [[ "$url" == https://github.com/* ]]; then
  echo "Build (Docker image): $url/actions"
  echo "Create a GitHub release from it: $url/releases/new?tag=$new"
fi
