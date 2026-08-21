@echo off
setlocal
cd /d "%~dp0"
py -m pip install --upgrade pyinstaller
pyinstaller --noconfirm --clean LocalXIVAnalyzer.spec
if errorlevel 1 exit /b 1
echo Created: dist\LocalXIVAnalyzer.exe
pause
