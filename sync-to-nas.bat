@echo off
REM Refresh the read-only GitHub mirror on the NAS. Run after `git push`.
REM The mirror is a plain clone kept in sync with origin/main + all tags.
setlocal
set "NAS=G:\03-开发中心\03-活跃 active\Point-Translate-Glance"

if not exist "%NAS%\.git" (
    echo [*] first run - cloning mirror to the NAS ...
    git clone https://github.com/Joshuahu0129/Point-Translate-Glance.git "%NAS%" || exit /b 1
)

git -C "%NAS%" fetch --all --tags --prune || exit /b 1
git -C "%NAS%" reset --hard origin/main || exit /b 1

for /f "delims=" %%v in ('git -C "%NAS%" describe --tags --always') do set "VER=%%v"
for /f "delims=" %%h in ('git -C "%NAS%" rev-parse --short HEAD') do set "HASH=%%h"

> "%NAS%\MIRROR.txt" echo Point-Translate-Glance - GitHub 镜像备份（只读，勿在此开发）
>>"%NAS%\MIRROR.txt" echo(
>>"%NAS%\MIRROR.txt" echo 版本:   %VER%
>>"%NAS%\MIRROR.txt" echo 提交:   %HASH%
>>"%NAS%\MIRROR.txt" echo 同步于: %DATE% %TIME%
>>"%NAS%\MIRROR.txt" echo 源:     https://github.com/Joshuahu0129/Point-Translate-Glance
>>"%NAS%\MIRROR.txt" echo 开发在: E:\dev\point-translate-glance

echo [ok] mirror synced -> %VER% (%HASH%)
endlocal
