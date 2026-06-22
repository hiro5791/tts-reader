"""Qwen3-TTS アダプタ。

pip install した qwen-tts パッケージを使って、日本語のプリセット話者で読み上げる。
モデルの読み込みは重いので、初回だけ読み込んでメモリに置いておき、2回目以降は使い回す。

このエンジンの仕様メモ:
  - 話者（声）… プリセット話者を speaker で指定する（9種類）。言語は japanese 固定。
  - 速度       … generate_custom_voice に速度パラメータが無いため、
                 生成後にタイムストレッチ（ピッチ保持）で速度を変える。
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path


# ---- 最小版からの固定設定 ----------------------------------------------------

# 使うモデル。8GBのGPUなら 1.7B でだいたい動く。
# もし VRAM 不足のエラーが出たら、下を 0.6B 版に変えると軽くなる：
#   "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
MODEL_NAME = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"

# ---- 音声の言語（声が何語として読み上げるか）--------------------------------
# Qwen3-TTS が対応する言語。モデル設定 config.json の codec_language_id に基づく。
# (表示名の i18n キー, generate_custom_voice の language に渡す値)
# language は英語名（先頭大文字）で渡す。表示名は i18n.py に持たせ、表示言語に追従させる。
LANGUAGES = [
    ("audiolang_japanese", "Japanese"),
    ("audiolang_english", "English"),
    ("audiolang_chinese", "Chinese"),
    ("audiolang_korean", "Korean"),
    ("audiolang_german", "German"),
    ("audiolang_french", "French"),
    ("audiolang_russian", "Russian"),
    ("audiolang_portuguese", "Portuguese"),
    ("audiolang_spanish", "Spanish"),
    ("audiolang_italian", "Italian"),
]
DEFAULT_LANGUAGE = "English"
_VALID_LANGUAGES = {val for _key, val in LANGUAGES}

# 出力先フォルダ
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

# ---- 選べる声（プリセット話者）-----------------------------------------------
# (表示名の i18n キー, 内部の話者ID) の組。日本語ネイティブの ono_anna を先頭（初期値）にする。
# 表示名は i18n.py の辞書に持たせ、表示言語の切り替えに追従させる（話者名は固定表記）。
# どの話者も language="Japanese" で日本語を読み上げられる。
VOICES = [
    ("voice_ono_anna", "ono_anna"),
    ("voice_serena", "serena"),
    ("voice_vivian", "vivian"),
    ("voice_sohee", "sohee"),
    ("voice_aiden", "aiden"),
    ("voice_ryan", "ryan"),
    ("voice_dylan", "dylan"),
    ("voice_eric", "eric"),
    ("voice_uncle_fu", "uncle_fu"),
]

DEFAULT_VOICE = "ono_anna"

# ------------------------------------------------------------------------------

# 読み込んだモデルを覚えておく場所（最初は None）
_model = None


def list_voices() -> list[tuple[str, str]]:
    """選べる声の一覧 (表示名の i18n キー, 声ID) を返す。"""
    return list(VOICES)


def list_languages() -> list[tuple[str, str]]:
    """選べる音声の言語の一覧 (表示名の i18n キー, 言語名) を返す。"""
    return list(LANGUAGES)


def _get_model():
    """モデルを（初回だけ）読み込んで返す。2回目以降は使い回す。"""
    global _model
    if _model is not None:
        return _model

    # 重いインポートはここで（このエンジンを実際に使うときだけ）
    import torch
    from qwen_tts import Qwen3TTSModel

    # GPU が使えるか確認。使えなければ CPU（とても遅い）になる。
    if torch.cuda.is_available():
        device = "cuda:0"
        dtype = torch.float16  # float16 は GPU で安定して速い
    else:
        device = "cpu"
        dtype = torch.float32

    print(f"[Qwen3] モデルを読み込みます（初回は時間がかかります）: {MODEL_NAME} on {device}")
    _model = Qwen3TTSModel.from_pretrained(
        MODEL_NAME,
        device_map=device,
        dtype=dtype,
        # flash_attention_2 は Windows で入れにくいので sdpa を使う（どの環境でも動く）
        attn_implementation="sdpa",
    )
    print("[Qwen3] モデルの読み込みが終わりました。")
    return _model


def synthesize(text: str, voice: str = DEFAULT_VOICE,
               language: str = DEFAULT_LANGUAGE, progress_callback=None,
               cancel_event=None) -> str:
    """テキストを Qwen3-TTS で読み上げ、生の wav ファイルのパスを返す。

    voice    … プリセット話者ID（VOICES の右側の値）
    language … 何語として読み上げるか（LANGUAGES の右側の値。例 "Japanese"）。
    progress_callback … 受け取るが Qwen は分割しないので未使用（アダプタ方式の互換用）。

    速度・音量・ピッチは共通層（adapter）の後処理で適用するため、ここでは生の音声を返す。
    Qwen3 は長文でも分割せず一度に生成する（10分超でも崩れない設計のため）。
    """
    import soundfile as sf

    speaker = voice or DEFAULT_VOICE
    if language not in _VALID_LANGUAGES:
        language = DEFAULT_LANGUAGE
    model = _get_model()

    wavs, sr = model.generate_custom_voice(
        text=text,
        language=language,
        speaker=speaker,
    )
    audio = wavs[0]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_path = OUTPUT_DIR / f"qwen3_{stamp}.wav"
    sf.write(str(out_path), audio, sr)
    print(f"[Qwen3] 音声を書き出しました（話者={speaker}, 言語={language}）: {out_path}")
    return str(out_path)
