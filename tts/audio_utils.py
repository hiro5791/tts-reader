"""音声まわりの小さな共通処理。"""

from __future__ import annotations

import numpy as np


def change_speed_keep_pitch(wav, speed: float):
    """音の高さ（ピッチ）を変えずに、再生速度だけを変える。

    速度パラメータを持たないエンジン（Qwen3 など）の速度調整に使う。
    単純な再生レート変更だと声が高く/低くなってしまうので、
    librosa のタイムストレッチ（ピッチ保持）を使う。

    引数:
        wav   … 音声データ（numpy 配列、モノラル想定）
        speed … 1.0 が等倍。2.0 で2倍速（短く）、0.5 で半分の速さ（長く）

    戻り値:
        速度を変えた音声データ（numpy float32 配列）
    """
    if speed is None or abs(speed - 1.0) < 1e-3:
        return wav  # 等倍ならそのまま

    import librosa

    y = np.asarray(wav, dtype=np.float32)
    # librosa の rate は「>1 で速く（短く）」なので speed をそのまま渡せばよい
    stretched = librosa.effects.time_stretch(y, rate=float(speed))
    return stretched.astype(np.float32)
