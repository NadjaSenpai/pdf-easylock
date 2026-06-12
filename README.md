# PDF EasyLock

PDFを暗号化（パスワード設定）または解除（パスワード削除）するシンプルなGUIツール。複数ファイルを一括で処理できます。

## 起動方法

1. 配布フォルダを開きます。
2. `pdf-easylock.exe` をダブルクリックします。

## 使い方

1. 画面にPDFをドラッグ&ドロップするか「ファイルを選択」で追加します。
2. 「処理内容」で「暗号化」または「解除」を選びます。
3. 必要なパスワードを入力します。
   - **暗号化**: 「新しいパスワード」
   - **解除**: 「現在のパスワード」
4. 出力先フォルダを選びます（未選択なら元のフォルダに保存）。
5. 右下の「暗号化開始 / 解除開始」を押します。

> **パスワードについて**
> - 4文字未満は拒否、8文字未満は警告が出ます（暗号化時）。
> - 互換性のため、PDFビューア間で問題が起きにくい **ASCII（半角英数字＋記号）** を推奨します。日本語など非ASCII文字はpikepdfがUTF-8として扱いますが、一部の古いPDFビューアでは開けない場合があります。

## 設定

右上の「設定」から以下を変更できます。

- 既定の出力先
- 既定で上書き
- 既定の暗号方式（AES-256 / AES-128）
- 外観テーマ（System / Light / Dark）
- 「ライセンス情報を表示」ボタンから第三者ライセンス全文を確認できます。

## ビルド方法

推奨環境: **Windows 10/11 (64-bit), Python 3.11 または 3.12**

シェルに応じてビルドスクリプトを使い分けてください。

### cmd.exe の場合

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
build.bat
```

### PowerShell の場合

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\build.ps1
```

> `build.bat` は cmd.exe の構文 (`^` 行継続) を使っているため、PowerShell から直接コマンドをコピペして実行すると「コマンドの構文が間違っています」エラーになります。PowerShell では `build.ps1` を使ってください。
>
> 初回 PowerShell 実行時に「このシステムではスクリプトの実行が無効になっているため」と出る場合は、次のコマンドで現セッションのみ許可します:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

`dist/pdf-easylock.exe` と `dist/THIRD-PARTY-NOTICES.txt` が生成されます。依存バージョン (pikepdf, tkinterdnd2, customtkinter, pyinstaller) は [`requirements.txt`](requirements.txt) で固定されています。

## FAQ

### Q. 「処理に失敗しました」と出ます

以下を確認してください。

- 出力先フォルダに書き込み権限があるか
- 出力先に同名ファイルが開かれていないか
- 解除の場合、現在のパスワードが正しいか

### Q. 出力先が見つかりません

出力先のフォルダが存在するか確認してください。存在しない場合は別のフォルダを選択してください。

### Q. 解除なのに新しいパスワードを要求される

「処理内容」が「暗号化」になっていないか確認してください。

### Q. どこに保存されたかわからない

出力先未選択の場合は、元のPDFと同じフォルダに保存されます。

## ライセンス

### 本ソフトウェア本体

PDF EasyLock の本体ソースコード (`main.py` 等) は **MIT License** で配布されています。詳細は [`LICENSE`](LICENSE) を参照してください。

### 第三者ライブラリ

本ソフトウェアは以下の第三者ライブラリを利用しています。ライセンス全文または参照先 URL は同梱の [`THIRD-PARTY-NOTICES.txt`](THIRD-PARTY-NOTICES.txt) を参照してください。アプリ内の「設定 → ライセンス情報を表示」からも閲覧できます。

| ライブラリ | ライセンス | カテゴリ |
| --- | --- | --- |
| pikepdf | MPL-2.0 | weak copyleft (改変ファイルの開示義務あり) |
| qpdf (pikepdf 同梱) | Apache-2.0 | permissive |
| libjpeg (pikepdf 同梱、プラットフォーム依存) | IJG | permissive |
| tkinterdnd2 | MIT | permissive |
| tkdnd (tkinterdnd2 同梱) | BSD-like / Petasis | permissive |
| customtkinter | MIT | permissive |
| Python | PSF License v2 | permissive |
| Tcl/Tk | BSD-style | permissive |
| PyInstaller bootloader | GPL-2.0 + bootloader exception | copyleft (exception により本アプリは MIT のまま再配布可) |

再配布の際は `THIRD-PARTY-NOTICES.txt` を必ず同梱してください。`build.bat` は exe と同じフォルダにこのファイルを自動配置します。
