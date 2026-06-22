"""読み上げアプリ（デスクトップ版 / CustomTkinter）。

ブラウザではなく、Windows のデスクトップアプリとして動く画面。
起動:
    python app.py

このアプリは「画面の状態（state）」を1つ持ち、それに合わせて
  - ボタンの有効／無効
  - ステータス表示
  - 波形と再生位置バー
がまとめて切り替わるように作ってある。

状態（state）は4つ:
  idle       … 起動直後・まだ何も生成していない（生成だけ押せる）
  generating … 生成中（すべて押せない）
  ready      … 生成完了で再生待ち（生成・再生が押せる）
  playing    … 再生中（生成・停止が押せる）

表示言語（日本語／英語）は i18n.py の辞書にまとめてあり、画面右上で切り替えられる。
言語を切り替えると、画面の文字（ラベル・ボタン・ステータス・波形）が即座に貼り替わる。

ポイント:
  - 音声生成は重いので別スレッドで実行し、生成中も画面が固まらないようにする。
  - Tkinter は別スレッドから触ると不安定なので、生成結果はキュー経由で
    メインスレッドが受け取って画面を更新する。
  - 読み上げの中身（adapter.py / 各エンジン）はそのまま流用する。
"""

from __future__ import annotations

import os
import sys
import json
import time
import queue
import zipfile
import tempfile
import datetime as _dt
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
from tkinterdnd2 import TkinterDnD, DND_FILES

# Windows のコンソール文字コード（cp932）で日本語の print が落ちないようにする
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# オフライン同梱配布用：MVS_OFFLINE=1 のとき、モデルのダウンロードを試みず
# ローカルキャッシュだけを使う（ネットが無くても起動・生成できる）。
# モデルを HF から取り込むより前（ここ）で設定しておく必要がある。
if os.environ.get("MVS_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on"):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np
import customtkinter as ctk

