@echo off
setlocal
cd /d "%~dp0"
start "StarDance SongSheet Web Server" cmd /k "python -m http.server 8765 --bind 127.0.0.1"
timeout /t 1 /nobreak > nul
start "" "http://127.0.0.1:8765/web/"
endlocal
