@echo off
setlocal

set "ROOT=%~dp0"
set "VENV_PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" set "VENV_PYTHON=%ROOT%.venv-codex\Scripts\python.exe"
set "PUBLIC_WEB_DIR=%ROOT%public-web"
set "FRONTEND_DIR=%ROOT%frontend"

if "%~1"=="" goto :help

if /I "%~1"=="setup" (
  call "%ROOT%install.cmd"
  exit /b %ERRORLEVEL%
)

if /I "%~1"=="check" goto :check

if /I "%~1"=="public-web" (
  if not exist "%PUBLIC_WEB_DIR%\package.json" (
    echo Missing %PUBLIC_WEB_DIR%\package.json
    exit /b 1
  )
  pushd "%PUBLIC_WEB_DIR%"
  call npm.cmd %2 %3 %4 %5 %6 %7 %8 %9
  set "EXIT_CODE=%ERRORLEVEL%"
  popd
  exit /b %EXIT_CODE%
)

if /I "%~1"=="frontend" (
  if not exist "%FRONTEND_DIR%\package.json" (
    echo Missing %FRONTEND_DIR%\package.json
    exit /b 1
  )
  pushd "%FRONTEND_DIR%"
  call npm.cmd %2 %3 %4 %5 %6 %7 %8 %9
  set "EXIT_CODE=%ERRORLEVEL%"
  popd
  exit /b %EXIT_CODE%
)

if not exist "%VENV_PYTHON%" (
  echo Missing %VENV_PYTHON%
  echo Run .\install.cmd first.
  exit /b 1
)

if /I "%~1"=="python" (
  "%VENV_PYTHON%" %2 %3 %4 %5 %6 %7 %8 %9
  exit /b %ERRORLEVEL%
)

if /I "%~1"=="pip" (
  "%VENV_PYTHON%" -m pip %2 %3 %4 %5 %6 %7 %8 %9
  exit /b %ERRORLEVEL%
)

if /I "%~1"=="pytest" (
  set "PYTHONPATH=%ROOT%backend"
  "%VENV_PYTHON%" -m pytest %2 %3 %4 %5 %6 %7 %8 %9
  exit /b %ERRORLEVEL%
)

if /I "%~1"=="backend" (
  set "PYTHONPATH=%ROOT%backend"
  "%VENV_PYTHON%" "%ROOT%backend\src\main.py" %2 %3 %4 %5 %6 %7 %8 %9
  exit /b %ERRORLEVEL%
)

echo Unknown command: %1
echo.
goto :help

:check
echo Repo root: %ROOT%
if exist "%VENV_PYTHON%" (
  "%VENV_PYTHON%" -c "import sys; print('python=' + sys.executable); print('version=' + sys.version.split()[0])"
) else (
  echo python=missing
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo npm.cmd=missing
) else (
  for /f "delims=" %%I in ('where npm.cmd') do (
    echo npm.cmd=%%I
    goto :node_check
  )
)

:node_check
where node >nul 2>nul
if errorlevel 1 (
  echo node=missing
) else (
  for /f "delims=" %%I in ('where node') do (
    echo node=%%I
    goto :env_check
  )
)

:env_check
if exist "%ROOT%.env" (
  echo .env=present
) else (
  echo .env=missing
)
if exist "%PUBLIC_WEB_DIR%\.env.local" (
  echo public-web/.env.local=present
) else (
  echo public-web/.env.local=missing
)
exit /b 0

:help
echo Usage:
echo   .\dev.cmd setup
echo   .\dev.cmd check
echo   .\dev.cmd python -m compileall backend\packages backend\src
echo   .\dev.cmd pip list
echo   .\dev.cmd pytest tests\test_crypto_pipeline.py -q
echo   .\dev.cmd backend public-worker-doctor
echo   .\dev.cmd public-web install
echo   .\dev.cmd public-web run dev
echo   .\dev.cmd public-web run lint
echo   .\dev.cmd public-web run build
echo   .\dev.cmd frontend install
exit /b 0
