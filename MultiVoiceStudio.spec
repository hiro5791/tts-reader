# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# MultiVoiceStudio.spec — PyInstaller ビルド定義（雛形）
#
#   使い方（配布ビルド環境で）:  pyinstaller MultiVoiceStudio.spec
#
#   これは「出発点の雛形」です。torch / irodori_tts / numba などは隠れ依存・
#   データファイルが多く、ビルド機で「足りないモジュール/データを足す」試行錯誤が
#   前提になります（下の "よくある不足" コメントと 配布手順書 を参照）。
#
#   形式は onedir（COLLECT）。onefile より起動が速く、MSIX 化もしやすい。
# =============================================================================

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)  # この .spec があるフォルダ（PyInstaller が定義）

datas, binaries, hiddenimports = [], [], []

# --- 隠れ依存・データの多いパッケージは collect_all でまとめて取り込む ---------
#   失敗しても止めない（ビルド機で個別に対処する）。
_COLLECT = [
    "torch", "torchaudio", "torchcodec", "numba", "llvmlite",
    "sentencepiece", "safetensors", "soundfile", "librosa",
    "customtkinter", "tkinterdnd2", "matplotlib",
    "huggingface_hub", "transformers", "peft",
    "dacvae", "silentcipher", "irodori_tts", "qwen_tts",
    # dacvae が内部で使う音声ツール群（データファイル headers.html 等を同梱するため）
    "audiotools", "encodec",
]
for pkg in _COLLECT:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:  # noqa: BLE001
        print(f"[spec] collect_all 失敗（ビルド機で対処）: {pkg}: {e}")

# --- アプリ同梱データ ---------------------------------------------------------
# Irodori の設定ファイル（推論時に参照されることがある）
_cfg = ROOT / "vendor" / "Irodori-TTS" / "configs"
if _cfg.exists():
    datas.append((str(_cfg), "vendor/Irodori-TTS/configs"))

# ライセンス表示（ストア配布で同梱必須）
_notices = ROOT / "THIRD-PARTY-NOTICES.md"
if _notices.exists():
    datas.append((str(_notices), "."))

# version.txt(?????)???????? app.py ????
_ver = ROOT / "version.txt"
if _ver.exists():
    datas.append((str(_ver), "."))

# 同梱モデル（HuggingFace キャッシュ）。
#   ★既定は「非同梱」★（Microsoft Store 提出版＝約3GB・初回起動時に HF からDL）。
#   モデルを同梱した「オフライン動作版（約15-18GB）」が必要なときだけ、
#   環境変数 MVS_BUNDLE_MODELS=1 を明示的に立ててビルドする。
#     事前に  HF_HOME=<models>  python scripts/prefetch_models.py  で集めておく。
#     置き場所は MVS_MODELS_DIR で差し替え可能（既定 ROOT/models）。
#   ※「models/ があれば自動同梱」だと、開発で prefetch しただけで巨大MSIXが
#     できてしまい事故るため、明示オプトインにしている（再発防止）。
_bundle_models = os.environ.get("MVS_BUNDLE_MODELS", "").strip().lower() in ("1", "true", "yes", "on")
_models_env = os.environ.get("MVS_MODELS_DIR")
_models = Path(_models_env) if _models_env else (ROOT / "models")
if _bundle_models and _models.exists():
    datas.append((str(_models), "models"))
    print(f"[spec] モデルを同梱します（MVS_BUNDLE_MODELS=1・オフライン版・約15-18GB）: {_models}")
elif _bundle_models:
    print(f"[spec] 警告: MVS_BUNDLE_MODELS=1 ですが {_models} が無いため非同梱でビルドします。")
else:
    print("[spec] モデル非同梱（Store提出と同じ約3GB構成・実行時にHFからDL）。"
          "オフライン同梱版が要るときは MVS_BUNDLE_MODELS=1 を設定して再ビルド。")

# --- 解析 ---------------------------------------------------------------------
a = Analysis(
    ["app.py"],
    # irodori_tts は site-packages に入れるのが基本だが、vendor から読む場合に備え pathex にも追加
    pathex=[str(ROOT), str(ROOT / "vendor" / "Irodori-TTS")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "irodori_tts.inference_runtime",
        "tts.adapter", "tts.qwen_engine", "tts.qwen_design_engine",
        "tts.clone_engine", "tts.irodori_engine", "tts.audio_utils", "tts.player", "tts.paths", "tts.device",
        "i18n",
    ],
    hookspath=[],
    runtime_hooks=[],
    # 実行に不要で、かつ MSIX のパス長制限に引っかかる/巨大なものは除外する。
    #   jedi/IPython … 対話補完用。アプリ（GUI）では使わない。jedi の typeshed は
    #     超深い階層の .pyi を大量に含み、MSIX パック時に 0x8007007B で失敗する原因。
    excludes=["jedi", "IPython", "ipykernel", "notebook"],
    noarchive=False,
)
# python-docx が同梱する「展開済み Word テンプレート」は OPC 予約名
# （[Content_Types].xml / _rels / *.rels）を含み、MSIX 化(makeappx)が 0x8007007B で失敗する。
# 読み込み用途では不要（zip版 default.docx を使う）なので、同梱データから除外する。
a.datas = [d for d in a.datas
           if "default-docx-template" not in str(d[0]).replace("\\", "/")]

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MultiVoiceStudio",
    console=False,        # GUI アプリ（コンソール非表示）
    # icon="assets/app.ico",   # .ico を用意したら指定
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="MultiVoiceStudio",   # dist/MultiVoiceStudio/ に出力（onedir）
)

# =============================================================================
# よくある不足とその対処（ビルド機で発生したら）:
#   - ModuleNotFoundError: xxx   → hiddenimports に "xxx" を足す
#       （または collect_submodules("親パッケージ") を使う）
#   - データが無いと言われる     → datas に (元パス, 配置先) を足す
#   - torch の CUDA DLL が無い    → collect_all("torch") で大抵入るが、
#       足りなければ NVIDIA の cuda*/cudnn*/*.dll を binaries に追加
#   - numba/llvmlite のエラー     → collect_all 済み。だめなら *.dll を binaries に
#   - tkinterdnd2 の tkdnd が無い  → collect_all 済み。だめなら tkdnd フォルダを datas に
#   - matplotlib のフォント/データ → collect_all 済み。バックエンドは TkAgg を使用
# =============================================================================
