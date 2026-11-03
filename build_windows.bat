@echo off
setlocal
python -m pip install -r requirements.txt pyinstaller pywin32
if errorlevel 1 exit /b 1
if not exist icon.ico (
  echo Fehler: icon.ico wurde im Projektordner nicht gefunden.
  exit /b 1
)
if exist PyPack.spec del /f /q PyPack.spec
if exist build\PyPack rmdir /s /q build\PyPack
if exist dist\PyPack.exe del /f /q dist\PyPack.exe
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PyPack --icon icon.ico --exclude-module torch --exclude-module torchvision --exclude-module torchaudio --exclude-module sentence_transformers --exclude-module transformers --exclude-module timm --exclude-module numpy --exclude-module scipy --exclude-module sklearn --exclude-module numba --exclude-module pygame gui.py
if errorlevel 1 exit /b 1
echo PyPack.exe erstellt: dist\PyPack.exe
