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

# Each pair supplies the light and dark appearance colors.
BG = ("#F3F6FA", "#10151E")
SURFACE = ("#FFFFFF", "#191F2B")
INSET = ("#F7F9FC", "#131923")
BORDER = ("#DFE5EE", "#303A4B")
TEXT = ("#182438", "#EDF2FA")
MUTED = ("#58677C", "#A2AFC2")
ACCENT = ("#087F8C", "#39C6CB")
ACCENT_HOVER = ("#066B76", "#65D5D8")
ACCENT_TEXT = ("#FFFFFF", "#10252B")
SOFT = ("#E5F3F4", "#20383F")
HOVER = ("#EAF0F6", "#263143")

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")
if sys.platform == "win32":
    ctk.ThemeManager.theme["CTkFont"]["family"] = "Yu Gothic UI"
for _widget in ("CTkButton", "CTkCheckBox", "CTkProgressBar"):
    ctk.ThemeManager.theme[_widget]["fg_color"] = ACCENT
ctk.ThemeManager.theme["CTkButton"].update(
    hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT, corner_radius=10,
)
ctk.ThemeManager.theme["CTkEntry"].update(
    fg_color=INSET, border_color=BORDER, text_color=TEXT,
    placeholder_text_color=MUTED, border_width=1,
)
ctk.ThemeManager.theme["CTkLabel"]["text_color"] = TEXT
ctk.ThemeManager.theme["CTkFrame"].update(fg_color=SURFACE, top_fg_color=SURFACE)
ctk.ThemeManager.theme["CTkSegmentedButton"].update(
    fg_color=INSET, selected_color=SOFT, selected_hover_color=SOFT,
    unselected_color=INSET, unselected_hover_color=HOVER,
    text_color=TEXT,
)


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
        super().__init__(master, corner_radius=10, fg_color=INSET)
        self.path = path
        self.canon_key = _canon_key(_resolve_safe(path))
        self.on_remove = on_remove

        self.grid_columnconfigure(1, weight=1)
        icon = ctk.CTkLabel(self, text="PDF", width=40, height=38,
                            corner_radius=8, fg_color=SOFT, text_color=ACCENT,
                            font=ctk.CTkFont(size=11, weight="bold"))
        icon.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=10)

        text = path.name if len(path.name) <= 48 else f"{path.name[:30]}…{path.name[-14:]}"
        label = ctk.CTkLabel(self, text=text, anchor="w", height=22,
                             font=ctk.CTkFont(size=13, weight="bold"))
        label.grid(row=0, column=1, sticky="ew", pady=(9, 0))
        parent = str(path.parent)
        if len(parent) > 64:
            parent = f"…{parent[-62:]}"
        ctk.CTkLabel(self, text=parent, anchor="w", height=18,
                     text_color=MUTED, font=ctk.CTkFont(size=11)
                     ).grid(row=1, column=1, sticky="ew", pady=(0, 9))

        remove = ctk.CTkButton(
            self, text="×", width=28, height=24, corner_radius=12,
            fg_color="transparent", hover_color=HOVER,
            text_color=MUTED,
            command=self._remove,
        )
        self.remove_button = remove
        remove.grid(row=0, column=2, rowspan=2, padx=(4, 12), pady=4)

    def _remove(self):
        self.on_remove(self)


