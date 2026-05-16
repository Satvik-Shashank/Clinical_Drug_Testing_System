@echo off
REM =====================================================================
REM  Clinical Drug Testing System — Start Script
REM  Starts both the FastAPI backend and Vite frontend dev servers
REM =====================================================================

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║     Clinical Drug Testing System — Starting...          ║
echo  ║                                                         ║
echo  ║     Backend  : http://localhost:8000                     ║
echo  ║     Frontend : http://localhost:5173                     ║
echo  ║     API Docs : http://localhost:8000/docs                ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

REM Start backend in a new terminal
echo [1/2] Starting FastAPI backend on port 8000...
start "CDTS Backend" cmd /k "cd backend && python main.py"

REM Wait a moment for backend to initialize
timeout /t 3 /nobreak > nul

REM Start frontend in a new terminal
echo [2/2] Starting Vite frontend on port 5173...
start "CDTS Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo  Both servers are starting in separate windows.
echo  Press any key to exit this launcher...
pause > nul
