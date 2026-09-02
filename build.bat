@echo off
REM Build Glance.exe (single file). Requires:  pip install pyinstaller
REM glance-dict.db must already exist (run make_dict.py once to create it).

pyinstaller --noconfirm --clean --onefile --noconsole ^
  --name Glance ^
  --add-data "glance-dict.db;." ^
  --collect-binaries winsdk ^
  --hidden-import winsdk.windows.media.ocr ^
  --hidden-import winsdk.windows.globalization ^
  --hidden-import winsdk.windows.graphics.imaging ^
  --hidden-import winsdk.windows.storage.streams ^
  --hidden-import winsdk.windows.foundation ^
  main.py

echo.
echo Done -> dist\Glance.exe
pause
