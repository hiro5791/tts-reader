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
import webbrowser
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

# ---- クラッシュ記録（原因究明用）-------------------------------------------
# 配布版(GUI/コンソール無し)は、ネイティブな致命傷（セグフォ/不正命令/メモリ確保失敗の
# abort 等）や未捕捉例外が起きても画面にもログにも何も残らず「無言で落ちる」。
# そこで faulthandler でネイティブ致命傷も含め、落ちた箇所のスタックをファイルに残す。
# 出力先（書込可）: %LOCALAPPDATA%\MultiVoiceStudio\logs\crash.log（frozen時）。
try:
    import faulthandler as _faulthandler
    from tts.paths import data_root as _data_root

    _log_dir = _data_root() / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _crash_fp = open(_log_dir / "crash.log", "a", encoding="utf-8", buffering=1)
    _crash_fp.write(
        f"\n==== start {_dt.datetime.now():%Y-%m-%d %H:%M:%S} "
        f"frozen={getattr(sys, 'frozen', False)} ====\n"
    )
    try:
        import platform as _platform
        _ram = ""
        try:
            import ctypes as _ct

            class _MSX(_ct.Structure):
                _fields_ = [("l", _ct.c_ulong), ("load", _ct.c_ulong),
                            ("tot", _ct.c_ulonglong), ("av", _ct.c_ulonglong),
                            ("tp", _ct.c_ulonglong), ("ap", _ct.c_ulonglong),
                            ("tv", _ct.c_ulonglong), ("avv", _ct.c_ulonglong),
                            ("ae", _ct.c_ulonglong)]
            _m = _MSX(); _m.l = _ct.sizeof(_MSX)
            if _ct.windll.kernel32.GlobalMemoryStatusEx(_ct.byref(_m)):
                _ram = f" ram_total={_m.tot/1024**3:.1f}GB ram_avail={_m.av/1024**3:.1f}GB"
        except Exception:
            pass
        _crash_fp.write(
            f"python={sys.version.split()[0]} {_platform.platform()} "
            f"cpu_count={os.cpu_count()}{_ram}\n"
        )
        _crash_fp.flush()
    except Exception:
        pass

    # ネイティブ致命傷（SIGSEGV 等）で、全スレッドのPythonスタックを crash.log へ。
    _faulthandler.enable(file=_crash_fp, all_threads=True)

    # 未捕捉のPython例外（メイン/別スレッド）も記録する。
    def _log_uncaught(exc_type, exc, tb):
        try:
            import traceback as _traceback
            _crash_fp.write(f"---- uncaught {_dt.datetime.now():%Y-%m-%d %H:%M:%S} ----\n")
            _traceback.print_exception(exc_type, exc, tb, file=_crash_fp)
            _crash_fp.flush()
        except Exception:
            pass

    sys.excepthook = _log_uncaught
    try:
        import threading as _threading
        _threading.excepthook = lambda a: _log_uncaught(a.exc_type, a.exc_value, a.exc_traceback)
    except Exception:
        pass
except Exception:
    pass

# 配布（PyInstaller）で同梱したモデルを使う。
# frozen（exe化）かつ同梱 models/（HF キャッシュ）があれば、そこを HF_HOME に向け、
# オフライン扱いにする（別PCでもネット無しで動く）。開発時（非frozen）は何もしない。
if getattr(sys, "frozen", False):
    _base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    _bundled_models = _base / "models"
    if _bundled_models.exists():
        os.environ.setdefault("HF_HOME", str(_bundled_models))
        os.environ.setdefault("MVS_OFFLINE", "1")
else:
    # 開発時（非frozen）: プロジェクト直下に完全な models/（HFキャッシュ）が
    # あれば、そこを既定の HF_HOME にする。これで `python app.py` を HF_HOME 無指定で
    # 起動しても同梱の完全モデルを使い、既定キャッシュの未完成DLで固まらない。
    # （HF_HOME を明示指定した場合はそれを尊重＝setdefault）
    _local_models = Path(__file__).resolve().parent / "models"
    if (_local_models / "hub").exists():
        os.environ.setdefault("HF_HOME", str(_local_models))

# オフライン同梱配布用：MVS_OFFLINE=1 のとき、モデルのダウンロードを試みず
# ローカルキャッシュだけを使う（ネットが無くても起動・生成できる）。
# モデルを HF から取り込むより前（ここ）で設定しておく必要がある。
if os.environ.get("MVS_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on"):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# オフライン時の不具合回避：
# transformers 4.57 のトークナイザ読み込みは内部の _patch_mistral_regex →
# is_base_mistral() で model_info()（ネットAPI）を呼ぶため、HF_HUB_OFFLINE=1 だと
# 必ず OfflineModeIsEnabled で落ちる。Qwen/Irodori は Mistral ではなくこの処理は不要なので、
# オフライン時はこのメソッドを「トークナイザをそのまま返す」no-op に差し替えてネット参照を防ぐ。
if os.environ.get("HF_HUB_OFFLINE") == "1":
    try:
        from transformers.tokenization_utils_base import PreTrainedTokenizerBase as _PTTB

        def _skip_mistral_patch(cls, tokenizer, *args, **kwargs):
            return tokenizer

        _PTTB._patch_mistral_regex = classmethod(_skip_mistral_patch)
    except Exception:
        pass

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

# アプリ名・バージョン・問題報告先（情報ダイアログで使う）
APP_NAME = "Multi Voice Studio"


def _read_app_version() -> str:
    """version.txt(???????)????????????????_MEIPASS?dev?app.py??????"""
    try:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        return (base / "version.txt").read_text(encoding="utf-8").strip() or "0.0.0.0"
    except Exception:
        return "0.0.0.0"


APP_VERSION = _read_app_version()
# 「問題を報告」ボタンから開く Google フォーム
REPORT_FORM_URL = "https://forms.gle/7ci3VpBVVA4jcw8U7"

# 設定・ウィンドウ状態は「書き込み可能なデータフォルダ」に置く。
# 配布(MSIX)版はインストール先が読み取り専用のため、ここを誤ると保存に失敗する。
from tts.paths import data_root
# ウィンドウのサイズ・位置を覚えておくファイル
WINDOW_STATE_FILE = data_root() / "window_state.json"
# 設定ファイル（最小限：エンジンと声だけ）
SETTINGS_FILE = data_root() / "settings.json"
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

# 読み上げ位置のハイライト色（薄い黄色）
HL_COLOR = "#ffe9a8"

