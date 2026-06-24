"""実行デバイス（GPU/CPU）の選択。

VRAM が足りない、または NVIDIA GPU が無いマシンでもクラッシュせず動くよう、
「必要な空き VRAM を満たせば cuda、無理なら cpu」を選ぶ。CPU は遅いが確実に動く。

※ adapter 側で「使わないモデルを解放」してから各エンジンがモデルを読むため、
   ここで見る空き VRAM は、ほぼそのモデル専用に使える量になる。
"""

from __future__ import annotations


def cuda_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def free_vram_gb() -> float:
    """現在の空き VRAM（GB）。GPU が無ければ 0。"""
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0
        free, _total = torch.cuda.mem_get_info()
        return float(free) / (1024 ** 3)
    except Exception:
        return 0.0


def pick_device(required_gb: float) -> str:
    """必要 VRAM(GB) を満たせば 'cuda:0'、満たさなければ 'cpu' を返す。

    required_gb は「そのモデルを読み込んで生成するのに必要な VRAM の目安」。
    余裕（活性化・KVキャッシュ等）を含めて少し大きめに渡すこと。
    """
    if cuda_available():
        free = free_vram_gb()
        if free >= required_gb:
            return "cuda:0"
        print(f"[device] 空きVRAM {free:.1f}GB < 必要 {required_gb:.1f}GB のため CPU で実行します（遅くなります）。")
    return "cpu"
