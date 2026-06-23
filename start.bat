@echo off
REM ──────────────────────────────────────────────
REM The Trend Terminal — startup script (Windows)
REM Run this from the project root after setup.
REM ──────────────────────────────────────────────

echo ──────────────────────────────────────
echo  Starting The Trend Terminal
echo ──────────────────────────────────────

REM Load .env variables if file exists
if exist .env (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set %%A=%%B
  )
)

echo [1/3] Starting Python classifier service on :5100 ...
start "Classifier" python artifacts\api-server\python\classifier_service.py

echo [2/3] Starting Node API server on :8080 ...
start "API Server" pnpm --filter @workspace/api-server run dev

echo [3/3] Starting frontend on :5173 ...
start "Frontend" pnpm --filter @workspace/trend-terminal run dev

echo.
echo All services started in separate windows.
echo   Frontend   -^> http://localhost:5173
echo   API        -^> http://localhost:8080
echo   Classifier -^> http://localhost:5100
echo.
pause
