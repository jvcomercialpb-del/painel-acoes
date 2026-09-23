@echo off
chcp 65001 >nul
title Acoes - Painel com login
cd /d "%~dp0"
set PYTHONUTF8=1
set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist %PY% set PY=python
echo.
echo  Abrindo o app no navegador. Isso leva alguns segundos...
echo  Para FECHAR o app, feche esta janela preta.
echo.
%PY% app.py
if errorlevel 1 (
  echo.
  echo  Algo deu errado. Tire uma foto desta tela e peca ajuda.
  pause
)
