#!/usr/bin/env bash
# Convenience wrapper for running without nix.
# With nix, just use: nix run
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python start.py "$@"