import matplotlib
matplotlib.use("TkAgg")
# 波形の軸ラベル等で日本語が豆腐（□）にならないよう、Windows の日本語フォントを使う
matplotlib.rcParams["font.family"] = ["Yu Gothic", "Meiryo", "MS Gothic", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import i18n
from tts import (
    synthesize, synthesize_clone, list_voices, default_voice,
    list_languages, default_language, ENGINES,
)
from tts import player

# エンジンの「表示名 ⇔ 内部名」の対応表
ENGINE_KEY_TO_LABEL = dict(ENGINES)                       # {"qwen3": "Qwen3-TTS", ...}
ENGINE_LABEL_TO_KEY = {v: k for k, v in ENGINES.items()}  # {"Qwen3-TTS": "qwen3", ...}
DEFAULT_ENGINE = "qwen3"

# 音声言語（エンジンに渡す言語名）→ 表示文言を引くための i18n 言語コード。
# テキスト欄のプレースホルダを「音声言語」に合わせるために使う。
AUDIO_LANG_TO_I18N = {
    "Japanese": "ja",
    "English": "en",
    "Chinese": "zh-CN",
    "Korean": "ko",
    "German": "de",
    "French": "fr",
    "Russian": "ru",
    "Portuguese": "pt",
    "Spanish": "es",
    "Italian": "it",
}

# ウィンドウのサイズ・位置を覚えておくファイル
WINDOW_STATE_FILE = Path(__file__).resolve().parent / "window_state.json"
DEFAULT_SIZE = (700, 800)   # 初回（保存が無いとき）の大きさ
MIN_SIZE = (600, 700)       # これより小さくはしない

# 画面の状態
STATE_IDLE = "idle"
STATE_GENERATING = "generating"
STATE_READY = "ready"
STATE_PLAYING = "playing"

# ステータス文字の色（明るいテーマ用, 暗いテーマ用）
COLOR_NORMAL = ("gray10", "gray90")
COLOR_ERROR = ("#C0392B", "#FF6B6B")

# 波形の色
WAVE_BG = "#f3f3f3"
WAVE_LINE = "#1f6aa5"
CURSOR_COLOR = "#e74c3c"

ctk.set_appearance_mode("system")       # OSの設定に合わせて明/暗
ctk.set_default_color_theme("blue")     # ベース。色は下で Windows 風グレーに上書きする


def _apply_windows_theme():
    """ボタン・ドロップダウン・スライダー等の青を、一般的な Windows アプリ風の
    ニュートラルなグレーに置き換える。

    色は (明るいテーマ用, 暗いテーマ用) の組で指定する。
    CustomTkinter のバージョン差でキーが無い場合に備え、各設定は try で囲む。
    """
    theme = ctk.ThemeManager.theme

    SURFACE = ["#e6e6e6", "#3a3a3a"]   # コントロールの地色
    HOVER = ["#d5d5d5", "#454545"]     # マウスを乗せたとき
    BORDER = ["#bfbfbf", "#4d4d4d"]    # ふち
    TEXT = ["#1a1a1a", "#f2f2f2"]      # 文字
    ACCENT = ["#8a8a8a", "#9a9a9a"]    # スライダーのつまみ／オンの色（青の代わりの濃いグレー）
    TROUGH = ["#cdcdcd", "#4a4a4a"]    # スライダーの溝・セグメントの土台
    WHITE = ["#ffffff", "#2b2b2b"]     # ドロップダウンの背景（白）

    # ボタンは一般的な Windows アプリの押しボタン風（薄いグレーの面＋はっきりしたふち）。
    # 真っ白にはせず、背景から浮く程度のグレーにする。
    BTN_FG = ["#e1e1e1", "#3a3a3a"]
    BTN_HOVER = ["#d2d2d2", "#474747"]
    BTN_BORDER = ["#adadad", "#5e5e5e"]

    def upd(widget, **vals):
        try:
            theme[widget].update(vals)
        except Exception:
            pass

    upd("CTkButton", fg_color=BTN_FG, hover_color=BTN_HOVER, text_color=TEXT,
        border_color=BTN_BORDER, border_width=1, corner_radius=4)
    # ドロップダウン（本体＋開いたときのリスト）の背景を白に
    upd("CTkOptionMenu", fg_color=WHITE, button_color=SURFACE,
        button_hover_color=HOVER, text_color=TEXT)
    upd("CTkComboBox", fg_color=WHITE, button_color=SURFACE,
        button_hover_color=HOVER, border_color=BORDER, text_color=TEXT)
    upd("DropdownMenu", fg_color=WHITE, hover_color=HOVER, text_color=TEXT)
    upd("CTkSegmentedButton", fg_color=TROUGH, selected_color=SURFACE,
        selected_hover_color=HOVER, unselected_color=TROUGH,
        unselected_hover_color=HOVER, text_color=TEXT)
    upd("CTkSlider", fg_color=TROUGH, progress_color=ACCENT,
        button_color=ACCENT, button_hover_color=HOVER)
    upd("CTkSwitch", fg_color=TROUGH, progress_color=ACCENT,
        button_color=["#ffffff", "#d0d0d0"], button_hover_color=HOVER)


_apply_windows_theme()


class TTSApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        # ファイルのドラッグ&ドロップを使えるようにする（tkdnd を読み込む）
        try:
            self.TkdndVersion = TkinterDnD._require(self)
        except Exception:
            self.TkdndVersion = None
        self.title("Multi Voice Studio")
        self.minsize(*MIN_SIZE)
        self._apply_saved_geometry()

        # 言語まわり
        # 初期言語＝「前回保存した言語」→ 無ければ「OSの言語」→ それも対象外なら英語
        self._lang = self._load_saved_lang() or i18n.detect_os_lang()
        self._lang_label_to_code = {label: code for code, label in i18n.LANGUAGES.items()}
        # プルダウンの並び順（日本語・英語を特別扱いせず、表示名で五十音／アルファベット順）
        self._lang_labels_sorted = sorted(i18n.LANGUAGES.values())

        # エンジンまわり：初期エンジン＝「前回保存したエンジン」→ 無ければ既定（Irodori）
        self._engine = self._load_saved_engine() or DEFAULT_ENGINE

        # 状態まわりの変数
        self._state = STATE_IDLE
        self.current_wav: str | None = None
        self._wav_data = None
        self._wav_sr = None
        self._audio_duration = 0.0
        self._play_start = 0.0
        self._cursor_after_id = None
        self._cursor = None
        self._voice_items: list[tuple[str, str]] = []   # (表示名キー, 声ID)
        self._voice_map: dict[str, str] = {}            # 表示名 -> 声ID（現在の言語）
        self._current_voice_id: str | None = None
        self._audio_lang_items: list[tuple[str, str]] = []   # (表示名キー, 言語名)
        self._audio_lang_map: dict[str, str] = {}            # 表示名 -> 言語名（現在の言語）
        self._current_audio_lang: str | None = None
        self._saved_voice_file: str | None = None   # 「保存した声」タブに追加された .mvsvoice（1個まで）
        self._mvsvoice_cache: tuple | None = None    # (path, ref_wav, ref_text, language) の展開キャッシュ
        self._result_queue: "queue.Queue" = queue.Queue()

        # ステータスは「キー＋差し込み値」で覚えておき、言語切替時に貼り替える
        self._status_key = "status_ready"
        self._status_params: dict = {}
        self._status_error = False

        self._build_widgets()
        self._refresh_voices(self._engine)
        # 音声言語は前回保存した値を優先（そのエンジンで使えなければ既定にする）
        self._refresh_audio_languages(self._engine, preferred=self._load_saved_audio_lang())
        self._set_state(STATE_IDLE)
        self._apply_language(self._lang)   # 画面の文字を初期言語でセット

        self.after(100, self._poll_result)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- 翻訳の近道 ---------------------------------------------------------
    def _t(self, key, **params):
        return i18n.t(self._lang, key, **params)

    # ---- ウィンドウのサイズ・位置の保存／復元 -------------------------------
    @staticmethod
    def _parse_geometry(geo: str):
        try:
            nums = [int(p) for p in geo.replace("x", "+").split("+") if p != ""]
            if len(nums) == 4:
                return tuple(nums)
        except Exception:
            pass
        return None

    def _clamp_to_screen(self, w, h, x, y):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = max(MIN_SIZE[0], min(w, sw))
        h = max(MIN_SIZE[1], min(h, sh))
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        return w, h, x, y

    def _apply_saved_geometry(self):
        self.update_idletasks()
        parsed = None
        try:
            data = json.loads(WINDOW_STATE_FILE.read_text(encoding="utf-8"))
            parsed = self._parse_geometry(data.get("geometry", ""))
        except Exception:
            parsed = None
        if parsed:
            w, h, x, y = self._clamp_to_screen(*parsed)
        else:
            w, h = DEFAULT_SIZE
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _load_saved_lang(self) -> str | None:
        """前回保存した言語コードを返す。無効／未保存なら None。"""
        try:
            data = json.loads(WINDOW_STATE_FILE.read_text(encoding="utf-8"))
            lang = data.get("lang")
            if lang in i18n.LANGUAGES:
                return lang
        except Exception:
            pass
        return None

    def _load_saved_engine(self) -> str | None:
        """前回保存したエンジンのキーを返す。無効／未保存なら None。"""
        try:
            data = json.loads(WINDOW_STATE_FILE.read_text(encoding="utf-8"))
            engine = data.get("engine")
            if engine in ENGINES:
                return engine
        except Exception:
            pass
        return None

    def _load_saved_audio_lang(self) -> str | None:
        """前回保存した音声言語（言語名）を返す。未保存なら None。

        値の妥当性は、エンジンごとの選択肢に対して後で確認する。
        """
        try:
            data = json.loads(WINDOW_STATE_FILE.read_text(encoding="utf-8"))
            val = data.get("audio_lang")
            if isinstance(val, str):
                return val
        except Exception:
            pass
        return None

    def _save_window_state(self):
        try:
            WINDOW_STATE_FILE.write_text(
                json.dumps({
                    "geometry": self.geometry(),
                    "lang": self._lang,
                    "engine": self._engine,
                    "audio_lang": self._current_audio_lang,
                }),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ---- 画面の組み立て -----------------------------------------------------
    def _build_widgets(self):

        # 上部バー：エンジン選択（左・ラベルなし）／言語切り替え（右）
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 0))
        self.lang_btn = ctk.CTkOptionMenu(
            top, values=self._lang_labels_sorted, command=self._on_language_change
        )
        self.lang_btn.set(i18n.LANGUAGES[self._lang])
        self.lang_btn.pack(side="right")
        self.engine_btn = ctk.CTkSegmentedButton(
            top, values=list(ENGINE_LABEL_TO_KEY.keys()), command=self._on_engine_change
        )
        self.engine_btn.set(ENGINE_KEY_TO_LABEL[self._engine])
        self.engine_btn.pack(side="left")

        # 音声言語（声が何語として読み上げるか）。エンジンのスイッチの右に置く。
        self.lbl_audio_lang = ctk.CTkLabel(top, text="")
        self.lbl_audio_lang.pack(side="left", padx=(12, 0))
        self.audio_lang_menu = ctk.CTkOptionMenu(
            top, values=["—"], command=self._on_audio_lang_change
        )
        self.audio_lang_menu.pack(side="left", padx=(8, 0))

        # テキスト入力（ラベルなし）
        self.text_box = ctk.CTkTextbox(self, height=120, wrap="word")
        self.text_box.pack(fill="both", expand=True, padx=16, pady=(10, 0))

        # 声：タブ方式（「プリセット」「保存した声」）。タブで自然に排他になる。
        # 将来タブを増やすときは self._voice_tab_keys に i18n キーを足すだけでよい。
        # anchor="nw" でタブ見出しを左寄せ（他の要素の左端にそろえる）。
        self._voice_tab_keys = ["tab_preset", "tab_saved"]   # ← ここに足せばタブが増える
        self.voice_tabview = ctk.CTkTabview(self, height=150, anchor="nw",
                                            command=self._on_voice_tab_change)
        self.voice_tabview.pack(fill="x", padx=16, pady=(8, 0))
        self._voice_tab_names = {}
        for _k in self._voice_tab_keys:
            _name = self._t(_k)
            self.voice_tabview.add(_name)
            self._voice_tab_names[_k] = _name
        # プリセットタブ：今ある「声」のプルダウン（おの あんな 等）
        preset_tab = self.voice_tabview.tab(self._voice_tab_names["tab_preset"])
        self.voice_menu = ctk.CTkOptionMenu(preset_tab, values=["—"],
                                            command=self._on_voice_change)
        self.voice_menu.pack(anchor="w", padx=4, pady=4)
        # 保存した声タブ：ファイル選択／ドラッグ&ドロップ（.mvsvoice を1個まで）
        saved_tab = self.voice_tabview.tab(self._voice_tab_names["tab_saved"])
        # 上段：「ファイルを選択」ボタン＋その右にファイル名（フルパス）
        pick_row = ctk.CTkFrame(saved_tab, fg_color="transparent")
        pick_row.pack(fill="x", padx=4, pady=(4, 0))
        self.btn_pick_mvsvoice = ctk.CTkButton(pick_row, text="", width=120,
                                               command=self._on_pick_mvsvoice)
        self.btn_pick_mvsvoice.pack(side="left")
        self.lbl_saved_file = ctk.CTkLabel(pick_row, text="", anchor="w")
        self.lbl_saved_file.pack(side="left", padx=(8, 0), fill="x", expand=True)
        # 下段：ドロップ領域（素の tk.Label。tkinterdnd2 でドロップを受ける）
        self.dnd_zone = tk.Label(saved_tab, text="", relief="groove", bd=1,
                                 height=2, fg="#666666", bg="#f5f5f5")
        self.dnd_zone.pack(fill="x", padx=4, pady=(6, 0))
        try:
            self.dnd_zone.drop_target_register(DND_FILES)
            self.dnd_zone.dnd_bind("<<Drop>>", self._on_drop_mvsvoice)
        except Exception:
            pass   # DnD が使えない環境では「ファイルを選択」だけ使える

        # 速度
        speed_row = ctk.CTkFrame(self, fg_color="transparent")
        speed_row.pack(fill="x", padx=16, pady=(10, 0))
        self.lbl_speed = ctk.CTkLabel(speed_row, text="")
        self.lbl_speed.pack(side="left")
        self.speed_value_label = ctk.CTkLabel(speed_row, text="", width=48)
        self.speed_value_label.pack(side="right")
        self.speed_slider = ctk.CTkSlider(
            speed_row, from_=0.5, to=2.0, number_of_steps=15, command=self._on_speed_change
        )
        self.speed_slider.set(1.0)
        self.speed_slider.pack(side="left", fill="x", expand=True, padx=10)

        # ボタン類
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(14, 0))
        self.speak_btn = ctk.CTkButton(btn_row, text="", height=40, command=self._on_speak)
        self.speak_btn.pack(side="left", fill="x", expand=True)
        self.play_btn = ctk.CTkButton(btn_row, text="", width=90, command=self._on_play)
        self.play_btn.pack(side="left", padx=(10, 0))
        self.stop_btn = ctk.CTkButton(btn_row, text="", width=90, command=self._on_stop)
        self.stop_btn.pack(side="left", padx=(10, 0))

        # 波形表示（生成・再生・停止ボタンの下）
        wave_frame = ctk.CTkFrame(self)
        wave_frame.pack(fill="x", padx=16, pady=(12, 0))
        self._fig = Figure(figsize=(5, 1.6), dpi=100, facecolor=WAVE_BG)
        self._ax = self._fig.add_subplot(111)
        # 左右のマージンを揃えて、波形を中央に置く（右寄り対策）
        self._fig.subplots_adjust(left=0.04, right=0.96, top=0.92, bottom=0.22)
        self._canvas = FigureCanvasTkAgg(self._fig, master=wave_frame)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        # 生成中インジケータ（処理中アニメーション）。波形エリアの中央に重ねて表示。
        # 普段は隠し、生成中だけ _set_state で表示してアニメーションさせる。
        self._busy_bar = ctk.CTkProgressBar(wave_frame, mode="indeterminate")

        # 「声を保存する」ボタン：波形の枠の外（下の白い部分）に置く
        save_row = ctk.CTkFrame(self, fg_color="transparent")
        save_row.pack(fill="x", padx=16, pady=(6, 0))
        # 並び：左から「声を保存する」→「音声を保存する」
        self.btn_save_audio_file = ctk.CTkButton(
            save_row, text="", width=120, height=28, command=self._on_save_audio_file
        )
        self.btn_save_audio_file.pack(side="right")
        self.btn_save_voice_file = ctk.CTkButton(
            save_row, text="", width=120, height=28, command=self._on_save_voice_file
        )
        self.btn_save_voice_file.pack(side="right", padx=(0, 8))

        # 状態表示
        self.status_label = ctk.CTkLabel(
            self, text="", anchor="w", justify="left", wraplength=660
        )
        self.status_label.pack(fill="x", padx=16, pady=(12, 14))

    # ---- 言語の切り替え -----------------------------------------------------
    def _on_language_change(self, lang_label: str):
        code = self._lang_label_to_code.get(lang_label, i18n.DEFAULT_LANG)
        self._apply_language(code)
        self._save_window_state()   # 言語を変えたらすぐ保存する

    def _apply_language(self, lang: str):
        """画面に出ている文字を、指定言語に一括で貼り替える。"""
        self._lang = lang

        # 言語トグルの選択表示を現在の言語に合わせる（プログラム的変更でも追従）
        self.lang_btn.set(i18n.LANGUAGES[lang])

        # ラベル類
        self.lbl_audio_lang.configure(text=self._t("label_audio_language"))
        self.lbl_speed.configure(text=self._t("label_speed"))

        # 声タブの見出し（タブ名）と「保存した声」のプレースホルダーを言語に合わせる
        for _k in self._voice_tab_keys:
            _new = self._t(_k)
            _old = self._voice_tab_names[_k]
            if _new != _old:
                self.voice_tabview.rename(_old, _new)
                self._voice_tab_names[_k] = _new
        # 「保存した声」タブの中身（ボタン・ドロップ案内・ファイル名表示）
        self.btn_pick_mvsvoice.configure(text=self._t("btn_pick_mvsvoice"))
        self.dnd_zone.configure(text=self._t("dnd_hint"))
        self._refresh_saved_file_label()

        # 声・音声言語プルダウンの中身（各項目＋選択中の表示）も新しい言語で作り直す
        self._relabel_voices()
        self._relabel_audio_languages()

        # 再生・停止ボタン（生成ボタンの文字は状態によるので _set_state で）
        self.play_btn.configure(text=self._t("btn_play"))
        self.stop_btn.configure(text=self._t("btn_stop"))
        self.btn_save_voice_file.configure(text=self._t("btn_save_voice_file"))
        self.btn_save_audio_file.configure(text=self._t("btn_save_audio_file"))
        self._set_state(self._state)  # 生成ボタンの文字を今の状態に合わせて貼り直す

        # 速度の数値表示
        self.speed_value_label.configure(
            text=self._t("speed_value", v=round(float(self.speed_slider.get()), 1))
        )

        # テキスト欄が「手つかず（プレースホルダのまま／空）」なら言語に合わせて差し替え
        self._maybe_update_placeholder()

        # 波形（音声があれば描き直し、無ければ案内文）
        if self._wav_data is not None:
            self._draw_waveform(self._wav_data, self._wav_sr)
        else:
            self._init_waveform_placeholder()

        # ステータス（今の内容を新しい言語で出し直す）
        self._render_status()

    def _placeholder_text(self) -> str:
        """テキスト欄の案内文。表示言語ではなく『音声言語』に合わせる。"""
        code = AUDIO_LANG_TO_I18N.get(self._current_audio_lang, self._lang)
        return i18n.t(code, "textbox_placeholder")

    def _maybe_update_placeholder(self):
        current = self.text_box.get("1.0", "end").strip()
        # どの言語のプレースホルダでも「手つかず」とみなす
        placeholders = {i18n.t(code, "textbox_placeholder") for code in i18n.translations}
        if current == "" or current in placeholders:
            self.text_box.delete("1.0", "end")
            self.text_box.insert("1.0", self._placeholder_text())

    # ---- 波形の描画 ---------------------------------------------------------
    def _init_waveform_placeholder(self):
        self._ax.clear()
        self._ax.set_facecolor(WAVE_BG)
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        self._ax.text(
            0.5, 0.5, self._t("wave_placeholder"),
            ha="center", va="center", fontsize=9, color="gray",
            transform=self._ax.transAxes,
        )
        self._cursor = None
        self._canvas.draw_idle()

    def _draw_waveform(self, data, sr):
        y = np.asarray(data, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)
        self._audio_duration = len(y) / sr if sr else 0.0

        max_points = 2000
        if len(y) > max_points:
            step = len(y) // max_points
            y_ds = y[::step]
            t = np.arange(len(y_ds)) * step / sr
        else:
            y_ds = y
            t = np.arange(len(y)) / sr if sr else np.arange(len(y))

        self._ax.clear()
        self._ax.set_facecolor(WAVE_BG)
        self._ax.plot(t, y_ds, linewidth=0.6, color=WAVE_LINE)
        peak = max(0.05, float(np.abs(y_ds).max()) if len(y_ds) else 0.05)
        self._ax.set_ylim(-peak * 1.1, peak * 1.1)
        self._ax.set_xlim(0, max(self._audio_duration, 0.01))
        self._ax.set_yticks([])
        self._ax.set_xlabel(self._t("wave_xlabel"), fontsize=8)
        self._ax.tick_params(labelsize=8)
        self._cursor = self._ax.axvline(0, color=CURSOR_COLOR, linewidth=1.4)
        self._canvas.draw_idle()

    def _move_cursor(self, x_sec):
        if self._cursor is not None:
            self._cursor.set_xdata([x_sec, x_sec])
            self._canvas.draw_idle()

    # ---- 部品のイベント -----------------------------------------------------
    def _on_engine_change(self, engine_label: str):
        key = ENGINE_LABEL_TO_KEY[engine_label]
        self._engine = key
        self._refresh_voices(key)
        self._refresh_audio_languages(key)   # 言語の選択肢・状態も連動して切り替える
        self._maybe_update_placeholder()     # テキストの案内文を音声言語に合わせる
        self._save_window_state()   # 選んだエンジン・音声言語をすぐ保存する

    def _refresh_voices(self, engine_key: str, preferred: str | None = None):
        # 声の一覧は (表示名キー, 声ID)。表示名は今の言語で組み立てる。
        # preferred が指定され、そのエンジンで使える声ならそれを選ぶ（呼び出し復元用）。
        self._voice_items = list_voices(engine_key)
        valid = {vid for _k, vid in self._voice_items}
        self._current_voice_id = preferred if preferred in valid else default_voice(engine_key)
        self._relabel_voices()

    def _relabel_voices(self):
        """声プルダウンの表示名を、現在の表示言語で作り直す。

        選択中の声（self._current_voice_id）は維持し、その表示名も新しい言語で出し直す。
        """
        self._voice_map = {}
        labels = []
        for key, vid in self._voice_items:
            label = self._t(key)          # i18n キー → 今の言語の表示名
            self._voice_map[label] = vid
            labels.append(label)
        if not labels:
            labels = ["—"]
        self.voice_menu.configure(values=labels)
        # 選択中の声を、今の言語のラベルで選び直す
        cur_label = next(
            (self._t(k) for k, v in self._voice_items if v == self._current_voice_id),
            labels[0],
        )
        self.voice_menu.set(cur_label)

    def _on_voice_change(self, label: str):
        # ユーザーが選んだ声を、表示名ではなく声IDで覚えておく（言語が変わっても追える）
        self._current_voice_id = self._voice_map.get(label, self._current_voice_id)

    def _refresh_audio_languages(self, engine_key: str, preferred: str | None = None):
        """音声言語プルダウンを、エンジンに合わせて作り直す。

        preferred が指定され、そのエンジンで使える言語なら、それを選択する
        （前回保存した値の復元に使う）。使えなければ既定言語にする。
        """
        # 音声言語の一覧は (表示名キー, 言語名)。表示名は今の表示言語で組み立てる。
        self._audio_lang_items = list_languages(engine_key)
        valid = {val for _key, val in self._audio_lang_items}
        if preferred in valid:
            self._current_audio_lang = preferred
        else:
            self._current_audio_lang = default_language(engine_key)
        self._relabel_audio_languages()

    def _relabel_audio_languages(self):
        """音声言語プルダウンの表示名を、現在の表示言語で作り直す。

        - 選択中の言語（self._current_audio_lang）は維持し、その表示も新しい言語で出し直す。
        - 選べる言語が1つだけ（Irodori＝日本語のみ）のときはグレーアウトする。
        """
        self._audio_lang_map = {}
        labels = []
        for key, val in self._audio_lang_items:
            label = self._t(key)          # i18n キー → 今の表示言語での言語名
            self._audio_lang_map[label] = val
            labels.append(label)
        if not labels:
            labels = ["—"]
        self.audio_lang_menu.configure(values=labels, state="normal")
        cur_label = next(
            (self._t(k) for k, v in self._audio_lang_items if v == self._current_audio_lang),
            labels[0],
        )
        self.audio_lang_menu.set(cur_label)
        # 1言語しかない（日本語のみ）なら選べないようにする
        if len(labels) <= 1:
            self.audio_lang_menu.configure(state="disabled")

    def _on_audio_lang_change(self, label: str):
        # 選んだ音声言語を、表示名ではなく言語名（値）で覚えておく
        self._current_audio_lang = self._audio_lang_map.get(label, self._current_audio_lang)
        self._maybe_update_placeholder()   # テキストの案内文を音声言語に合わせる
        self._save_window_state()          # 音声言語の選択を保存する

    def _on_speed_change(self, value):
        self.speed_value_label.configure(
            text=self._t("speed_value", v=round(float(value), 1))
        )

    # ---- 「保存した声」タブ：.mvsvoice の追加（選択／ドラッグ&ドロップ）-----
    def _refresh_saved_file_label(self):
        """追加された .mvsvoice のファイル名（フルパス）ラベルを更新する。"""
        if self._saved_voice_file:
            self.lbl_saved_file.configure(
                text=self._t("saved_file_label", name=self._saved_voice_file)
            )
        else:
            self.lbl_saved_file.configure(text="")

    def _on_pick_mvsvoice(self):
        path = filedialog.askopenfilename(
            parent=self,
            filetypes=[("Multi Voice Studio voice", "*.mvsvoice")],
        )
        if path:
            self._add_mvsvoice(path)

    def _on_drop_mvsvoice(self, event):
        # tkinterdnd2 のドロップイベント（メインスレッド）。複数パスを安全に分解する。
        try:
            paths = list(self.tk.splitlist(event.data))
        except Exception:
            paths = [event.data] if event.data else []
        self._handle_dropped(paths)

    def _handle_dropped(self, paths):
        if len(paths) > 1:   # ファイルは1個まで
            self._set_status("saved_file_too_many", error=True)
            return
        if paths:
            self._add_mvsvoice(paths[0])

    def _add_mvsvoice(self, path: str):
        """.mvsvoice だけ受け付けて1個保持し、ファイル名（フルパス）を表示する。"""
        if Path(path).suffix.lower() != ".mvsvoice":
            self._set_status("saved_file_bad_ext", error=True)
            return
        self._saved_voice_file = path
        self._mvsvoice_cache = None        # 別ファイルなので展開キャッシュを捨てる
        self._refresh_saved_file_label()
        self._set_state(self._state)       # 生成ボタンの有効/無効を更新（ファイルが入った）
        self._set_status("saved_file_added", name=path)

    def _on_voice_tab_change(self, *_):
        # タブを切り替えたら、生成ボタンの有効/無効を選択タブに合わせて更新する
        self._set_state(self._state)

    def _extract_mvsvoice(self, path: str):
        """.mvsvoice（zip）を展開し、(参照wavパス, ref_text, language) を返す。

        必須（reference.wav 相当＋voice.json の name/ref_text）が無ければエラー。
        同じファイルなら展開結果をキャッシュして使い回す。
        """
        if self._mvsvoice_cache and self._mvsvoice_cache[0] == path:
            return self._mvsvoice_cache[1:]
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "voice.json" not in names:
                raise ValueError("voice.json がありません（壊れた .mvsvoice です）。")
            meta = json.loads(z.read("voice.json").decode("utf-8"))
            audio_name = meta.get("audio_file", "reference.wav")
            if audio_name not in names:
                raise ValueError(f"参照音声 {audio_name} がありません（壊れた .mvsvoice です）。")
            tmpdir = tempfile.mkdtemp(prefix="mvsvoice_")
            z.extract(audio_name, tmpdir)
            ref_wav = os.path.join(tmpdir, audio_name)
        ref_text = meta.get("ref_text") or None
        language = meta.get("language") or None
        self._mvsvoice_cache = (path, ref_wav, ref_text, language)
        return ref_wav, ref_text, language

    # ---- 音声を保存する（読み上げた音声を wav と mp3 で書き出す）-----------
    def _on_save_audio_file(self):
        """直近に生成した読み上げ音声を、wav と mp3 の両方で保存する。"""
        if self._wav_data is None or not self.current_wav:
            self._set_status("save_audio_no_audio", error=True)
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".wav",
            filetypes=[("WAV / MP3", "*.wav *.mp3"), ("All files", "*.*")],
        )
        if not path:
            return
        import soundfile as sf
        base = Path(path).with_suffix("")   # 拡張子を外し、wav と mp3 を並べて書き出す
        wav_path = str(base) + ".wav"
        mp3_path = str(base) + ".mp3"
        try:
            sf.write(wav_path, self._wav_data, self._wav_sr)
            sf.write(mp3_path, self._wav_data, self._wav_sr, format="MP3")
        except Exception as e:
            self._set_status("save_audio_error", error=True, msg=str(e))
            return
        self._set_status("save_audio_done", path=str(base))

    # ---- 声を保存する（.mvsvoice として書き出す）---------------------------
    def _on_save_voice_file(self):
        """直近に生成した音声を参照音声として、.mvsvoice（zip）に書き出す。"""
        if not self.current_wav or not Path(self.current_wav).exists():
            self._set_status("save_voice_no_audio", error=True)
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".mvsvoice",
            filetypes=[("Multi Voice Studio voice", "*.mvsvoice"), ("All files", "*.*")],
        )
        if not path:
            return
        # 書き起こし（ref_text）はテキスト欄の内容。プレースホルダのままなら空にする。
        ref_text = self.text_box.get("1.0", "end").strip()
        placeholders = {i18n.t(c, "textbox_placeholder") for c in i18n.translations}
        if ref_text in placeholders:
            ref_text = ""
        voice_json = {
            "format_version": 1,
            "name": Path(path).stem,
            "ref_text": ref_text,
            "language": self._current_audio_lang or "Japanese",
            "audio_file": "reference.wav",
            "note": "",
            "created_at": _dt.date.today().isoformat(),
        }
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(self.current_wav, "reference.wav")
                z.writestr("voice.json", json.dumps(voice_json, ensure_ascii=False, indent=2))
        except Exception as e:
            self._set_status("save_voice_error", error=True, msg=str(e))
            return
        self._set_status("save_voice_done", path=path)

    # ---- 読み上げ（別スレッド）---------------------------------------------
    def _on_speak(self):
        if self._state == STATE_GENERATING:
            return
        text = self.text_box.get("1.0", "end").strip()
        if not text:
            self._set_status("status_empty", error=True)
            return

        self._cancel_cursor()
        try:
            player.stop()
        except Exception:
            pass

        engine = ENGINE_LABEL_TO_KEY[self.engine_btn.get()]
        speed = round(float(self.speed_slider.get()), 1)

        # どちらのタブが有効かで、生成の中身（プリセット or 保存した声のクローン）を決める
        if self._is_saved_tab_active():
            if not self._saved_voice_file:
                self._set_status("saved_file_need", error=True)
                return
            try:
                ref_wav, ref_text, mv_lang = self._extract_mvsvoice(self._saved_voice_file)
            except Exception as e:
                self._set_status("status_error", error=True, msg=str(e))
                return
            language = mv_lang or self._current_audio_lang
            job = (lambda: synthesize_clone(engine, text, ref_wav,
                                            ref_text=ref_text, language=language, speed=speed))
            voice_label = Path(self._saved_voice_file).stem
        else:
            voice = self._current_voice_id
            language = self._current_audio_lang
            job = (lambda: synthesize(text, engine, voice=voice,
                                      speed=speed, language=language))
            voice_label = self.voice_menu.get()
        engine_label = ENGINE_KEY_TO_LABEL.get(engine, engine)

        # 生成ボタンを押したら、前回の波形をクリアする
        self._wav_data = None
        self._wav_sr = None
        self.current_wav = None
        self._init_waveform_placeholder()

        self._set_state(STATE_GENERATING)
        self._set_status("status_generating")

        threading.Thread(
            target=self._worker, args=(job, engine_label, voice_label, speed), daemon=True
        ).start()

    def _worker(self, job, engine_label, voice_label, speed):
        try:
            wav = job()
            self._result_queue.put(("done", wav, engine_label, voice_label, speed))
        except Exception as e:
            self._result_queue.put(("error", str(e)))

    def _poll_result(self):
        try:
            while True:
                item = self._result_queue.get_nowait()
                if item[0] == "done":
                    _, wav, engine_label, voice_label, speed = item
                    self._on_generation_done(wav, engine_label, voice_label, speed)
                elif item[0] == "error":
                    self._on_generation_error(item[1])
        except queue.Empty:
            pass
        self.after(100, self._poll_result)

    def _on_generation_done(self, wav, engine_label, voice_label, speed):
        self.current_wav = wav
        try:
            data, sr = player.load(wav)
            self._wav_data, self._wav_sr = data, sr
            self._draw_waveform(data, sr)
        except Exception as e:
            self._wav_data, self._wav_sr = None, None
            self._set_state(STATE_READY)
            self._set_status("status_wave_error", error=True, msg=str(e))
            return

        self._start_playback("status_done_playing",
                             engine=engine_label, voice=voice_label, speed=speed)

    def _on_generation_error(self, msg):
        self._set_state(STATE_READY if self.current_wav else STATE_IDLE)
        self._set_status("status_error", error=True, msg=msg)

    # ---- 再生・停止 ---------------------------------------------------------
    def _on_play(self):
        if self._wav_data is None:
            self._set_status("status_no_audio", error=True)
            return
        self._start_playback("status_playing")

    def _on_stop(self):
        self._cancel_cursor()
        try:
            player.stop()
        except Exception:
            pass
        self._move_cursor(0)
        self._set_state(STATE_READY)
        self._set_status("status_stopped")

    def _start_playback(self, status_key, **status_params):
        try:
            player.play_array(self._wav_data, self._wav_sr)
        except Exception as e:
            self._set_state(STATE_READY)
            self._set_status("status_play_error", error=True, msg=str(e))
            return
        self._play_start = time.monotonic()
        self._set_state(STATE_PLAYING)
        self._set_status(status_key, **status_params)
        self._move_cursor(0)
        self._schedule_cursor()

    def _schedule_cursor(self):
        self._cursor_after_id = self.after(40, self._tick_cursor)

    def _tick_cursor(self):
        if self._state != STATE_PLAYING:
            return
        elapsed = time.monotonic() - self._play_start
        if elapsed >= self._audio_duration:
            self._move_cursor(self._audio_duration)
            self._on_playback_finished()
            return
        self._move_cursor(elapsed)
        self._schedule_cursor()

    def _on_playback_finished(self):
        self._cursor_after_id = None
        self._move_cursor(0)
        self._set_state(STATE_READY)
        self._set_status("status_finished")

    def _cancel_cursor(self):
        if self._cursor_after_id is not None:
            try:
                self.after_cancel(self._cursor_after_id)
            except Exception:
                pass
            self._cursor_after_id = None

    # ---- 状態とステータス ---------------------------------------------------
    def _is_saved_tab_active(self) -> bool:
        """「保存した声」タブが選ばれているか。"""
        try:
            return self.voice_tabview.get() == self._voice_tab_names["tab_saved"]
        except Exception:
            return False

    def _set_state(self, state: str):
        self._state = state
        speak_on = state in (STATE_IDLE, STATE_READY, STATE_PLAYING)
        # 「保存した声」タブのときは、ファイルが選ばれていないと生成できない
        if self._is_saved_tab_active() and self._saved_voice_file is None:
            speak_on = False
        play_on = state == STATE_READY
        stop_on = state == STATE_PLAYING
        # 生成中・再生中はエンジン／声を変えられないようにする（待機中だけ操作可）
        controls_on = state in (STATE_IDLE, STATE_READY)
        self.speak_btn.configure(
            state="normal" if speak_on else "disabled",
            text=self._t("btn_generating") if state == STATE_GENERATING else self._t("btn_generate"),
        )
        self.play_btn.configure(state="normal" if play_on else "disabled")
        self.stop_btn.configure(state="normal" if stop_on else "disabled")
        self.engine_btn.configure(state="normal" if controls_on else "disabled")
        self.voice_menu.configure(state="normal" if controls_on else "disabled")
        # 生成中・再生中はタブ（プリセット／保存した声）の切り替えも無効化
        self.voice_tabview.configure(state="normal" if controls_on else "disabled")
        # 保存ボタンは、保存するもの（生成済み音声）が無いときは無効
        save_on = self._wav_data is not None
        self.btn_save_audio_file.configure(state="normal" if save_on else "disabled")
        self.btn_save_voice_file.configure(state="normal" if save_on else "disabled")

        # 生成中は波形エリアに「処理中」のアニメーションを重ねて表示する
        if state == STATE_GENERATING:
            self._busy_bar.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.6)
            self._busy_bar.start()
        else:
            self._busy_bar.stop()
            self._busy_bar.place_forget()

    def _set_status(self, key: str, error: bool = False, **params):
        self._status_key = key
        self._status_params = params
        self._status_error = error
        self._render_status()

    def _render_status(self):
        text = self._t(self._status_key, **self._status_params)
        self.status_label.configure(
            text=text, text_color=(COLOR_ERROR if self._status_error else COLOR_NORMAL)
        )

    def _on_close(self):
        self._save_window_state()
        self._cancel_cursor()
        try:
            player.stop()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    TTSApp().mainloop()
