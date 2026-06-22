"""Qwen3-TTS Base モデルによるボイスクローン（参照音声から生成）。

「保存した声」（.mvsvoice の reference.wav）で生成するときに使う。
クローン系 API は Base モデルでのみ動き、float32 が必須（float16 はエラー）。
公式の流れ: 参照音声 → create_voice_clone_prompt → generate_voice_clone
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .audio_utils import change_speed_keep_pitch

# Base（クローン対応）モデル
MODEL_NAME = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
DEFAULT_LANGUAGE = "Japanese"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

_model = None
_prompt_cache: dict = {}


def _get_model():
    """Base モデルを（初回だけ）読み込む。クローンは float32 必須。"""
    global _model
    if _model is not None:
        return _model
    import torch
    from qwen_tts import Qwen3TTSModel

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"[Clone] Base モデルを読み込みます（初回は時間がかかります）: {MODEL_NAME} on {device}")
    _model = Qwen3TTSModel.from_pretrained(
        MODEL_NAME, device_map=device, dtype=torch.float32, attn_implementation="sdpa",
    )
    print("[Clone] Base モデルの読み込みが終わりました。")
    return _model


def synthesize_clone(text: str, ref_wav: str, ref_text: str | None = None,
                     language: str = DEFAULT_LANGUAGE, speed: float = 1.0) -> str:
    """参照音声のクローンで text を読み上げ、wav ファイルのパスを返す。"""
    import soundfile as sf

    if not Path(ref_wav).exists():
        raise FileNotFoundError(f"参照音声が見つかりません: {ref_wav}")

    model = _get_model()
    # 参照音声→プロンプトはセッション中キャッシュ（毎回の特徴抽出を省く）
    x_vector_only = not bool(ref_text)
    key = (str(ref_wav), ref_text or "")
    prompt = _prompt_cache.get(key)
    if prompt is None:
        prompt = model.create_voice_clone_prompt(
            ref_audio=str(ref_wav),
            ref_text=(None if x_vector_only else ref_text),
            x_vector_only_mode=x_vector_only,
        )
        _prompt_cache[key] = prompt

    wavs, sr = model.generate_voice_clone(
        text=text, language=language or DEFAULT_LANGUAGE, voice_clone_prompt=prompt,
    )
    audio = change_speed_keep_pitch(wavs[0], speed)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_path = OUTPUT_DIR / f"clone_{stamp}.wav"
    sf.write(str(out_path), audio, sr)
    print(f"[Clone] 音声を書き出しました（ref={Path(ref_wav).name}, 速度={speed}）: {out_path}")
    return str(out_path)