class App:
    def __init__(self) -> None:
        self.settings = Settings.load()
        ctk.set_appearance_mode(self.settings.appearance)

        self.root = _Tk()
        self.root.title(APP_NAME)
        self.root.geometry("720x800")
        self.root.minsize(640, 780)
        self.root.configure(fg_color=BG)

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
        header = ctk.CTkFrame(root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 20))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="EL", width=46, height=46,
                     corner_radius=13, fg_color=ACCENT, text_color=ACCENT_TEXT,
                     font=ctk.CTkFont(size=19, weight="bold")
                     ).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        ctk.CTkLabel(
            header, text=APP_NAME, height=28,
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(header, text="PDFのパスワード設定・解除を、まとめて。",
                     height=22, font=ctk.CTkFont(size=12), text_color=MUTED
                     ).grid(row=1, column=1, sticky="w")
        self.settings_button = self._secondary_button(
            header, text="設定", width=70, height=34,
            command=self._open_settings,
        )
        self.settings_button.grid(row=0, column=2, rowspan=2, sticky="e")

        files_card = ctk.CTkFrame(root, corner_radius=16, border_width=1,
                                 border_color=BORDER, fg_color=SURFACE)
        files_card.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 16))
        files_card.grid_columnconfigure(0, weight=1)
        files_card.grid_rowconfigure(1, weight=1)
        file_heading = ctk.CTkFrame(files_card, fg_color="transparent")
        file_heading.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 10))
        file_heading.grid_columnconfigure(1, weight=1)
        self._step_heading(file_heading, "01", "PDFファイル")
        self.file_count = ctk.CTkLabel(file_heading, text="0 件", width=56, height=26,
                                      corner_radius=8, fg_color=INSET,
                                      text_color=MUTED, font=ctk.CTkFont(size=12))
        self.file_count.grid(row=0, column=2, sticky="e")

        self.file_container = ctk.CTkFrame(files_card, corner_radius=12,
                                           border_width=1, border_color=BORDER,
                                           fg_color=INSET)
        self.file_container.grid(row=1, column=0, sticky="nsew", padx=20)
        self.file_container.grid_columnconfigure(0, weight=1)
        self.file_container.grid_rowconfigure(0, weight=1)
        self.empty_label = ctk.CTkFrame(self.file_container, fg_color="transparent")
        ctk.CTkLabel(self.empty_label, text="PDF", width=46, height=48,
                     corner_radius=10, fg_color=SOFT, text_color=ACCENT,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(0, 10))
        ctk.CTkLabel(self.empty_label,
                     text="PDFをここにドロップ" if DND_AVAILABLE else "PDFを選択して追加",
                     height=26, font=ctk.CTkFont(size=17, weight="bold")).pack()
        ctk.CTkLabel(self.empty_label, text="複数ファイルをまとめて追加できます",
                     height=24, text_color=MUTED, font=ctk.CTkFont(size=12)).pack()
        self.file_list = ctk.CTkScrollableFrame(
            self.file_container, fg_color="transparent",
            corner_radius=10, height=150, scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED,
        )
        self.file_list.grid_columnconfigure(0, weight=1)
        if DND_AVAILABLE:
            self.file_container.drop_target_register(DND_FILES)
            self.file_container.dnd_bind("<<Drop>>", self._on_drop)
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)
        toolbar = ctk.CTkFrame(files_card, fg_color="transparent")
        toolbar.grid(row=2, column=0, sticky="ew", padx=20, pady=(12, 16))
        self.add_button = self._secondary_button(
            toolbar, text="＋  ファイルを選択", height=34, width=156,
            command=self._add_files,
        )
        self.add_button.pack(side="left")
        self.clear_button = self._secondary_button(
            toolbar, text="すべてクリア", height=34, width=104,
            command=self._clear_files,
        )
        self.clear_button.pack(side="right")

        options = ctk.CTkFrame(root, corner_radius=16, border_width=1,
                               border_color=BORDER, fg_color=SURFACE)
        options.grid(row=2, column=0, sticky="ew", padx=28)
        options.grid_columnconfigure(0, weight=1)
        option_heading = ctk.CTkFrame(options, fg_color="transparent")
        option_heading.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 12))
        self._step_heading(option_heading, "02", "処理設定")
        mode_row = ctk.CTkFrame(options, fg_color="transparent")
        mode_row.grid(row=1, column=0, sticky="ew", padx=20)
        self.mode_seg = ctk.CTkSegmentedButton(
            mode_row, values=["暗号化", "解除"],
            command=self._on_mode_change, font=ctk.CTkFont(size=14, weight="bold"),
            height=40, corner_radius=10, border_width=4,
            selected_color=SOFT, selected_hover_color=SOFT,
        )
        self.mode_seg.set("暗号化")
        self.mode_seg.pack(fill="x")
        self.mode_hint = ctk.CTkLabel(options, text="PDFを開くときに必要なパスワードを設定します。",
                                      anchor="w", height=24, text_color=MUTED,
                                      font=ctk.CTkFont(size=12))
        self.mode_hint.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 10))
        pw_row = ctk.CTkFrame(options, fg_color="transparent")
        pw_row.grid(row=3, column=0, sticky="ew", padx=20)
        self.pw_label = ctk.CTkLabel(pw_row, text="新しいパスワード",
                                     height=24, font=ctk.CTkFont(size=12, weight="bold"))
        self.pw_label.pack(anchor="w", pady=(0, 5))
        pw_inner = ctk.CTkFrame(pw_row, fg_color="transparent")
        pw_inner.pack(fill="x")
        self.pw_entry = ctk.CTkEntry(pw_inner, show="●", height=40, corner_radius=10,
                                     placeholder_text="パスワードを入力",
                                     font=ctk.CTkFont(size=13))
        self.pw_entry.pack(side="left", fill="x", expand=True)
        self.pw_entry.bind("<KeyRelease>", lambda event: self._update_ready_state())
        self.show_password_button = self._secondary_button(
            pw_inner, text="表示", width=68, height=40, command=self._toggle_password)
        self.show_password_button.pack(side="left", padx=(8, 0))
        self.pw_hint = ctk.CTkLabel(options, text="4文字以上・8文字以上を推奨",
                                    anchor="w", height=22, text_color=MUTED,
                                    font=ctk.CTkFont(size=11))
        self.pw_hint.grid(row=4, column=0, sticky="ew", padx=20, pady=(3, 10))
        out_row = ctk.CTkFrame(options, fg_color="transparent")
        out_row.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 16))
        ctk.CTkLabel(out_row, text="保存先", height=24,
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).pack(anchor="w", pady=(0, 5))
        out_inner = ctk.CTkFrame(out_row, fg_color="transparent")
        out_inner.pack(fill="x")
        self.out_entry = ctk.CTkEntry(out_inner, height=40, corner_radius=10,
                                      placeholder_text="元のPDFと同じフォルダに保存",
                                      font=ctk.CTkFont(size=13))
        self.out_entry.pack(side="left", fill="x", expand=True)
        if self.settings.default_output_dir:
            self.out_entry.insert(0, self.settings.default_output_dir)
        self.browse_button = self._secondary_button(
            out_inner, text="参照", width=68, height=40,
            command=self._choose_output_dir,
        )
        self.browse_button.pack(side="left", padx=(8, 0))
        footer = ctk.CTkFrame(root, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=28, pady=(18, 22))
        footer.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(
            footer, text="PDFを追加してください", anchor="w",
            font=ctk.CTkFont(size=12), text_color=MUTED,
        )
        self.status_label.grid(row=0, column=0, sticky="w")
        self.run_button = ctk.CTkButton(
            footer, text="暗号化開始  →", width=176, height=46, corner_radius=12,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color_disabled=MUTED,
            command=self._run,
        )
        self.run_button.grid(row=0, column=1, sticky="e")
        self.progress = ctk.CTkProgressBar(footer, height=4, fg_color=BORDER,
                                          progress_color=ACCENT)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.progress.grid_remove()

    @staticmethod
    def _secondary_button(master, **kwargs):
        return ctk.CTkButton(master, corner_radius=9, fg_color="transparent",
                            border_width=1, border_color=BORDER, text_color=TEXT,
                            hover_color=HOVER, font=ctk.CTkFont(size=12), **kwargs)

    @staticmethod
    def _step_heading(master, number: str, title: str) -> None:
        ctk.CTkLabel(master, text=number, width=28, height=28, corner_radius=8,
                     fg_color=SOFT, text_color=ACCENT,
                     font=ctk.CTkFont(size=11, weight="bold")
                     ).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkLabel(master, text=title, font=ctk.CTkFont(size=15, weight="bold")
                     ).grid(row=0, column=1, sticky="w")

    def _toggle_password(self) -> None:
        visible = self.pw_entry.cget("show") == ""
        self.pw_entry.configure(show="●" if visible else "")
        self.show_password_button.configure(text="表示" if visible else "隠す")

    # ---- Mode ----
    def _on_mode_change(self, value: str) -> None:
        self.mode = "encrypt" if value == "暗号化" else "decrypt"
        if self.mode == "encrypt":
            self.pw_label.configure(text="新しいパスワード")
            self.run_button.configure(text="暗号化開始  →")
            self.mode_hint.configure(text="PDFを開くときに必要なパスワードを設定します。")
            self.pw_hint.configure(text="4文字以上・8文字以上を推奨")
        else:
            self.pw_label.configure(text="現在のパスワード")
            self.run_button.configure(text="解除開始  →")
            self.mode_hint.configure(text="設定済みのパスワードを使って、PDFの保護を解除します。")
            self.pw_hint.configure(text="PDFに設定されているパスワードを入力")
        self._update_ready_state()

    def _update_ready_state(self, update_status: bool = True) -> None:
        if self.processing:
            return
        ready = bool(self.file_rows) and len(self.pw_entry.get()) >= PASSWORD_MIN_LEN
        self.run_button.configure(state="normal" if ready else "disabled",
                                   fg_color=ACCENT if ready else HOVER)
        if update_status:
            if not self.file_rows:
                text = "PDFを追加してください"
            elif len(self.pw_entry.get()) < PASSWORD_MIN_LEN:
                text = "パスワードを入力してください（4文字以上）"
            else:
                text = f"{len(self.file_rows)} 件のPDFを処理できます"
            self.status_label.configure(text=text)

    def _set_processing_controls(self, processing: bool) -> None:
        state = "disabled" if processing else "normal"
        for widget in (self.add_button, self.clear_button, self.settings_button,
                       self.mode_seg, self.pw_entry, self.show_password_button,
                       self.out_entry, self.browse_button):
            widget.configure(state=state)
        for row in self.file_rows:
            row.remove_button.configure(state=state)
        if not processing:
            self.clear_button.configure(state="normal" if self.file_rows else "disabled")

    # ---- File list ----
    def _update_empty_state(self) -> None:
        self.file_count.configure(text=f"{len(self.file_rows)} 件")
        self.clear_button.configure(state="normal" if self.file_rows else "disabled")
        if self.file_rows:
            self.empty_label.grid_forget()
            self.file_list.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        else:
            self.file_list.grid_forget()
            self.empty_label.grid(row=0, column=0)
        self._update_ready_state()

    def _add_files(self) -> None:
        if self.processing:
            return
        paths = filedialog.askopenfilenames(
            title="PDFを選択", filetypes=[("PDF", "*.pdf")],
        )
        for p in paths:
            self._add_file(Path(p))

    def _add_file(self, p: Path) -> None:
        if self.processing:
            return
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
        if self.processing:
            return
        row.destroy()
        self.file_rows.remove(row)
        # re-layout remaining
        for i, r in enumerate(self.file_rows):
            r.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
        self._update_empty_state()

    def _clear_files(self) -> None:
        if self.processing:
            return
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
        self._set_processing_controls(True)
        self.progress.set(0)
        self.progress.grid()
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
            self.root.after(0, self._update_progress, i, len(files))
        self.root.after(0, self._finish, ok, fail)

    def _update_progress(self, completed: int, total: int) -> None:
        self.status_label.configure(text=f"{completed} / {total} 件を処理中…")
        self.progress.set(completed / total)

    def _finish(self, ok: int, fail: list) -> None:
        self.processing = False
        self._set_processing_controls(False)
        self.progress.grid_remove()
        run_text = "暗号化開始  →" if self.mode == "encrypt" else "解除開始  →"
        self.run_button.configure(text=run_text)
        self._update_ready_state(update_status=False)
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
        if self.processing:
            return
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("設定")
        dlg.geometry("520x430")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(fg_color=BG)
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
            border_color=BORDER, text_color=TEXT, hover_color=HOVER,
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
            border_color=BORDER, text_color=TEXT, hover_color=HOVER,
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
