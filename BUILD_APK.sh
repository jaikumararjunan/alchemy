#!/usr/bin/env bash
# =============================================================================
# Alchemy APK Builder
# =============================================================================
# Prerequisites (install on your machine before running):
#   - Node.js 18+  (https://nodejs.org)
#   - Java 17+     (https://adoptium.net)
#   - Android SDK  (install via Android Studio or sdkmanager)
#   - compileSdkVersion 34, buildTools 34.0.0
#
# One-time SDK install via sdkmanager:
#   sdkmanager "platforms;android-34" "build-tools;34.0.0"
#
# Usage:
#   1. Clone the repo and cd into it
#   2. Set ANDROID_HOME:  export ANDROID_HOME=$HOME/Android/Sdk
#   3. Run:  bash BUILD_APK.sh
#
# Output: mobile/android/app/build/outputs/apk/release/app-release.apk
# =============================================================================
set -e

ROOT=$(cd "$(dirname "$0")" && pwd)
MOBILE="$ROOT/mobile"
ANDROID="$MOBILE/android"

echo "==> Installing mobile JS dependencies..."
cd "$MOBILE"
npm install

echo ""
echo "==> Building release APK..."
cd "$ANDROID"
chmod +x gradlew

# Build a release APK (unsigned debug is also fine for sideloading)
./gradlew assembleRelease --no-daemon

APK=$(find "$ANDROID/app/build/outputs/apk" -name "*.apk" | head -1)
if [ -n "$APK" ]; then
    cp "$APK" "$ROOT/alchemy-release.apk"
    echo ""
    echo "======================================================"
    echo "  APK ready: $ROOT/alchemy-release.apk"
    echo "======================================================"
    echo ""
    echo "Install on device:"
    echo "  adb install $ROOT/alchemy-release.apk"
    echo ""
    echo "Or transfer the file to your phone and open it directly."
else
    echo "ERROR: APK not found after build"
    exit 1
fi
