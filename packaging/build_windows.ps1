$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cmake -S native -B build/muscriptor -G "Visual Studio 17 2022" -A x64 -T ClangCL -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { throw "MuScriptor CMake configure failed" }
cmake --build build/muscriptor --config Release --target muscriptor_cli -- /m
if ($LASTEXITCODE -ne 0) { throw "MuScriptor native engine build failed" }
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name StarDanceSongSheet `
  --collect-all imageio_ffmpeg `
  --collect-all sounddevice `
  --collect-all onnxruntime `
  --add-binary "build/muscriptor/bin/Release/muscriptor_cli.exe;native" `
  --add-data "assets;assets" `
  app.py

Write-Host "Built dist/StarDanceSongSheet.exe"
