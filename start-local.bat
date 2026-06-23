@echo off
REM The Trend Terminal — Windows Starter
REM Run this to start all 3 services on Windows

echo ============================================
echo   The Trend Terminal — Windows Starter
echo ============================================
echo.

REM Check prerequisites
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js not found. Download from https://nodejs.org
echo    Install the "LTS" version, then restart your PC.
    pause
    exit /b 1
)

pnpm --version >nul 2>&1
if errorlevel 1 (
    echo ❌ pnpm not found. Run: npm install -g pnpm
    pause
    exit /b 1
)

python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found. Download from https://python.org
    pause
    exit /b 1
)

echo ✅ All prerequisites found!
echo.

REM Check if dependencies are installed
if not exist "node_modules" (
    echo 🔄 Installing dependencies (first time only, takes ~2 minutes)...
    call pnpm install
    if errorlevel 1 (
        echo ❌ pnpm install failed. Try running: npm install -g pnpm
        pause
        exit /b 1
    )
)

REM Check if Python dependencies are installed
python -c "import flask, pandas, requests, yfinance, bs4, lxml, feedparser" >nul 2>&1
if errorlevel 1 (
    echo 🔄 Installing Python dependencies (first time only)...
    python -m pip install -r artifacts\api-server\python\requirements.txt --quiet
    if errorlevel 1 (
        echo ❌ Python package install failed. Try: python -m pip install --upgrade pip
        pause
        exit /b 1
    )
)

echo.
echo 🚀 Starting The Trend Terminal...
echo.

REM Start Python stock data service in background
echo [1/3] Starting Python stock data service (port 5100)...
start /B python artifacts\api-server\python\stock_data_service.py

echo     Waiting 5 seconds for Python to start...
timeout /t 5 /nobreak >nul

REM Start API server in background
echo [2/3] Starting API server (port 8080)...
start /B cmd /c "pnpm --filter @workspace/api-server run dev"

echo     Waiting 5 seconds for API to start...
timeout /t 5 /nobreak >nul

REM Start frontend in background
echo [3/3] Starting frontend (port 3000)...
start /B cmd /c "pnpm --filter @workspace/trend-terminal run dev"

echo.
echo ============================================
echo   ✅ All services started!
echo.
echo   🌐 Open http://localhost:3000 in your browser
echo.
echo   📊 The app uses YOUR PC's WiFi to fetch:
echo      • Yahoo Finance (prices, charts)
echo      • Finviz (stock details)
echo      • Google News (sentiment)
echo.
echo   ⏰ Data refreshes automatically:
echo      • AI picks: daily at midnight
echo      • Sentiment: every 6 hours
echo      • Prices: every 5 minutes
echo.
echo   ⚠️  Press Ctrl+C in any of the terminal windows to stop
echo      Or close the command windows
echo ============================================
echo.
echo ⏳ Wait 30 seconds for the first data load...
echo     Then open http://localhost:3000
echo.

pause
