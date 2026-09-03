@echo off
REM One-shot dev setup: creates .venv (Python 3.12) and installs everything.
REM Run once after `git clone`.  Safe to re-run.
setlocal

cd /d "%~dp0"

REM --- pick a way to get Python 3.12 --------------------------------------
where uv >nul 2>nul
if %ERRORLEVEL%==0 goto :use_uv
if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    goto :use_uv
)

py -3.12 --version >nul 2>nul
if %ERRORLEVEL%==0 goto :use_py

echo(
echo [x] Need Python 3.12 (winsdk has no wheels for 3.13/3.14).
echo     Install uv:   powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
echo     or install Python 3.12 from https://www.python.org/downloads/
exit /b 1

:use_uv
echo [*] uv found - creating .venv with Python 3.12 ...
uv venv --python 3.12 .venv || exit /b 1
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt || exit /b 1
goto :done

:use_py
echo [*] py -3.12 found - creating .venv ...
py -3.12 -m venv .venv || exit /b 1
.venv\Scripts\python.exe -m pip install --upgrade pip >nul
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt || exit /b 1
goto :done

:done
echo(
echo [ok] Done.  Next:
echo        .venv\Scripts\activate
echo        python selftest.py       (quick end-to-end check)
echo        python main.py           (run Glance from source)
echo        build.bat                (build dist\Glance.exe)
echo(
echo     In Cursor/VSCode: pick the interpreter at  .venv\Scripts\python.exe
endlocal
