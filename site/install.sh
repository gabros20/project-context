#!/bin/sh
set -eu

DEFAULT_VERSION="v0.5.0"
REPOSITORY="https://github.com/gabros20/project-context.git"
version="${PROJECT_CONTEXT_VERSION:-$DEFAULT_VERSION}"
python_bin="${PROJECT_CONTEXT_PYTHON:-python3}"

if ! command -v git >/dev/null 2>&1; then
  echo "project-context requires Git." >&2
  exit 1
fi

if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "project-context requires Python 3.10 or newer (expected: $python_bin)." >&2
  exit 1
fi

if ! "$python_bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "project-context requires Python 3.10 or newer." >&2
  exit 1
fi

install_tmp="$(mktemp -d "${TMPDIR:-/tmp}/project-context.XXXXXX")"
cleanup() {
  rm -rf "$install_tmp"
}
trap cleanup EXIT HUP INT TERM

echo "Installing project-context $version..."
git clone --quiet --depth 1 --branch "$version" --single-branch \
  "$REPOSITORY" "$install_tmp/project-context"

"$python_bin" "$install_tmp/project-context/scripts/install.py" install "$@"

echo "project-context $version installed. Run: ctx --help"
