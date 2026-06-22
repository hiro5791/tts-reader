"""Qwen3-TTS VoiceDesign（声を作る）。

参照音声なしで、自然言語の説明文（instruct）から声を作る。
generate_voice_design は専用モデル（tts_model_type=="voice_design"）が必要で、
VoiceDesign は 1.7B のみ対応（0.6B は非対応）。CustomVoice/Base とは別モデル。

注意（モデルカードの実情）:
  - 話者を固定する仕組みが無いため、同じ説明文でも生成ごとに声が微妙にブレる。
    気に入った声は「保存した声」に取り込んで使い回す運用が有効。
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

MODEL_NAME = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
DEFAULT_LANGUAGE = "Japanese"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

_model = None


def _get_model():
    """VoiceDesign モデルを（初回だけ）読み込む。"""
    global _model
    if _model is not None:
        return _model
    import torch
    from qwen_tts import Qwen3TTSModel

    if torch.cuda.is_available():
        device, dtype = "cuda:0", torch.float16
    else:
        device, dtype = "cpu", torch.float32
    print(f"[VoiceDesign] モデルを読み込みます（初回は時間がかかります）: {MODEL_NAME} on {device}")
    _model = Qwen3TTSModel.from_pretrained(
        MODEL_NAME, device_map=device, dtype=dtype, attn_implementation="sdpa",
    )
    print("[VoiceDesign] モデルの読み込みが終わりました。")
    return _model


def synthesize_design(text: str, instruct: str = "",
                      language: str = DEFAULT_LANGUAGE,
                      progress_callback=None, cancel_event=None) -> str:
    """説明文（instruct）から声を作って text を読み上げ、生の wav パスを返す。

    速度・音量・ピッチは共通層（adapter）の後処理で適用する。
    """
    import soundfile as sf

    model = _get_model()
    wavs, sr = model.generate_voice_design(
        text=text,
        instruct=(instruct or ""),   # 空文字は「指定なし」扱い
        language=language or DEFAULT_LANGUAGE,
    )
    audio = wavs[0]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_path = OUTPUT_DIR / f"qwen_design_{stamp}.wav"
    sf.write(str(out_path), audio, sr)
    print(f"[VoiceDesign] 音声を書き出しました（説明={instruct!r}, 言語={language}）: {out_path}")
    return str(out_path)
