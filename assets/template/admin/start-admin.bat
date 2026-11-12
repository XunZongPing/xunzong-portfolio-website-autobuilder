@echo off
rem ===========================================================================
rem  Portfolio admin launcher (Windows)
rem
rem  THIS FILE IS PURE ASCII ON PURPOSE. Do not add Chinese text here.
rem
rem  Why: cmd parses .bat with the OEM codepage (936/GBK on zh-CN). A UTF-8 CJK
rem  line does not merely display wrong -- it shifts the parser's file offset and
rem  the FOLLOWING lines get executed from the middle of the sentence (cmd prints
rem  "is not recognized as an internal or external command" for a fragment of the
rem  Chinese echo). "chcp 65001" at the top does not save you either: it works
rem  for one line and breaks on the next (tested). Chinese inside "( )" blocks is
rem  worse still, because the whole block is decoded before it runs.
rem
rem  So: every user-facing Chinese line is printed by server.py. Python on Windows
rem  writes through WriteConsoleW, so it renders correctly whatever the codepage.
rem
rem  What this script does: find a REAL python (the Windows Store stub answers
rem  "--version" and exits without running anything), clear the console, then hand
rem  over to server.py in this window. Closing the window stops the server.
rem ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY="

rem ---------------------------------------------------------------- 1. find python
if defined SITE_PY if exist "%SITE_PY%" set "PY=%SITE_PY%"

rem the managed runtime shipped with the WorkBuddy workspace
if not defined PY (
  for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\versions\*") do (
    if exist "%%D\python.exe" set "PY=%%D\python.exe"
  )
)

rem py launcher -> resolve to its real executable
if not defined PY (
  for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
)

rem python on PATH, skipping the WindowsApps stub
if not defined PY (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | find /i "WindowsApps" >nul || if not defined PY set "PY=%%P"
  )
)

rem ------------------------------------------------- 2. prove it actually works
rem A path that exists is not enough: the Store stub exists too. Import the very
rem module the server needs -- that is the only real test.
if defined PY (
  "%PY%" -c "import http.server" >nul 2>&1 || set "PY="
)

if not defined PY goto :no_python

rem ------------------------------------------------------------------ 3. run it
set "PORT=8848"
if defined SITE_PORT set "PORT=%SITE_PORT%"
rem SITE_OPEN=1 tells server.py "a human double-clicked this, open the browser".
set "SITE_OPEN=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
title Portfolio admin - port %PORT%

cls
"%PY%" -u "%~dp0server.py"
set "RC=%ERRORLEVEL%"

rem rc=3 means the port is already serving; server.py already printed the URL in
rem Chinese, here we just help by opening it.
if "%RC%"=="3" start "" http://127.0.0.1:%PORT%/

echo.
pause
exit /b %RC%

:no_python
echo.
echo   [ERROR] No usable Python 3 found.
echo.
echo   Install Python 3.8+ and tick "Add python.exe to PATH",
echo   or point SITE_PY at a real python.exe, e.g.
echo       set SITE_PY=C:\Python311\python.exe
echo.
pause
exit /b 1
