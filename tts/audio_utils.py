"""音声まわりの小さな共通処理。"""

from __future__ import annotations

import numpy as np


def apply_dsp(audio, sr: int, speed: float = 1.0, pitch: float = 0.0,
              volume: float = 1.0):
    """生成された音声に「ピッチ→速度→音量」の順で後処理をかける（共通層）。

    両エンジンとも音量/ピッチのつまみを持たないため、生成後の音声を加工して実現する。
    予測可能で、どちらのエンジンでも同じように効く。

    引数:
        audio  … 音声データ（numpy 配列。モノラル想定。ステレオなら平均してモノラル化）
        sr     … サンプリングレート
        speed  … 1.0 が等倍（高さ保持で速さを変える＝タイムストレッチ）
        pitch  … 0 が変化なし。半音単位（長さ保持でピッチシフト）
        volume … 1.0 が等倍（最後にゲイン）。最後に [-1,1] にクリップして歪み防止

    戻り値:
        後処理した音声データ（numpy float32）
    """
    y = np.asarray(audio, dtype=np.float32)
    if y.ndim > 1:               # 念のためモノラル化
        y = y.mean(axis=1)

    need_pitch = pitch is not None and abs(float(pitch)) > 1e-6
    need_speed = speed is not None and abs(float(speed) - 1.0) > 1e-3
    need_vol = volume is not None and abs(float(volume) - 1.0) > 1e-3
    if not (need_pitch or need_speed or need_vol):
        return y   # 何もしないならそのまま（無駄な劣化を避ける）

    if need_pitch or need_speed:
        import librosa
        # ① ピッチ変更（長さは変えず、高さだけ。半音単位）
        if need_pitch:
            y = librosa.effects.pitch_shift(y, sr=sr, n_steps=float(pitch))
        # ② 速度変更（高さは変えず、速さだけ。rate>1 で速く＝短く）
        if need_speed:
            y = librosa.effects.time_stretch(y, rate=float(speed))

    # ③ 音量（線形ゲイン）→ 最後に必ずクリップして歪みを防ぐ
    if need_vol:
        y = y * float(volume)
    y = np.clip(y, -1.0, 1.0)
    return y.astype(np.float32)


def concat_with_silence(chunks, sr: int, gap_sec: float = 0.25):
    """複数の音声チャンクを、間に無音を挟んで1本に連結する（Irodori 分割用）。

    引数:
        chunks  … 音声データ（numpy 配列）のリスト
        sr      … サンプリングレート（全チャンクで同一前提）
        gap_sec … チャンク間に入れる無音の長さ（秒）
    """
    parts = []
    silence = np.zeros(int(sr * max(0.0, gap_sec)), dtype=np.float32)
    for i, c in enumerate(chunks):
        y = np.asarray(c, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)
        if i > 0 and silence.size:
            parts.append(silence)
        parts.append(y)
    if not parts:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(parts).astype(np.float32)


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
