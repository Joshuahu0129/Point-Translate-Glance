@echo off
REM Build Glance.exe (single file).
REM   - run setup-dev.bat first (it puts pyinstaller in .venv)
REM   - glance-dict.db must exist (it is committed; make_dict.py regenerates it)
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\pyinstaller.exe" (
    set "PYI=.venv\Scripts\pyinstaller.exe"
) else (
    set "PYI=pyinstaller"
)

%PYI% --noconfirm --clean --onefile --noconsole ^
  --name Glance ^
  --add-data "glance-dict.db;." ^
  --collect-binaries winsdk ^
  --hidden-import winsdk.windows.media.ocr ^
  --hidden-import winsdk.windows.globalization ^
  --hidden-import winsdk.windows.graphics.imaging ^
  --hidden-import winsdk.windows.storage.streams ^
  --hidden-import winsdk.windows.foundation ^
  --hidden-import PIL.ImageTk ^
  main.py

echo(
echo Done -^> dist\Glance.exe
endlocal
pause
