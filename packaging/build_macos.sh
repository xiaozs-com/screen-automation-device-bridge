#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="${1:-$(uname -m)}"
case "$ARCH" in
  x86_64) TARGET=x86_64-apple-darwin; PLATFORM=macos-x64 ;;
  arm64|aarch64) TARGET=aarch64-apple-darwin; PLATFORM=macos-arm64 ;;
  *) echo "Use x86_64 or arm64" >&2; exit 2 ;;
esac
if [[ $(uname -s) != Darwin ]]; then echo "Run this script on macOS" >&2; exit 2; fi
cargo test --locked --manifest-path "$ROOT/native/Cargo.toml"
cargo build --locked --release --target "$TARGET" --manifest-path "$ROOT/native/Cargo.toml"
python3 "$ROOT/packaging/package_macos.py" "$PLATFORM"
