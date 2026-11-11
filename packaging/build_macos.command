#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
cmake -S native -B build/muscriptor -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/muscriptor --target muscriptor_cli --parallel
python3 -m PyInstaller --noconfirm --clean --windowed \
  --name StarDanceSongSheet \
  --collect-all imageio_ffmpeg \
  --collect-all sounddevice \
  --collect-all onnxruntime \
  --add-binary "build/muscriptor/bin/muscriptor_cli:native" \
  --add-data "assets:assets" \
  app.py

mkdir -p dist
hdiutil create -volname "StarDance SongSheet Studio" \
  -srcfolder dist/StarDanceSongSheet.app \
  -ov -format UDZO dist/StarDanceSongSheet-macOS.dmg
echo "Built dist/StarDanceSongSheet-macOS.dmg"
