"""音声の再生・停止（デスクトップアプリ用）。

sounddevice を使って wav を再生する。float / 16bit などフォーマットを問わず鳴らせる。
再生は別スレッドで非同期に行われるので、UI をふさがない。
"""

from __future__ import annotations


def load(wav_path: str):
    """wav を読み込んで (音声データ, サンプリングレート) を返す。"""
    import soundfile as sf
    data, samplerate = sf.read(wav_path, dtype="float32")
    return data, samplerate


def play_array(data, samplerate: int) -> None:
    """すでに読み込んだ音声データを最初から再生する（前の再生は止めてから）。"""
    import sounddevice as sd
    sd.stop()
    sd.play(data, samplerate)


def play(wav_path: str) -> None:
    """wav ファイルを最初から再生する（前の再生は止めてから）。"""
    data, samplerate = load(wav_path)
    play_array(data, samplerate)


def stop() -> None:
    """再生中の音声を止める。"""
    import sounddevice as sd
    sd.stop()
