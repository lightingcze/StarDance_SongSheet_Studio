$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name StarDanceSongSheet `
  --collect-all imageio_ffmpeg `
  --collect-all sounddevice `
  --add-data "assets;assets" `
  app.py

Write-Host "Built dist/StarDanceSongSheet.exe"
