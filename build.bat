@echo off
REM PDF EasyLock — Windows build script (cmd.exe 用)
REM PowerShell から起動する場合は build.ps1 を使ってください
REM   cmd.exe>     build.bat
REM   PowerShell>  .\build.ps1
REM
REM 推奨: Python 3.11 / 3.12 (64-bit)
REM 事前準備:
REM   py -3.11 -m venv .venv
REM   .venv\Scripts\activate
REM   pip install -r requirements.txt

setlocal
set NAME=pdf-easylock

REM PyInstaller の存在チェック (バージョンは requirements.txt で固定)
where pyinstaller >nul 2>&1
if errorlevel 1 (
  echo Error: pyinstaller が見つかりません。
  echo   pip install -r requirements.txt を実行してから再度ビルドしてください。
  exit /b 1
)

pyinstaller --noconfirm --clean ^
  --onefile ^
  --noconsole ^
  --name %NAME% ^
  --collect-all tkinterdnd2 ^
  --collect-all customtkinter ^
  --collect-binaries pikepdf ^
  --add-data "THIRD-PARTY-NOTICES.txt;." ^
  main.py

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

REM 配布物の隣にもNOTICESを置く (アプリ内表示+外部参照の両対応)
copy /Y THIRD-PARTY-NOTICES.txt dist\ >nul
if errorlevel 1 (
  echo Error: THIRD-PARTY-NOTICES.txt のコピーに失敗しました。
  echo ライセンスファイル同梱は配布要件のため、ビルドを失敗扱いにします。
  exit /b 1
)

echo.
echo Build OK:
echo   dist\%NAME%.exe
echo   dist\THIRD-PARTY-NOTICES.txt
endlocal