# 速度・音量・ピッチの3組を横1行にするか縦3段にするかの境目（ウィンドウ幅px）。
# 縦3段にすると背が高くなり、下の保存ボタン/状態バーが画面外に押し出されてしまうため、
# 実用上は常に横1行にする（最小ウィンドウ幅600でもスライダー幅を小さくして収める）。
# これより狭いと縦3段になるが、最小幅600より小さくできないので実質発動しない。
SLIDERS_WRAP_WIDTH = 400

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
        self.title(APP_NAME)
        self.minsize(*MIN_SIZE)
        self._apply_saved_geometry()

        # 設定（最小限：エンジンと声だけ）を読み込む。
        self._settings = self._load_settings()

        # 表示言語：保存値が有効ならそれ、無ければ OS の言語（対象外なら英語）。
        saved_lang = self._settings.get("lang")
        self._lang = saved_lang if saved_lang in i18n.LANGUAGES else i18n.detect_os_lang()
        self._lang_label_to_code = {label: code for code, label in i18n.LANGUAGES.items()}
        # プルダウンの並び順（日本語・英語を特別扱いせず、表示名で五十音／アルファベット順）
        self._lang_labels_sorted = sorted(i18n.LANGUAGES.values())

        # エンジン：保存値が有効ならそれ、無ければ既定。
        saved_engine = self._settings.get("engine")
        self._engine = saved_engine if saved_engine in ENGINES else DEFAULT_ENGINE

        # 状態まわりの変数
        self._state = STATE_IDLE
        self.current_wav: str | None = None
        self._wav_data = None
        self._wav_sr = None
        self._audio_duration = 0.0
        self._play_start = 0.0
        self._cursor_after_id = None
        self._cursor = None
        # 機能⑤：読み上げ位置のハイライト用
        self._gen_text = ""                 # 生成したときの文章（ハイライトの基準）
        self._sentence_spans: list[tuple[int, int]] = []   # 各文の文字インデックス [start,end)
        self._sentence_timeline: list[tuple[float, float]] = []  # 各文の再生時間帯
        self._hl_current = -1               # いまハイライト中の文の番号
        self._voice_items: list[tuple[str, str]] = []   # (表示名キー, 声ID)
        self._voice_map: dict[str, str] = {}            # 表示名 -> 声ID（現在の言語）
        self._current_voice_id: str | None = None
        self._audio_lang_items: list[tuple[str, str]] = []   # (表示名キー, 言語名)
        self._audio_lang_map: dict[str, str] = {}            # 表示名 -> 言語名（現在の言語）
        self._current_audio_lang: str | None = None
        self._saved_voice_file: str | None = None   # 「保存した声」タブに追加された .mvsvoice（1個まで）
        self._mvsvoice_cache: tuple | None = None    # (path, ref_wav, ref_text, language) の展開キャッシュ
        self._gen_id = 0                 # 生成の通し番号（停止した生成の結果を無視するため）
        self._cancel_event = None        # 実行中の生成の中断フラグ（Irodoriサブプロセス停止用）
        self._result_queue: "queue.Queue" = queue.Queue()

        # ステータスは「キー＋差し込み値」で覚えておき、言語切替時に貼り替える
        self._status_key = "status_ready"
        self._status_params: dict = {}
        self._status_error = False

        # 日本語入力で文字サイズがばらつく問題への対処。CustomTkinter の既定
        # フォント Roboto には日本語グリフが無く、日本語を入れると Tk が別のCJK
        # フォントへ差し替えるため同じポイント数でも大きく見える。UI 既定フォントを
        # 日本語対応フォントにそろえて解消する（_build_widgets の前に設定する）。
        self._apply_ui_font()
        self._build_widgets()
        # 声：保存値がそのエンジンに存在すればそれ、無ければ既定にフォールバック。
        self._refresh_voices(self._engine, preferred=self._settings.get("voice"))
        # 音声言語：保存値がそのエンジンで使えればそれ、無ければ既定にフォールバック。
        # （速度・音量・ピッチは保存しない＝毎回 1.0倍/100%/0半音から開始）
        self._refresh_audio_languages(self._engine, preferred=self._settings.get("audio_lang"))
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

    def _virtual_screen_bounds(self):
        """全モニタを合わせたデスクトップ全体の (左, 上, 幅, 高さ) を返す。

        マルチディスプレイ対応：Windows では「仮想スクリーン」を使う
        （2台目モニタの座標はプライマリ幅を超えたり負になったりするため）。
        取得できなければプライマリモニタのみにフォールバックする。
        """
        try:
            import ctypes
            gsm = ctypes.windll.user32.GetSystemMetrics
            vx, vy = gsm(76), gsm(77)        # SM_XVIRTUALSCREEN / SM_YVIRTUALSCREEN
            vw, vh = gsm(78), gsm(79)        # SM_CXVIRTUALSCREEN / SM_CYVIRTUALSCREEN
            if vw > 0 and vh > 0:
                return vx, vy, vw, vh
        except Exception:
            pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _clamp_to_screen(self, w, h, x, y):
        # マルチディスプレイ全体（仮想デスクトップ）の範囲に収める。
        # 2台目モニタ上の位置（大きい座標・負座標）もそのまま保持できる。
        vx, vy, vw, vh = self._virtual_screen_bounds()
        w = max(MIN_SIZE[0], min(w, vw))
        h = max(MIN_SIZE[1], min(h, vh))
        x = max(vx, min(x, vx + vw - w))
        y = max(vy, min(y, vy + vh - h))
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

    def _save_window_state(self):
        """ウィンドウの大きさ・位置だけを保存する（次回起動時に復元）。"""
        try:
            WINDOW_STATE_FILE.write_text(
                json.dumps({"geometry": self.geometry()}), encoding="utf-8"
            )
        except Exception:
            pass

    def _load_settings(self) -> dict:
        """設定ファイル（settings.json）を読む。無い／壊れていれば空の辞書。"""
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_settings(self):
        """設定（エンジン・声・表示言語・音声言語）を保存する。"""
        try:
            SETTINGS_FILE.write_text(
                json.dumps({"engine": self._engine, "voice": self._current_voice_id,
                            "lang": self._lang, "audio_lang": self._current_audio_lang},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _apply_ui_font(self):
        """UIウィジェットの既定フォントを日本語対応フォントにそろえる。

        CustomTkinter の既定は Roboto（日本語グリフ無し）。日本語を入力すると Tk が
        別のCJKフォントへ差し替え、同じポイント数でも大きく見えてサイズがばらつく。
        Latin と日本語を1つのフォントで描く Windows 標準のUIフォントに統一する。
        インストール済みのものを優先順に選び、どれも無ければ既定のまま（悪化しない）。
        """
        try:
            import tkinter.font as tkfont
            available = set(tkfont.families())
            for fam in ("Yu Gothic UI", "Meiryo UI", "Yu Gothic", "Meiryo", "MS Gothic"):
                if fam in available:
                    ctk.ThemeManager.theme["CTkFont"]["family"] = fam
                    break
        except Exception:
            pass

    # ---- 画面の組み立て -----------------------------------------------------
    def _build_widgets(self):

        # 上部バー：エンジン選択（左・ラベルなし）／情報ボタン・言語切り替え（右）
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 0))
        # 旧「情報」ボタンは廃止。ウィンドウ上部のメニューバー
        # （ヘルプ ＞ バージョン情報／お問い合わせ ＞ 問題を報告）に移行した。
        self._build_menubar()
        self.lang_btn = ctk.CTkOptionMenu(
            top, values=self._lang_labels_sorted, command=self._on_language_change
        )
        self.lang_btn.set(i18n.LANGUAGES[self._lang])
        self.lang_btn.pack(side="right", padx=(0, 8))
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

        # ファイル読み込み（txt / PDF / Word → テキスト欄）。.mvsvoice 用とは別物。
        open_row = ctk.CTkFrame(self, fg_color="transparent")
        open_row.pack(fill="x", padx=16, pady=(8, 0))
        self.btn_open_file = ctk.CTkButton(open_row, text="", width=150,
                                           command=self._on_open_file)
        self.btn_open_file.pack(side="left")
        # チェック時は、読み込んだ内容をテキストの末尾に追加する（OFFなら置き換え）。
        # 状態は読み込み時に chk_append.get()（1/0）で直接読む（変数バインドに依存しない）。
        self.chk_append = ctk.CTkCheckBox(open_row, text="")
        self.chk_append.pack(side="left", padx=(12, 0))

        # テキスト入力（案内文は箱の中に出す。追記・生成時は案内文を本文に数えない）
        self.text_box = ctk.CTkTextbox(self, height=120, wrap="word")
        self.text_box.pack(fill="both", expand=True, padx=16, pady=(8, 0))
        # 機能⑤：ハイライト用タグ（読み上げ中の文の背景色）と、編集でハイライト解除
        self._inner_text = self.text_box._textbox   # 内部の tkinter.Text
        self._inner_text.tag_config("hl", background=HL_COLOR)
        self._inner_text.bind("<KeyRelease>", lambda e: self._clear_highlight())
        # コピー（Ctrl+C）・全選択（Ctrl+A）を確実に効かせる
        self._inner_text.bind("<Control-c>", self._copy_selection)
        self._inner_text.bind("<Control-C>", self._copy_selection)
        self._inner_text.bind("<Control-a>", self._select_all_text)
        self._inner_text.bind("<Control-A>", self._select_all_text)

        # 声：タブ方式。順番は「プリセット ／ 声を作る ／ 保存した声」。
        # エンジンにより使えない組み合わせは _apply_engine_gating でグレーアウトする。
        self._voice_tab_keys = ["tab_preset", "tab_design", "tab_saved"]
        self.voice_tabview = ctk.CTkTabview(self, height=200, anchor="nw",
                                            command=self._on_voice_tab_change)
        self.voice_tabview.pack(fill="x", padx=16, pady=(8, 0))
        self._voice_tab_names = {}
        for _k in self._voice_tab_keys:
            _name = self._tab_label(_k)
            self.voice_tabview.add(_name)
            self._voice_tab_names[_k] = _name

        # --- プリセットタブ（Qwen専用。Irodoriではグレーアウト）---
        preset_tab = self.voice_tabview.tab(self._voice_tab_names["tab_preset"])
        self.voice_menu = ctk.CTkOptionMenu(preset_tab, values=["—"],
                                            command=self._on_voice_change)
        self.voice_menu.pack(anchor="w", padx=4, pady=(4, 0))
        # 喋り方（感情・スタイル）欄。Qwenのみ有効、Irodoriはグレーアウト。
        self.lbl_style_preset = ctk.CTkLabel(preset_tab, text="")
        self.lbl_style_preset.pack(anchor="w", padx=4, pady=(8, 0))
        self.style_preset_entry = ctk.CTkEntry(preset_tab)
        self.style_preset_entry.pack(fill="x", padx=4, pady=(2, 4))
        # 通常時の背景色を控えておく（無効時はグレー背景にして見た目でも分かるようにする）。
        # 空の CTkEntry は disabled だけだと見た目が変わらないため、背景色でも明示する。
        self._entry_fg_normal = self.style_preset_entry.cget("fg_color")
        self._entry_fg_disabled = ("gray82", "gray28")

        # --- 声を作る（VoiceDesign）タブ（Qwen/Irodori 両対応）---
        design_tab = self.voice_tabview.tab(self._voice_tab_names["tab_design"])
        self.lbl_design = ctk.CTkLabel(design_tab, text="")
        self.lbl_design.pack(anchor="w", padx=4, pady=(4, 0))
        # 声の説明は複数行書けるよう、タブ内の空きスペースを埋めて広く取る
        # （固定 height=64 だと3行ぶんしか見えず窮屈だった）。
        self.design_box = ctk.CTkTextbox(design_tab, height=130, wrap="word")
        self.design_box.pack(fill="both", expand=True, padx=4, pady=(2, 4))

        # --- 保存した声タブ（Qwen/Irodori 両対応）---
        saved_tab = self.voice_tabview.tab(self._voice_tab_names["tab_saved"])
        pick_row = ctk.CTkFrame(saved_tab, fg_color="transparent")
        pick_row.pack(fill="x", padx=4, pady=(4, 0))
        self.btn_pick_mvsvoice = ctk.CTkButton(pick_row, text="", width=120,
                                               command=self._on_pick_mvsvoice)
        self.btn_pick_mvsvoice.pack(side="left")
        self.lbl_saved_file = ctk.CTkLabel(pick_row, text="", anchor="w")
        self.lbl_saved_file.pack(side="left", padx=(8, 0), fill="x", expand=True)
        self.dnd_zone = tk.Label(saved_tab, text="", relief="groove", bd=1,
                                 height=2, fg="#666666", bg="#f5f5f5")
        self.dnd_zone.pack(fill="x", padx=4, pady=(6, 0))
        try:
            self.dnd_zone.drop_target_register(DND_FILES)
            self.dnd_zone.dnd_bind("<<Drop>>", self._on_drop_mvsvoice)
        except Exception:
            pass   # DnD が使えない環境では「ファイルを選択」だけ使える
        # 喋り方欄（保存した声）。Qwenのみ有効、Irodoriはグレーアウト。
        self.lbl_style_saved = ctk.CTkLabel(saved_tab, text="")
        self.lbl_style_saved.pack(anchor="w", padx=4, pady=(8, 0))
        self.style_saved_entry = ctk.CTkEntry(saved_tab)
        self.style_saved_entry.pack(fill="x", padx=4, pady=(2, 4))

        # 速度・音量・ピッチ。広いと横1行、狭いと縦3段に自動で組み替える。
        controls_row = ctk.CTkFrame(self, fg_color="transparent")
        controls_row.pack(fill="x", padx=16, pady=(10, 0))
        g_speed, self.lbl_speed, self.speed_slider, self.speed_value_label = \
            self._make_slider_group(controls_row, self._on_speed_change,
                                    dict(from_=0.5, to=2.0, number_of_steps=15))
        self.speed_slider.set(1.0)
        g_vol, self.lbl_volume, self.volume_slider, self.volume_value_label = \
            self._make_slider_group(controls_row, self._on_volume_change,
                                    dict(from_=0.0, to=2.0, number_of_steps=40))
        self.volume_slider.set(1.0)
        g_pitch, self.lbl_pitch, self.pitch_slider, self.pitch_value_label = \
            self._make_slider_group(controls_row, self._on_pitch_change,
                                    dict(from_=-12, to=12, number_of_steps=24), value_width=56)
        self.pitch_slider.set(0)
        self._slider_groups = [g_speed, g_vol, g_pitch]
        self._sliders_layout = None
        self._relayout_sliders("h")   # 初期は横1行（直後の Configure で幅に応じて補正）
        self.bind("<Configure>", self._on_window_configure)

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
        # 進捗バー。生成中は常に出す。
        #   分割しないとき … 左右に動く「不確定バー」（処理中表示）
        #   2チャンク以上に分割されたとき … 「完了数/全数」の確定バー
        self._busy_bar = ctk.CTkProgressBar(wave_frame, mode="indeterminate")
        self._busy_bar.set(0)

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

    def _make_slider_group(self, parent, command, slider_kwargs, value_width=48):
        """「ラベル＋短いスライダー＋数値」の1組を作る（パックは _relayout_sliders 側）。

        戻り値は (グループframe, ラベル, スライダー, 数値ラベル)。
        """
        g = ctk.CTkFrame(parent, fg_color="transparent")
        lbl = ctk.CTkLabel(g, text="")
        lbl.pack(side="left")
        val = ctk.CTkLabel(g, text="", width=value_width, anchor="w")
        val.pack(side="right")
        # CTkSlider の既定幅(約200px)は3本横並びだと収まらず右端が見切れる。
        # 小さめの幅にしておき、横に余裕があれば fill/expand で伸びるようにする。
        sld = ctk.CTkSlider(g, command=command, width=70, **slider_kwargs)
        sld.pack(side="left", fill="x", expand=True, padx=(6, 4))
        return g, lbl, sld, val

    def _relayout_sliders(self, layout: str):
        """速度・音量・ピッチの3組を、横1行（h）/縦3段（v）に組み替える。"""
        if layout == self._sliders_layout:
            return
        self._sliders_layout = layout
        for g in self._slider_groups:
            g.pack_forget()
        if layout == "h":
            # 横1行：等幅で並べ、組の間に少し余白（詰まりすぎ＆見切れ防止）
            for i, g in enumerate(self._slider_groups):
                g.pack(side="left", fill="x", expand=True, padx=((10 if i else 0), 0))
        else:
            # 縦3段：各組を全幅で積む
            for i, g in enumerate(self._slider_groups):
                g.pack(side="top", fill="x", pady=((8 if i else 0), 0))

    def _on_window_configure(self, event):
        """ウィンドウのリサイズを監視し、幅に応じて横1行/縦3段を切り替える。"""
        if event.widget is not self:
            return   # 子ウィジェットの Configure は無視（トップレベルのみ）
        want = "v" if event.width < SLIDERS_WRAP_WIDTH else "h"
        if want != self._sliders_layout:   # 閾値をまたいだときだけ組み替え（チラつき防止）
            self._relayout_sliders(want)

    # ---- 言語の切り替え -----------------------------------------------------
    def _on_language_change(self, lang_label: str):
        # 表示言語は保存しない（毎回 OS の言語から始める）。切替は今の表示にだけ反映。
        code = self._lang_label_to_code.get(lang_label, i18n.DEFAULT_LANG)
        self._apply_language(code)

    def _apply_language(self, lang: str):
        """画面に出ている文字を、指定言語に一括で貼り替える。"""
        self._lang = lang

        # 言語トグルの選択表示を現在の言語に合わせる（プログラム的変更でも追従）
        self.lang_btn.set(i18n.LANGUAGES[lang])

        # ラベル類
        self.lbl_audio_lang.configure(text=self._t("label_audio_language"))
        self.lbl_speed.configure(text=self._t("label_speed"))
        self.lbl_volume.configure(text=self._t("label_volume"))
        self.lbl_pitch.configure(text=self._t("label_pitch"))
        self.btn_open_file.configure(text=self._t("btn_open_file"))
        self.chk_append.configure(text=self._t("chk_append"))
        self._refresh_menubar_labels()

        # 声タブの見出し（タブ名）を言語に合わせて貼り替える
        for _k in self._voice_tab_keys:
            _new = self._tab_label(_k)
            _old = self._voice_tab_names[_k]
            if _new != _old:
                self.voice_tabview.rename(_old, _new)
                self._voice_tab_names[_k] = _new
        # 「保存した声」タブの中身（ボタン・ドロップ案内・ファイル名表示）
        self.btn_pick_mvsvoice.configure(text=self._t("btn_pick_mvsvoice"))
        self.dnd_zone.configure(text=self._t("dnd_hint"))
        self._refresh_saved_file_label()
        # 「声を作る」「喋り方」欄のラベル
        self.lbl_design.configure(text=self._t("label_design"))
        self.lbl_style_preset.configure(text=self._t("label_style"))
        self.lbl_style_saved.configure(text=self._t("label_style"))

        # 声・音声言語プルダウンの中身（各項目＋選択中の表示）も新しい言語で作り直す
        self._relabel_voices()
        self._relabel_audio_languages()

        # 再生・停止ボタン（生成ボタンの文字は状態によるので _set_state で）
        self.play_btn.configure(text=self._t("btn_play"))
        self.stop_btn.configure(text=self._t("btn_stop"))
        self.btn_save_voice_file.configure(text=self._t("btn_save_voice_file"))
        self.btn_save_audio_file.configure(text=self._t("btn_save_audio_file"))
        self._set_state(self._state)  # 生成ボタンの文字を今の状態に合わせて貼り直す

        # 速度・音量・ピッチの数値表示
        self.speed_value_label.configure(
            text=self._t("speed_value", v=round(float(self.speed_slider.get()), 1))
        )
        self._on_volume_change(self.volume_slider.get())
        self._on_pitch_change(self.pitch_slider.get())

        # テキスト欄が手つかずなら案内文を言語に合わせて差し替える
        self._maybe_update_placeholder()

        # 波形（音声があれば描き直し、無ければ案内文）
        if self._wav_data is not None:
            self._draw_waveform(self._wav_data, self._wav_sr)
        else:
            self._init_waveform_placeholder()

        # ステータス（今の内容を新しい言語で出し直す）
        self._render_status()

    def _placeholder_text(self) -> str:
        """案内文。表示言語ではなく『音声言語』に合わせる（箱の外のラベルに出す）。"""
        code = AUDIO_LANG_TO_I18N.get(self._current_audio_lang, self._lang)
        return i18n.t(code, "textbox_placeholder")

    def _maybe_update_placeholder(self):
        """テキスト欄が手つかず（案内文のまま／空）なら、案内文を言語に合わせて差し替える。"""
        current = self.text_box.get("1.0", "end").strip()
        placeholders = {i18n.t(code, "textbox_placeholder") for code in i18n.translations}
        if current == "" or current in placeholders:
            self.text_box.delete("1.0", "end")
            self.text_box.insert("1.0", self._placeholder_text())

    def _actual_text(self) -> str:
        """テキスト欄の中身（案内文も含め、そのまま）。"""
        return self.text_box.get("1.0", "end").strip()

    # ---- コピー（Ctrl+C）/ 全選択（Ctrl+A）--------------------------------
    def _copy_selection(self, event=None):
        try:
            sel = self._inner_text.get("sel.first", "sel.last")
        except Exception:
            return "break"   # 選択が無ければ何もしない
        if sel:
            self.clipboard_clear()
            self.clipboard_append(sel)
        return "break"

    def _select_all_text(self, event=None):
        self._inner_text.tag_add("sel", "1.0", "end-1c")
        return "break"

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
        self._maybe_update_placeholder()     # 案内文を音声言語に合わせる
        self._set_state(self._state)         # エンジンに応じたグレーアウトを反映
        # 保存はアプリ終了時にまとめて行う（ここでは保存しない）

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
        # 選んだ音声言語を、表示名ではなく言語名（値）で覚えておく（音声言語は保存しない）
        self._current_audio_lang = self._audio_lang_map.get(label, self._current_audio_lang)
        self._maybe_update_placeholder()   # 案内文を音声言語に合わせる

    def _on_speed_change(self, value):
        self.speed_value_label.configure(
            text=self._t("speed_value", v=round(float(value), 1))
        )

    def _on_volume_change(self, value):
        self.volume_value_label.configure(
            text=self._t("volume_value", v=int(round(float(value) * 100)))
        )

    def _on_pitch_change(self, value):
        n = int(round(float(value)))
        shown = f"+{n}" if n > 0 else str(n)
        self.pitch_value_label.configure(text=self._t("pitch_value", v=shown))

    # ---- ファイル読み込み（txt / PDF / Word → テキスト欄）-------------------
    def _on_open_file(self):
        path = filedialog.askopenfilename(
            parent=self, title=self._t("btn_open_file"),
            filetypes=[(self._t("ft_doc"), "*.txt *.pdf *.docx"),
                       (self._t("ft_text"), "*.txt"), ("PDF", "*.pdf"), ("Word", "*.docx"),
                       (self._t("ft_all"), "*.*")],
        )
        if not path:
            return
        ext = Path(path).suffix.lower()
        name = Path(path).name
        try:
            if ext == ".txt":
                text = self._read_txt(path)
            elif ext == ".pdf":
                text = self._read_pdf(path)
            elif ext == ".docx":
                text = self._read_docx(path)
            else:
                self._set_status("open_file_unsupported", error=True, name=name)
                return
        except Exception as e:
            self._set_status("open_file_error", error=True, msg=str(e))
            return
        text = (text or "").strip()
        if not text:
            self._set_status("open_file_empty", error=True, name=name)
            return
        # 「末尾に追加」がONなら今の本文の後ろに足す。OFFなら置き換える。
        # 実際に文字が入っているか（案内文のままなら空）を _actual_text() で見る。
        if self.chk_append.get():
            cur = self._actual_text()
            text = (cur + "\n" + text) if cur else text
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", text)
        self._clear_highlight()
        self._set_status("open_file_done", n=len(text), name=name)

    @staticmethod
    def _read_txt(path: str) -> str:
        # まず UTF-8、ダメなら cp932（Shift-JIS）で読み直す
        for enc in ("utf-8", "cp932"):
            try:
                return Path(path).read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        return Path(path).read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _read_pdf(path: str) -> str:
        from pypdf import PdfReader
        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    @staticmethod
    def _read_docx(path: str) -> str:
        import docx
        d = docx.Document(path)
        return "\n".join(p.text for p in d.paragraphs)

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
            parent=self, title=self._t("btn_pick_mvsvoice"),
            filetypes=[(self._t("ft_voice"), "*.mvsvoice")],
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

    # ---- 音声を保存する（選んだ拡張子の1ファイルで書き出す）---------------
    def _on_save_audio_file(self):
        """直近に生成した読み上げ音声を、選んだ拡張子（.wav か .mp3）で1つだけ保存する。"""
        if self._wav_data is None or not self.current_wav:
            self._set_status("save_audio_no_audio", error=True)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title=self._t("btn_save_audio_file"), defaultextension=".mp3",
            filetypes=[("MP3", "*.mp3"), ("WAV", "*.wav"), (self._t("ft_all"), "*.*")],
        )
        if not path:
            return
        import soundfile as sf
        # ユーザーが選んだ拡張子で1ファイルだけ書き出す（.wav なら WAV、それ以外は既定の MP3）。
        if Path(path).suffix.lower() == ".wav":
            out_path = path
            write_kwargs = {}
        else:
            out_path = str(Path(path).with_suffix(".mp3"))
            write_kwargs = {"format": "MP3"}
        try:
            sf.write(out_path, self._wav_data, self._wav_sr, **write_kwargs)
        except Exception as e:
            self._set_status("save_audio_error", error=True, msg=str(e))
            return
        self._set_status("save_audio_done", path=out_path)

    # ---- 声を保存する（.mvsvoice として書き出す）---------------------------
    def _on_save_voice_file(self):
        """直近に生成した音声を参照音声として、.mvsvoice（zip）に書き出す。"""
        if not self.current_wav or not Path(self.current_wav).exists():
            self._set_status("save_voice_no_audio", error=True)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title=self._t("btn_save_voice_file"), defaultextension=".mvsvoice",
            filetypes=[(self._t("ft_voice"), "*.mvsvoice"), (self._t("ft_all"), "*.*")],
        )
        if not path:
            return
        # 書き起こし（ref_text）はテキスト欄の本文（案内文のままなら空）。
        ref_text = self._actual_text()
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
        text = self._actual_text()   # 案内文（プレースホルダ）は本文に数えない
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
        volume = round(float(self.volume_slider.get()), 2)   # 1.0 = 100%
        pitch = round(float(self.pitch_slider.get()))         # 半音
        # 分割生成の進捗（Irodori 長文）を左下ステータスに反映する callback。
        # 別スレッドから呼ばれるので、UI 反映はメインスレッドへ（after）回す。
        progress = lambda i, n: self.after(0, self._on_chunk_progress, i, n)
        # 生成の停止用：この生成を識別するIDと、中断フラグ（Irodoriのサブプロセスを止める）
        self._gen_id += 1
        gen_id = self._gen_id
        self._cancel_event = threading.Event()
        cancel_event = self._cancel_event

        language = self._current_audio_lang
        active = self._active_voice_tab()   # "preset" | "design" | "saved"

        if active == "saved":
            # 保存した声（クローン）
            if not self._saved_voice_file:
                self._set_status("saved_file_need", error=True)
                return
            try:
                ref_wav, ref_text, mv_lang = self._extract_mvsvoice(self._saved_voice_file)
            except Exception as e:
                self._set_status("status_error", error=True, msg=str(e))
                return
            language = mv_lang or self._current_audio_lang
            style = self.style_saved_entry.get().strip() or None
            job = (lambda: synthesize_clone(engine, text, ref_wav,
                                            ref_text=ref_text, language=language,
                                            speed=speed, volume=volume, pitch=pitch,
                                            style=style, progress_callback=progress,
                                            cancel_event=cancel_event))
            voice_label = Path(self._saved_voice_file).stem
        elif active == "design":
            # 声を作る（VoiceDesign）：説明文から声を作る
            description = self.design_box.get("1.0", "end").strip()
            job = (lambda: synthesize(text, engine, mode="voice_design",
                                      voice_description=description, speed=speed,
                                      volume=volume, pitch=pitch, language=language,
                                      progress_callback=progress,
                                      cancel_event=cancel_event))
            voice_label = self._t("tab_design")
        else:
            # プリセット声（Qwen のみ喋り方=instruct を渡す。Irodori は無視される）
            voice = self._current_voice_id
            style = self.style_preset_entry.get().strip() or None
            job = (lambda: synthesize(text, engine, voice=voice, mode="preset",
                                      style=style, speed=speed, volume=volume,
                                      pitch=pitch, language=language,
                                      progress_callback=progress,
                                      cancel_event=cancel_event))
            voice_label = self.voice_menu.get()
        engine_label = ENGINE_KEY_TO_LABEL.get(engine, engine)

        # 機能⑤：ハイライトの基準は「生成したときの文章」。ここで確定して覚えておく。
        self._gen_text = text
        self._clear_highlight()

        # 生成ボタンを押したら、前回の波形をクリアする
        self._wav_data = None
        self._wav_sr = None
        self.current_wav = None
        self._init_waveform_placeholder()

        self._set_state(STATE_GENERATING)
        self._set_status("status_generating")

        threading.Thread(
            target=self._worker, args=(job, engine_label, voice_label, speed, gen_id),
            daemon=True,
        ).start()

    def _on_chunk_progress(self, i, n):
        # メインスレッドで呼ばれる（_on_speak で after 経由）。
        # 2チャンク以上に分割されたときだけ、不確定バー → 「i/n」の確定バーに切り替える。
        # 1チャンク（分割なし／Qwen）のときは何もせず、左右に動く不確定バーのままにする。
        if self._state != STATE_GENERATING or n < 2:
            return
        self._busy_bar.stop()                        # 左右の往復アニメを止め
        self._busy_bar.configure(mode="determinate")  # 確定バーに切り替え
        if not self._busy_bar.winfo_ismapped():
            self._busy_bar.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.6)
        self._busy_bar.set(i / n)   # 完了したチャンク数 / 全チャンク数
        self._set_status("status_generating_progress", i=i, n=n)

    def _worker(self, job, engine_label, voice_label, speed, gen_id):
        try:
            wav = job()
            self._result_queue.put(("done", wav, engine_label, voice_label, speed, gen_id))
        except Exception as e:
            self._result_queue.put(("error", str(e), gen_id))

    def _poll_result(self):
        try:
            while True:
                item = self._result_queue.get_nowait()
                # 停止された生成（ID不一致）の結果は無視する
                if item[-1] != self._gen_id:
                    continue
                if item[0] == "done":
                    _, wav, engine_label, voice_label, speed, _ = item
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

        # 機能⑤：完成音声の長さを、各文の文字数で按分してハイライトの時間割を作る
        self._build_highlight_timeline(self._gen_text, self._audio_duration)

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
        # 生成中の停止：実行中の生成を無効化し、Irodori のサブプロセスは中断フラグで止める。
        if self._state == STATE_GENERATING:
            self._cancel_generation()
            return
        # 再生中の停止：再生を止める。
        self._cancel_cursor()
        try:
            player.stop()
        except Exception:
            pass
        self._move_cursor(0)
        self._stop_highlight()   # 機能⑤：停止でハイライトを止める（時間割は残す）
        self._set_state(STATE_READY)
        self._set_status("status_stopped")

    def _cancel_generation(self):
        """生成を停止する。結果は ID 不一致で無視され、UI はすぐ操作可能に戻る。"""
        self._gen_id += 1             # 実行中の生成の結果を無効化（無視させる）
        if self._cancel_event is not None:
            self._cancel_event.set()  # Irodori のサブプロセスを止める合図
        self._set_state(STATE_READY if self.current_wav else STATE_IDLE)
        self._set_status("status_gen_stopped")

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
        self._update_highlight(elapsed)   # 機能⑤：いま読んでいる文を光らせる
        self._schedule_cursor()

    def _on_playback_finished(self):
        self._cursor_after_id = None
        self._move_cursor(0)
        self._stop_highlight()   # 色は消すが時間割は残す（再生し直せば再び光る）
        self._set_state(STATE_READY)
        self._set_status("status_finished")

    # ---- 機能⑤：読み上げ位置のハイライト ----------------------------------
    def _build_highlight_timeline(self, text: str, duration: float):
        """文に分割し、総再生時間を文字数比で按分して各文の再生時間帯を作る。"""
        self._sentence_spans = self._sentence_spans_of(text)
        self._sentence_timeline = []
        self._hl_current = -1
        total = sum(e - s for s, e in self._sentence_spans)
        if total <= 0 or duration <= 0:
            return
        t = 0.0
        for s, e in self._sentence_spans:
            dur = duration * (e - s) / total
            self._sentence_timeline.append((t, t + dur))
            t += dur

    @staticmethod
    def _sentence_spans_of(text: str) -> list[tuple[int, int]]:
        """「。」「！」「？」「改行」で文に分け、各文の文字インデックス [start,end) を返す。"""
        spans = []
        start = 0
        for idx, ch in enumerate(text):
            if ch in "。！？\n":
                spans.append((start, idx + 1))
                start = idx + 1
        if start < len(text):
            spans.append((start, len(text)))
        # 空白だけの区間は除外（位置インデックスはそのまま）
        return [(s, e) for s, e in spans if text[s:e].strip()]

    def _update_highlight(self, elapsed: float):
        """経過秒に対応する文だけ背景色を付ける（前の文の色は消す）。"""
        if not self._sentence_timeline:
            return
        idx = -1
        for i, (t0, t1) in enumerate(self._sentence_timeline):
            if t0 <= elapsed < t1:
                idx = i
                break
        if idx == self._hl_current:
            return
        self._hl_current = idx
        self._inner_text.tag_remove("hl", "1.0", "end")
        if 0 <= idx < len(self._sentence_spans):
            s, e = self._sentence_spans[idx]
            self._inner_text.tag_add("hl", f"1.0+{s}c", f"1.0+{e}c")

    def _stop_highlight(self):
        """ハイライトの色だけ消す（停止・再生終了時）。時間割は残し、再生し直せば再び光る。"""
        self._hl_current = -1
        try:
            self._inner_text.tag_remove("hl", "1.0", "end")
        except Exception:
            pass

    def _clear_highlight(self):
        """ハイライトを完全に消す（テキスト編集・新規生成時）。時間割も無効化する。"""
        self._sentence_timeline = []
        self._stop_highlight()

    def _cancel_cursor(self):
        if self._cursor_after_id is not None:
            try:
                self.after_cancel(self._cursor_after_id)
            except Exception:
                pass
            self._cursor_after_id = None

    # ---- 状態とステータス ---------------------------------------------------
    def _tab_label(self, key: str) -> str:
        """タブ見出しの文字。左右に空白を足して、タブ同士の文字がくっつかないようにする。"""
        return "   " + self._t(key) + "   "

    def _active_voice_tab(self) -> str:
        """選択中の声タブを返す（"preset" / "design" / "saved"）。"""
        try:
            cur = self.voice_tabview.get()
        except Exception:
            return "preset"
        for key in ("tab_preset", "tab_design", "tab_saved"):
            if self._voice_tab_names.get(key) == cur:
                return key[len("tab_"):]
        return "preset"

    def _is_saved_tab_active(self) -> bool:
        """「保存した声」タブが選ばれているか。"""
        return self._active_voice_tab() == "saved"

    # ---- メニューバー -------------------------------------------------------
    def _build_menubar(self):
        """ウィンドウ上部のメニューバーを作る。

        構成：ヘルプ ＞ ［問題を報告 ／ ──区切り── ／ バージョン情報（About）］
        ・問題を報告 … Google フォームを直接ブラウザで開く（_open_issue）
        ・About      … アプリ名・バージョン・注意書きのダイアログ（_show_info）。一番下。
        言語切り替え時にラベルを貼り替えられるよう、メニューを保持する。
        """
        # フォントは既定（TkMenuFont）のまま。Windows のメニューバー本体（"ヘルプ"）は
        # OS が描画してサイズを変えられないため、ドロップダウンだけ拡大すると不揃いになる。
        # ネイティブの tk メニュー（CTk は configure(menu=...) を Tk に通す）。
        # tearoff=0 を付けないと index 0 がティアオフ線になり、entryconfigure(0) が
        # カスケードでなくティアオフを指して "unknown option -label" で落ちる。
        menubar = tk.Menu(self, tearoff=0)
        help_menu = tk.Menu(menubar, tearoff=0)

        # ヘルプ ＞ 問題を報告（押すと Google フォームを直接開く）
        help_menu.add_command(label=self._t("menu_report"), command=self._open_issue)
        help_menu.add_separator()
        # ヘルプ ＞ バージョン情報（About）。区切り線の下＝一番下に配置。
        help_menu.add_command(label=self._t("info_title"), command=self._show_info)
        menubar.add_cascade(label=self._t("menu_help"), menu=help_menu)

        self.configure(menu=menubar)
        # 言語追従用に保持（各 entry の位置は固定）。
        self._menubar = menubar
        self._help_menu = help_menu

    def _refresh_menubar_labels(self):
        """表示言語が変わったらメニューのラベルを貼り替える。"""
        if getattr(self, "_menubar", None) is None:
            return
        # index は _build_menubar の追加順（report=0 / separator=1 / about=2）。
        self._menubar.entryconfigure(0, label=self._t("menu_help"))
        self._help_menu.entryconfigure(0, label=self._t("menu_report"))
        self._help_menu.entryconfigure(2, label=self._t("info_title"))

    # ---- 情報ダイアログ -----------------------------------------------------
    def _open_issue(self):
        """「問題を報告」：報告用の Google フォームを既定のブラウザで開く。"""
        try:
            webbrowser.open(REPORT_FORM_URL)
        except Exception:
            pass

    def _show_info(self):
        """右上の情報ボタン。アプリ名・バージョン・問題報告のダイアログを出す。"""
        # すでに開いていれば、二重に開かず前面に出すだけ。
        win = getattr(self, "_info_win", None)
        if win is not None and win.winfo_exists():
            win.lift(); win.focus()
            return

        win = ctk.CTkToplevel(self)
        self._info_win = win
        win.title(self._t("info_title"))
        win.resizable(False, False)
        win.transient(self)
        # 親ウィンドウの中央あたりに出す
        self.update_idletasks()
        w, h = 440, 240
        px, py = self.winfo_rootx(), self.winfo_rooty()
        pw = self.winfo_width()
        x = px + max(0, (pw - w) // 2)
        y = py + 80
        win.geometry(f"{w}x{h}+{x}+{y}")

        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)
        # アプリ名（見出し）
        ctk.CTkLabel(body, text=APP_NAME, anchor="w",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w")
        # 補足（任意）：生成物の注意書き
        ctk.CTkLabel(body, text=self._t("info_note"), anchor="w", justify="left",
                     wraplength=w - 56).pack(anchor="w", pady=(8, 0))
        # バージョン
        ctk.CTkLabel(body, text=f'{self._t("info_version")}: {APP_VERSION}',
                     anchor="w", text_color=("gray40", "gray60")).pack(anchor="w", pady=(10, 0))
        # ボタン行：右「閉じる」のみ（問題報告は「お問い合わせ」ダイアログに移動）
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")
        ctk.CTkButton(btn_row, text=self._t("btn_close"),
                      command=win.destroy).pack(side="right")

        # モーダル化（CTkToplevel はアイコン反映が遅れるので少し待ってから grab）
        win.after(150, win.lift)
        win.after(200, win.grab_set)

    def _set_entry_enabled(self, entry, enabled: bool):
        """入力欄を有効/無効にする。無効時は背景もグレーにして見た目で分かるようにする。"""
        if enabled:
            entry.configure(state="normal", fg_color=self._entry_fg_normal)
        else:
            # disabled の前に背景色を変える（disabled 中は一部設定が反映されないため）
            entry.configure(fg_color=self._entry_fg_disabled)
            entry.configure(state="disabled")

    def _set_state(self, state: str):
        self._state = state
        speak_on = state in (STATE_IDLE, STATE_READY, STATE_PLAYING)
        # 「保存した声」タブのときは、ファイルが選ばれていないと生成できない
        if self._is_saved_tab_active() and self._saved_voice_file is None:
            speak_on = False
        play_on = state == STATE_READY
        # 停止ボタンは「再生中」だけでなく「生成中」も有効（生成を止められる）
        stop_on = state in (STATE_PLAYING, STATE_GENERATING)
        # 生成中・再生中はエンジン／声を変えられないようにする（待機中だけ操作可）
        controls_on = state in (STATE_IDLE, STATE_READY)
        self.speak_btn.configure(
            state="normal" if speak_on else "disabled",
            text=self._t("btn_generating") if state == STATE_GENERATING else self._t("btn_generate"),
        )
        self.play_btn.configure(state="normal" if play_on else "disabled")
        self.stop_btn.configure(state="normal" if stop_on else "disabled")
        self.engine_btn.configure(state="normal" if controls_on else "disabled")
        # 生成中・再生中はタブ（プリセット／声を作る／保存した声）の切り替えも無効化
        self.voice_tabview.configure(state="normal" if controls_on else "disabled")
        # エンジンによる出し分け。
        #  ・声のプルダウン：両エンジンで使える（Irodori も「デフォルト」や説明文ベースの
        #    声を選べるようにする）。待機中のみ操作可。
        #  ・「喋り方（感情・スタイル）」欄：Qwen 専用。Irodori は感情を独立指定できない
        #    （caption 同居／本文の絵文字）ため、グレーアウトする。
        is_irodori = (self._engine == "irodori")
        self.voice_menu.configure(state="normal" if controls_on else "disabled")
        style_on = controls_on and not is_irodori
        # 「喋り方」欄（プリセット／保存した声）は状態＋背景色の両方でグレーアウトする
        self._set_entry_enabled(self.style_preset_entry, style_on)
        self._set_entry_enabled(self.style_saved_entry, style_on)
        # 「声を作る」の説明欄は両エンジン対応（待機中だけ編集可）
        self.design_box.configure(state="normal" if controls_on else "disabled")
        # 機能①：生成中はテキストを編集できないようにする（音声と文章のズレ防止）。
        # 別スレッドからではなく、必ずこのメインスレッドの状態更新で切り替える。
        self.text_box.configure(state="disabled" if state == STATE_GENERATING else "normal")
        self.btn_open_file.configure(state="disabled" if state == STATE_GENERATING else "normal")
        # 保存ボタンは、保存するもの（生成済み音声）が無いときは無効
        save_on = self._wav_data is not None
        self.btn_save_audio_file.configure(state="normal" if save_on else "disabled")
        self.btn_save_voice_file.configure(state="normal" if save_on else "disabled")

        # 生成中はバーを表示。既定は左右に動く不確定バー（分割しないときの処理中表示）。
        # 2チャンク以上に分割されたら _on_chunk_progress で i/n の確定バーに切り替える。
        if state == STATE_GENERATING:
            self._busy_bar.configure(mode="indeterminate")
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
        # アプリ終了時に、最小限の設定（エンジン・声）とウィンドウ位置を保存する
        self._save_settings()
        self._save_window_state()
        self._cancel_cursor()
        try:
            player.stop()
        except Exception:
            pass
        self.destroy()
        # torch+CUDA / PortAudio(sounddevice) を積んだGUIは、通常のインタプリタ
        # 終了処理だと後始末が長時間化・ハングし、数GBのモデルを抱えたまま
        # プロセスが居残る（＝終了後もPCが重い）。設定は上で保存済みなので、
        # ここで確実にプロセスを落として OS に全メモリ(VRAM/RAM)を即時回収させる。
        os._exit(0)


if __name__ == "__main__":
    TTSApp().mainloop()
