"""PDF EasyLock — PDFの暗号化/解除を行うシンプルなGUIツール (CustomTkinter版)。"""
from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pikepdf

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


APP_NAME = "PDF EasyLock"
APP_VERSION = "1.0.0"

AES_VALUES = ("AES-256", "AES-128")
APPEARANCE_VALUES = ("System", "Light", "Dark")
PASSWORD_MIN_LEN = 4
PASSWORD_WEAK_LEN = 8

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


def settings_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / "PDFEasyLock"
    else:
        base = Path.home() / ".config" / "pdf-easylock"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return base / "settings.json"


def _canon_key(p: Path) -> str:
    """Windows は大文字小文字区別がないため正規化キーは小文字。"""
    s = str(p)
    return s.lower() if sys.platform == "win32" else s


def _resolve_safe(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:
        return p


def resource_path(name: str) -> Path:
    """PyInstaller --onefile 環境では sys._MEIPASS に展開される。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / name
    return Path(__file__).parent / name


def load_notices() -> str:
    p = resource_path("THIRD-PARTY-NOTICES.txt")
    try:
        return p.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return "THIRD-PARTY-NOTICES.txt が見つかりません。配布物に含めてください。"


@dataclass
class Settings:
    default_output_dir: str = ""
    default_overwrite: bool = False
    default_aes: str = "AES-256"
    appearance: str = "System"  # System / Light / Dark

    @classmethod
    def load(cls) -> "Settings":
        path = settings_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        s = cls()
        if isinstance(data.get("default_output_dir"), str):
            s.default_output_dir = data["default_output_dir"]
        if isinstance(data.get("default_overwrite"), bool):
            s.default_overwrite = data["default_overwrite"]
        if data.get("default_aes") in AES_VALUES:
            s.default_aes = data["default_aes"]
        if data.get("appearance") in APPEARANCE_VALUES:
            s.appearance = data["appearance"]
        return s

    def save(self) -> None:
        try:
            settings_path().write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass


def encryption_for(aes: str, password: str) -> pikepdf.Encryption:
    R = 6 if aes == "AES-256" else 4
    return pikepdf.Encryption(owner=password, user=password, R=R)


def _unique_path(out_dir: Path, original_name: str, suffix_hint: str) -> Path:
    """`out_dir/original_name` の重複を避けて `_encrypted`/`_decrypted` 名を付け、
    それでもぶつかる場合は `(2)` `(3)` …でユニーク化する。"""
    src = Path(original_name)
    base = src.stem
    ext = src.suffix
    candidate = out_dir / f"{base}_{suffix_hint}{ext}"
    if not candidate.exists():
        return candidate
    i = 2
    while True:
        candidate = out_dir / f"{base}_{suffix_hint} ({i}){ext}"
        if not candidate.exists():
            return candidate
        i += 1


def process_one(
    src: Path,
    mode: str,
    password: str,
    output_dir: Path | None,
    overwrite: bool,
    aes: str,
) -> Path:
    out_dir = output_dir if output_dir else src.parent
    out_path = out_dir / src.name
    suffix_hint = "encrypted" if mode == "encrypt" else "decrypted"

    if not overwrite:
        # 入力==出力 か、出力先に既存ファイルがある場合はユニーク名に逃がす
        if _resolve_safe(out_path) == _resolve_safe(src) or out_path.exists():
            out_path = _unique_path(out_dir, src.name, suffix_hint)

    # 入力ファイル自身を上書きする場合 pikepdf は allow_overwriting_input=True を要求する
    allow_overwrite = _resolve_safe(out_path) == _resolve_safe(src)

    if mode == "encrypt":
        with pikepdf.open(src, allow_overwriting_input=allow_overwrite) as pdf:
            pdf.save(out_path, encryption=encryption_for(aes, password))
    else:
        with pikepdf.open(
            src, password=password, allow_overwriting_input=allow_overwrite
        ) as pdf:
            pdf.save(out_path)
    return out_path


# CustomTkinter + tkinterdnd2 を両立させるためのラッパー
if DND_AVAILABLE:
    class _Tk(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    class _Tk(ctk.CTk):
        pass


class FileRow(ctk.CTkFrame):
    def __init__(self, master, path: Path, on_remove):
        super().__init__(master, corner_radius=8, fg_color=("gray92", "gray22"))
        self.path = path
        self.canon_key = _canon_key(_resolve_safe(path))
        self.on_remove = on_remove

        self.grid_columnconfigure(1, weight=1)
        icon = ctk.CTkLabel(self, text="📄", width=24, font=ctk.CTkFont(size=14))
        icon.grid(row=0, column=0, padx=(10, 4), pady=6)

        text = path.name if len(str(path)) <= 60 else f"…{str(path)[-58:]}"
        label = ctk.CTkLabel(self, text=text, anchor="w", font=ctk.CTkFont(size=12))
        label.grid(row=0, column=1, sticky="ew", padx=4, pady=6)

        remove = ctk.CTkButton(
            self, text="×", width=28, height=24, corner_radius=12,
            fg_color="transparent", hover_color=("gray85", "gray30"),
            text_color=("gray30", "gray70"),
            command=self._remove,
        )
        remove.grid(row=0, column=2, padx=(4, 8), pady=4)

    def _remove(self):
        self.on_remove(self)


class App:
    def __init__(self) -> None:
        self.settings = Settings.load()
        ctk.set_appearance_mode(self.settings.appearance)

        self.root = _Tk()
        self.root.title(APP_NAME)
        self.root.geometry("680x720")
        self.root.minsize(580, 640)

        self.mode = "encrypt"
        self.file_rows: list[FileRow] = []
        self.processing = False

        self._build_ui()
        self._update_empty_state()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        if self.processing:
            ok = messagebox.askyesno(
                APP_NAME,
                "処理中です。本当に終了しますか？\n"
                "現在書き込み中のPDFが破損する可能性があります。",
            )
            if not ok:
                return
        self.root.destroy()

    def _build_ui(self) -> None:
        root = self.root
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        # ---- Header ----
        header = ctk.CTkFrame(root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text=APP_NAME,
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            header, text="⚙  設定", width=80, height=32,
            corner_radius=16,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            text_color=("gray20", "gray85"),
            hover_color=("gray90", "gray25"),
            command=self._open_settings,
        ).grid(row=0, column=1, sticky="e")

        # ---- File area (scrollable list + empty hint overlay) ----
        self.file_container = ctk.CTkFrame(root, corner_radius=14, border_width=2,
                                           border_color=("gray80", "gray30"))
        self.file_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=8)
        self.file_container.grid_columnconfigure(0, weight=1)
        self.file_container.grid_rowconfigure(0, weight=1)

        self.empty_label = ctk.CTkLabel(
            self.file_container,
            text="📄  PDFをここにドロップ\n\nまたは下の「ファイルを選択」をクリック",
            font=ctk.CTkFont(size=14),
            text_color=("gray50", "gray60"),
        )

        self.file_list = ctk.CTkScrollableFrame(
            self.file_container, fg_color="transparent",
            corner_radius=10,
        )
        self.file_list.grid_columnconfigure(0, weight=1)

        if DND_AVAILABLE:
            self.file_container.drop_target_register(DND_FILES)
            self.file_container.dnd_bind("<<Drop>>", self._on_drop)
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)

        # ---- Toolbar ----
        toolbar = ctk.CTkFrame(root, fg_color="transparent")
        toolbar.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 12))
        ctk.CTkButton(
            toolbar, text="ファイルを選択", height=36, corner_radius=18,
            command=self._add_files,
        ).pack(side="left")
        ctk.CTkButton(
            toolbar, text="クリア", height=36, corner_radius=18,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            text_color=("gray20", "gray85"),
            hover_color=("gray90", "gray25"),
            command=self._clear_files,
        ).pack(side="left", padx=(8, 0))
        if not DND_AVAILABLE:
            ctk.CTkLabel(toolbar, text="D&D 無効 (tkinterdnd2 未導入)",
                         text_color="gray").pack(side="left", padx=10)

        # ---- Mode segmented button ----
        mode_row = ctk.CTkFrame(root, fg_color="transparent")
        mode_row.grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 8))
        ctk.CTkLabel(mode_row, text="処理内容", font=ctk.CTkFont(size=12),
                     text_color=("gray35", "gray70")).pack(anchor="w", pady=(0, 4))
        self.mode_seg = ctk.CTkSegmentedButton(
            mode_row, values=["暗号化", "解除"],
            command=self._on_mode_change,
            height=36, corner_radius=12,
        )
        self.mode_seg.set("暗号化")
        self.mode_seg.pack(fill="x")

        # ---- Password ----
        pw_row = ctk.CTkFrame(root, fg_color="transparent")
        pw_row.grid(row=4, column=0, sticky="ew", padx=20, pady=8)
        self.pw_label = ctk.CTkLabel(pw_row, text="新しいパスワード",
                                     font=ctk.CTkFont(size=12),
                                     text_color=("gray35", "gray70"))
        self.pw_label.pack(anchor="w", pady=(0, 4))
        self.pw_entry = ctk.CTkEntry(pw_row, show="●", height=36, corner_radius=10,
                                     font=ctk.CTkFont(size=13))
        self.pw_entry.pack(fill="x")

        # ---- Output dir ----
        out_row = ctk.CTkFrame(root, fg_color="transparent")
        out_row.grid(row=5, column=0, sticky="ew", padx=20, pady=8)
        ctk.CTkLabel(out_row, text="出力先フォルダ (空欄なら元の場所)",
                     font=ctk.CTkFont(size=12),
                     text_color=("gray35", "gray70")).pack(anchor="w", pady=(0, 4))
        out_inner = ctk.CTkFrame(out_row, fg_color="transparent")
        out_inner.pack(fill="x")
        self.out_entry = ctk.CTkEntry(out_inner, height=36, corner_radius=10,
                                      font=ctk.CTkFont(size=13))
        self.out_entry.pack(side="left", fill="x", expand=True)
        if self.settings.default_output_dir:
            self.out_entry.insert(0, self.settings.default_output_dir)
        ctk.CTkButton(
            out_inner, text="参照…", width=70, height=36, corner_radius=10,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            text_color=("gray20", "gray85"),
            hover_color=("gray90", "gray25"),
            command=self._choose_output_dir,
        ).pack(side="left", padx=(8, 0))

        # ---- Footer: status + run ----
        footer = ctk.CTkFrame(root, fg_color="transparent")
        footer.grid(row=6, column=0, sticky="ew", padx=20, pady=(12, 18))
        footer.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(
            footer, text="待機中", font=ctk.CTkFont(size=12),
            text_color=("gray45", "gray60"),
        )
        self.status_label.grid(row=0, column=0, sticky="w")
        self.run_button = ctk.CTkButton(
            footer, text="暗号化開始", width=160, height=44, corner_radius=22,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._run,
        )
        self.run_button.grid(row=0, column=1, sticky="e")

    # ---- Mode ----
    def _on_mode_change(self, value: str) -> None:
        self.mode = "encrypt" if value == "暗号化" else "decrypt"
        if self.mode == "encrypt":
            self.pw_label.configure(text="新しいパスワード")
            self.run_button.configure(text="暗号化開始")
        else:
            self.pw_label.configure(text="現在のパスワード")
            self.run_button.configure(text="解除開始")

    # ---- File list ----
    def _update_empty_state(self) -> None:
        if self.file_rows:
            self.empty_label.grid_forget()
            self.file_list.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        else:
            self.file_list.grid_forget()
            self.empty_label.grid(row=0, column=0)

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="PDFを選択", filetypes=[("PDF", "*.pdf")],
        )
        for p in paths:
            self._add_file(Path(p))

    def _add_file(self, p: Path) -> None:
        if p.suffix.lower() != ".pdf" or not p.is_file():
            return
        key = _canon_key(_resolve_safe(p))
        if any(r.canon_key == key for r in self.file_rows):
            return
        row = FileRow(self.file_list, p, on_remove=self._remove_row)
        row.grid(row=len(self.file_rows), column=0, sticky="ew", padx=4, pady=3)
        self.file_rows.append(row)
        self._update_empty_state()

    def _remove_row(self, row: FileRow) -> None:
        row.destroy()
        self.file_rows.remove(row)
        # re-layout remaining
        for i, r in enumerate(self.file_rows):
            r.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
        self._update_empty_state()

    def _clear_files(self) -> None:
        for r in self.file_rows:
            r.destroy()
        self.file_rows.clear()
        self._update_empty_state()

    def _on_drop(self, event) -> None:
        # Tk のリストパーサに任せる ({brace} escape, Windows path 等を正しく扱う)
        try:
            items = self.root.tk.splitlist(event.data)
        except Exception:
            items = [event.data]
        for p in items:
            self._add_file(Path(p))

    def _choose_output_dir(self) -> None:
        d = filedialog.askdirectory(title="出力先フォルダを選択")
        if d:
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, d)

    # ---- Run ----
    def _run(self) -> None:
        if self.processing:
            return
        if not self.file_rows:
            messagebox.showwarning(APP_NAME, "PDFファイルが選択されていません。")
            return
        pw = self.pw_entry.get()
        if not pw:
            messagebox.showwarning(APP_NAME, "パスワードを入力してください。")
            return
        if len(pw) < PASSWORD_MIN_LEN:
            messagebox.showwarning(
                APP_NAME,
                f"パスワードは {PASSWORD_MIN_LEN} 文字以上で入力してください。",
            )
            return
        out_dir_str = self.out_entry.get().strip()
        out_dir = Path(out_dir_str) if out_dir_str else None
        if out_dir and not out_dir.is_dir():
            messagebox.showerror(APP_NAME, "出力先フォルダが見つかりません。")
            return
        if self.mode == "encrypt" and len(pw) < PASSWORD_WEAK_LEN:
            ok = messagebox.askyesno(
                APP_NAME,
                f"パスワードが短いため（{len(pw)} 文字）総当たり攻撃に弱くなります。\n"
                "このまま続行しますか？",
            )
            if not ok:
                return

        # バッチ実行中に設定ダイアログで値が変わっても影響を受けないよう snapshot を取る
        overwrite = self.settings.default_overwrite
        aes = self.settings.default_aes

        files = [r.path for r in self.file_rows]
        self.processing = True
        self.run_button.configure(state="disabled", text="処理中…")
        self.status_label.configure(text=f"0 / {len(files)} 処理中…")

        threading.Thread(
            target=self._do_process,
            args=(files, self.mode, pw, out_dir, overwrite, aes),
            daemon=True,
        ).start()

    def _do_process(self, files, mode, password, out_dir, overwrite, aes):
        ok, fail = 0, []
        for i, src in enumerate(files, 1):
            try:
                process_one(
                    src=src, mode=mode, password=password,
                    output_dir=out_dir,
                    overwrite=overwrite,
                    aes=aes,
                )
                ok += 1
            except pikepdf.PasswordError:
                fail.append((src.name, "パスワードが正しくありません"))
            except Exception as e:
                fail.append((src.name, str(e)))
            self.root.after(0, lambda i=i, n=len(files): self.status_label.configure(
                text=f"{i} / {n} 処理中…"
            ))
        self.root.after(0, self._finish, ok, fail)

    def _finish(self, ok: int, fail: list) -> None:
        self.processing = False
        run_text = "暗号化開始" if self.mode == "encrypt" else "解除開始"
        self.run_button.configure(state="normal", text=run_text)
        self.status_label.configure(text=f"完了: 成功 {ok} 件 / 失敗 {len(fail)} 件")
        if fail:
            detail = "\n".join(f"・{name}: {err}" for name, err in fail[:10])
            if len(fail) > 10:
                detail += f"\n…他 {len(fail) - 10} 件"
            messagebox.showerror(APP_NAME, f"一部のファイルで処理に失敗しました。\n\n{detail}")
        else:
            messagebox.showinfo(APP_NAME, f"{ok} 件のPDFを処理しました。")

    # ---- Settings dialog ----
    def _open_settings(self) -> None:
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("設定")
        dlg.geometry("520x430")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.grid_columnconfigure(0, weight=1)

        body = ctk.CTkFrame(dlg, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=24, pady=20)
        body.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(body, text="設定", font=ctk.CTkFont(size=18, weight="bold")
                     ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))

        # default output dir
        ctk.CTkLabel(body, text="既定の出力先").grid(row=1, column=0, sticky="w", pady=6)
        out_entry = ctk.CTkEntry(body, height=32, corner_radius=8)
        out_entry.insert(0, self.settings.default_output_dir)
        out_entry.grid(row=1, column=1, sticky="ew", padx=(8, 4), pady=6)
        ctk.CTkButton(
            body, text="…", width=36, height=32, corner_radius=8,
            command=lambda: self._pick_into(out_entry),
        ).grid(row=1, column=2, pady=6)

        # overwrite
        overwrite_var = ctk.BooleanVar(value=self.settings.default_overwrite)
        ctk.CTkCheckBox(body, text="既定で上書き", variable=overwrite_var
                        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=12)

        # AES
        ctk.CTkLabel(body, text="既定の暗号方式").grid(row=3, column=0, sticky="w", pady=6)
        aes_seg = ctk.CTkSegmentedButton(body, values=["AES-256", "AES-128"], height=32)
        aes_seg.set(self.settings.default_aes)
        aes_seg.grid(row=3, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=6)

        # appearance
        ctk.CTkLabel(body, text="外観テーマ").grid(row=4, column=0, sticky="w", pady=6)
        appearance_seg = ctk.CTkSegmentedButton(body, values=["System", "Light", "Dark"], height=32,
                                                command=lambda v: ctk.set_appearance_mode(v))
        appearance_seg.set(self.settings.appearance)
        appearance_seg.grid(row=4, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=6)

        # license info link
        ctk.CTkButton(
            body, text="ライセンス情報を表示", height=32, corner_radius=8,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            text_color=("gray20", "gray85"),
            hover_color=("gray90", "gray25"),
            command=self._show_licenses,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(16, 0))

        # buttons
        btn = ctk.CTkFrame(dlg, fg_color="transparent")
        btn.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 20))
        btn.grid_columnconfigure(0, weight=1)

        def save_and_close():
            self.settings.default_output_dir = out_entry.get()
            self.settings.default_overwrite = overwrite_var.get()
            self.settings.default_aes = aes_seg.get()
            self.settings.appearance = appearance_seg.get()
            self.settings.save()
            ctk.set_appearance_mode(self.settings.appearance)
            if not self.out_entry.get() and self.settings.default_output_dir:
                self.out_entry.insert(0, self.settings.default_output_dir)
            dlg.destroy()

        def cancel():
            ctk.set_appearance_mode(self.settings.appearance)
            dlg.destroy()

        ctk.CTkButton(
            btn, text="キャンセル", width=100, height=36, corner_radius=18,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray40"),
            text_color=("gray20", "gray85"),
            hover_color=("gray90", "gray25"),
            command=cancel,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(btn, text="保存", width=100, height=36, corner_radius=18,
                      command=save_and_close).grid(row=0, column=2)

    def _pick_into(self, entry: ctk.CTkEntry) -> None:
        d = filedialog.askdirectory()
        if d:
            entry.delete(0, "end")
            entry.insert(0, d)

    # ---- License dialog ----
    def _show_licenses(self) -> None:
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("ライセンス情報")
        dlg.geometry("720x560")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.grid_columnconfigure(0, weight=1)
        dlg.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            dlg, text="第三者ライセンス",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 8))

        textbox = ctk.CTkTextbox(
            dlg, corner_radius=10, font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word",
        )
        textbox.grid(row=1, column=0, sticky="nsew", padx=24, pady=8)
        textbox.insert("0.0", load_notices())
        textbox.configure(state="disabled")

        btn = ctk.CTkFrame(dlg, fg_color="transparent")
        btn.grid(row=2, column=0, sticky="e", padx=24, pady=(8, 20))
        ctk.CTkButton(
            btn, text="閉じる", width=100, height=36, corner_radius=18,
            command=dlg.destroy,
        ).pack()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    App().run()


if __name__ == "__main__":
    main()
