#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m PyInstaller --noconfirm --clean --windowed \
  --name StarDanceSongSheet \
  --collect-all imageio_ffmpeg \
  --collect-all sounddevice \
  --collect-all onnxruntime \
  --add-data "assets:assets" \
  app.py

mkdir -p dist
hdiutil create -volname "StarDance SongSheet Studio" \
  -srcfolder dist/StarDanceSongSheet.app \
  -ov -format UDZO dist/StarDanceSongSheet-macOS.dmg
echo "Built dist/StarDanceSongSheet-macOS.dmg"
