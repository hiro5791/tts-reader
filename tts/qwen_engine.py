"""Qwen3-TTS アダプタ。

pip install した qwen-tts パッケージを使って、日本語のプリセット話者で読み上げる。
モデルの読み込みは重いので、初回だけ読み込んでメモリに置いておき、2回目以降は使い回す。
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

# ---- 最小版の固定設定（後で変えやすいように、ここにまとめる）-----------------

# 使うモデル。8GBのGPUなら 1.7B でだいたい動く。
# もし VRAM 不足のエラーが出たら、下を 0.6B 版に変えると軽くなる：
#   "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
MODEL_NAME = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"

# 日本語のプリセット話者（最小版はこれで固定）
LANGUAGE = "Japanese"
SPEAKER = "Ono_Anna"

# 出力先フォルダ
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

# ------------------------------------------------------------------------------

# 読み込んだモデルを覚えておく場所（最初は None）
_model = None


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
        # float16 は GPU で安定して速い
        dtype = torch.float16
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


def synthesize(text: str) -> str:
    """日本語テキストを Qwen3-TTS で読み上げ、wav ファイルのパスを返す。"""
    import soundfile as sf

    model = _get_model()

    wavs, sr = model.generate_custom_voice(
        text=text,
        language=LANGUAGE,
        speaker=SPEAKER,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_path = OUTPUT_DIR / f"qwen3_{stamp}.wav"
    sf.write(str(out_path), wavs[0], sr)
    print(f"[Qwen3] 音声を書き出しました: {out_path}")
    return str(out_path)
