#!/usr/bin/env bash
# Build a RedForge AppImage from the staged release.
# Requires: appimagetool on PATH (https://github.com/AppImage/AppImageKit),
#           the release at releases/redforge-<version>/ (run build_release.py first).
# Runtime: end users need Python 3.11+ and Ollama. Node.js is NOT required.
set -euo pipefail

VERSION="$(cat "$(dirname "$0")/../../VERSION")"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$ROOT/releases/redforge-$VERSION"
APPDIR="$ROOT/releases/RedForge.AppDir"

[ -d "$STAGE" ] || { echo "Run: python scripts/build_release.py first"; exit 1; }
command -v appimagetool >/dev/null || { echo "appimagetool not found on PATH"; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -r "$STAGE/." "$APPDIR/usr/bin/redforge/"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="$HERE/usr/bin/redforge/cli:${PYTHONPATH:-}"
cd "$HERE/usr/bin/redforge"
exec python3 -m redforge start "$@"
EOF
chmod +x "$APPDIR/AppRun"

cp "$(dirname "$0")/redforge.desktop" "$APPDIR/redforge.desktop"
cp "$(dirname "$0")/redforge.png" "$APPDIR/redforge.png"

ARCH=x86_64 appimagetool "$APPDIR" "$ROOT/releases/RedForge-$VERSION-x86_64.AppImage"
echo "✓ AppImage → releases/RedForge-$VERSION-x86_64.AppImage"
