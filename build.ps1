# PDF EasyLock — PowerShell build script
# 推奨: Python 3.11 / 3.12 (64-bit)
# 事前準備:
#   py -3.11 -m venv .venv
#   .\.venv\Scripts\Activate.ps1
#   pip install -r requirements.txt

$ErrorActionPreference = 'Stop'
$Name = 'pdf-easylock'

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host "Error: pyinstaller が見つかりません。"
    Write-Host "  pip install -r requirements.txt を実行してから再度ビルドしてください。"
    exit 1
}

# PowerShell では行継続にバッククォート ` を使う (cmd.exe の ^ は使えない)
pyinstaller `
    --noconfirm --clean --onefile --noconsole `
    --name $Name `
    --collect-all tkinterdnd2 `
    --collect-all customtkinter `
    --collect-binaries pikepdf `
    --add-data "THIRD-PARTY-NOTICES.txt;." `
    main.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed."
    exit 1
}

# 配布物の隣にも NOTICES を置く (アプリ内表示 + 外部参照の両対応)
# $ErrorActionPreference = 'Stop' により失敗時は例外で抜ける
Copy-Item -Force THIRD-PARTY-NOTICES.txt dist\

Write-Host ""
Write-Host "Build OK:"
Write-Host "  dist\$Name.exe"
Write-Host "  dist\THIRD-PARTY-NOTICES.txt"
