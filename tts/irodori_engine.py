"""Irodori-TTS アダプタ。

Irodori は Python から直接呼ぶ部品（ライブラリ）が無く、
GitHub のリポジトリにある infer.py をコマンドとして実行して使う。
そこで、このアダプタは「infer.py を裏で実行して、出来た wav を返す」だけにする。

事前準備（setup_irodori で自動化する）:
  - vendor/Irodori-TTS にリポジトリを clone 済み
  - その中で `uv sync` 済み（必要なライブラリが入っている）
"""

from __future__ import annotations

import datetime as _dt
import re
import shutil
import site
import subprocess
import sys
from pathlib import Path

# 長文分割の設定（実機で崩れ始める所を見て微調整してよい）
_CHUNK_MIN_CHARS = 100      # 累計がこれ以上になったら文末で1チャンク確定
_LONG_SENTENCE_CHARS = 140  # 1文だけでこれを超えたら「、」で更に割る保険
_CHUNK_GAP_SEC = 0.25       # チャンク間に挟む無音の長さ


def _find_uv() -> str:
    """uv コマンドの場所を探す。PATH に無くても見つけられるようにする。"""
    found = shutil.which("uv")
    if found:
        return found
    # pip install --user で入れた場合の場所も探す
    candidates = [
        Path(site.getuserbase()) / "Scripts" / "uv.exe",   # Windows --user
        Path(site.getuserbase()) / "bin" / "uv",           # Linux/mac --user
        Path(sys.prefix) / "Scripts" / "uv.exe",           # venv 内
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    # 最後の手段：python -m uv で動かす
    return ""

# ---- 固定設定 ----------------------------------------------------------------

# Irodori のモデル（HuggingFace 上の名前）
# - 基本（参照音声タイプ）のモデル
HF_CHECKPOINT = "Aratako/Irodori-TTS-500M-v3"
# - caption（声の説明文）で声を作る VoiceDesign タイプのモデル
HF_CHECKPOINT_VOICEDESIGN = "Aratako/Irodori-TTS-600M-v3-VoiceDesign"

# clone してきた Irodori-TTS リポジトリの場所
IRODORI_DIR = Path(__file__).resolve().parent.parent / "vendor" / "Irodori-TTS"

# 用意した参照音声（声プリセット）の置き場所
VOICES_DIR = Path(__file__).resolve().parent.parent / "voices" / "irodori"

# 出力先フォルダ
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

# ---- 選べる声 ----------------------------------------------------------------
# 声の定義はこの VOICES 辞書 1か所にまとめる（編集・追加はここだけでよい）。
# 各声は次のどれかの形にする：
#   {"label_key": 表示名キー, "ref": None}        … 基本Irodori・参照なし（--no-ref）
#   {"label_key": 表示名キー, "ref": "xxx.wav"}   … 基本Irodori・voices/irodori/xxx.wav を参照音声に使う
#   {"label_key": 表示名キー, "caption": "説明文"} … VoiceDesign タイプ。説明文どおりの声を作る
#
# label_key は i18n.py の辞書のキー。表示名は表示言語の切り替えに追従する。
# caption を持つ声は、自動的に VoiceDesign モデル（HF_CHECKPOINT_VOICEDESIGN）に
# 切り替え、infer.py に  --caption "説明文" --no-ref  を渡して生成する。
# caption の文面を直したいときも、この辞書を書き換えるだけでよい。
DEFAULT_VOICE = "default"
VOICES = {
    # デフォルト（指定なし）：基本Irodori・参照なし
    "default": {
        "label_key": "voice_irodori_default",
        "ref": None,
    },
    # ↓ caption（声の説明文）で作る3種類の声
    "calm_female": {
        "label_key": "voice_irodori_calm_female",
        "caption": "落ち着いた女性の声で、近い距離感でやわらかく自然に読み上げてください。",
    },
    "bright_male": {
        "label_key": "voice_irodori_bright_male",
        "caption": "明るくはきはきした男性の声で、少し速めに元気よく読み上げてください。",
    },
    "gentle_neutral": {
        "label_key": "voice_irodori_gentle_neutral",
        "caption": "穏やかで中性的な声で、ゆっくり落ち着いて丁寧に読み上げてください。",
    },
}

# ---- 音声の言語 --------------------------------------------------------------
# Irodori は日本語のみ対応。UI 側ではこの1件だけになり、選択は日本語に固定される。
# (表示名の i18n キー, 言語名)
LANGUAGES = [("audiolang_japanese", "Japanese")]
DEFAULT_LANGUAGE = "Japanese"

# ------------------------------------------------------------------------------


def list_voices() -> list[tuple[str, str]]:
    """選べる声の一覧 (表示名の i18n キー, 声ID) を返す。"""
    return [(cfg["label_key"], vid) for vid, cfg in VOICES.items()]


def list_languages() -> list[tuple[str, str]]:
    """選べる音声の言語の一覧 (表示名の i18n キー, 言語名) を返す。Irodori は日本語のみ。"""
    return list(LANGUAGES)


class GenerationCancelled(Exception):
    """生成がユーザーにより停止されたことを表す（アプリ側で結果は無視される）。"""


def _run_infer(checkpoint: str, text: str, voice_args: list[str], speed: float,
               tag: str = "", cancel_event=None) -> str:
    """infer.py を実行して wav を書き出し、そのパスを返す（共通処理）。

    cancel_event が途中で set されたら、サブプロセスを kill して GenerationCancelled。
    """
    if not IRODORI_DIR.exists():
        raise FileNotFoundError(
            "Irodori-TTS がまだ用意されていません。\n"
            f"（{IRODORI_DIR} が見つかりません）\n"
            "先に scripts/setup_irodori を実行して、Irodori を準備してください。"
        )
    if cancel_event is not None and cancel_event.is_set():
        raise GenerationCancelled()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_path = OUTPUT_DIR / f"irodori_{stamp}.wav"

    # 速度 → duration-scale（>1 で長く=遅く、<1 で短く=速く）。速度の逆数を渡す。
    speed = max(0.1, float(speed))
    duration_scale = round(1.0 / speed, 3)

    uv = _find_uv()
    uv_prefix = [uv] if uv else [sys.executable, "-m", "uv"]
    cmd = [
        *uv_prefix, "run", "--no-sync", "python", "infer.py",
        "--hf-checkpoint", checkpoint,
        "--text", text,
        *voice_args,
        "--duration-scale", str(duration_scale),
        "--output-wav", str(out_path),
    ]
    print(f"[Irodori] 実行（{tag}, モデル={checkpoint}, 速度={speed}, "
          f"duration-scale={duration_scale}） ...（初回はモデル読み込みで時間がかかります）")

    # Popen で起動し、停止フラグを見ながら待つ（停止されたら kill する）
    proc = subprocess.Popen(
        cmd, cwd=str(IRODORI_DIR),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=0.3)
            break
        except subprocess.TimeoutExpired:
            if cancel_event is not None and cancel_event.is_set():
                proc.kill()
                try:
                    proc.communicate(timeout=5)
                except Exception:
                    pass
                raise GenerationCancelled()

    if proc.returncode != 0 or not out_path.exists():
        if cancel_event is not None and cancel_event.is_set():
            raise GenerationCancelled()
        raise RuntimeError(
            "Irodori-TTS の実行に失敗しました。\n"
            f"--- 標準出力 ---\n{(stdout or '')[-2000:]}\n"
            f"--- エラー出力 ---\n{(stderr or '')[-2000:]}"
        )
    print(f"[Irodori] 音声を書き出しました（{tag}, 速度={speed}）: {out_path}")
    return str(out_path)


# ---- 長文分割（Irodori 専用。約30秒の生成上限を超えると崩れるため必須）-----
def _split_sentences(text: str) -> list[str]:
    """「。」「！」「？」（と改行）で文に区切る。区切り文字は文末に残す。"""
    parts = re.split(r"(?<=[。！？\n])", text)
    return [p for p in (s.strip() for s in parts) if p]


def _split_by_comma(s: str) -> list[str]:
    """長すぎる1文を「、」（と「,」）で更に分割する保険。"""
    parts = re.split(r"(?<=[、,])", s)
    return [p for p in (x.strip() for x in parts) if p] or [s]


def split_text(text: str) -> list[str]:
    """長文を、文末を尊重しつつ約100文字ごとのチャンクに分ける。

    1. 「。！？」で文に区切る。
    2. 文を順に足し、累計が 100 文字以上になったら、その文末でチャンク確定。
    3. 保険：1文だけで 140 文字超なら「、」で更に分割してから足す。
    """
    chunks: list[str] = []
    cur = ""
    for s in _split_sentences(text):
        pieces = _split_by_comma(s) if len(s) > _LONG_SENTENCE_CHARS else [s]
        for piece in pieces:
            cur += piece
            if len(cur) >= _CHUNK_MIN_CHARS:
                chunks.append(cur)
                cur = ""
    if cur:
        chunks.append(cur)
    return chunks or [text.strip()]


def _generate_chunked(checkpoint: str, text: str, voice_args: list[str], tag: str,
                      progress_callback=None, cancel_event=None) -> str:
    """テキストをチャンクに分けて順に生成し、無音を挟んで1本に連結する。

    速度・音量・ピッチは共通層で後処理するため、ここは各チャンクを等倍（生）で作る。
    progress_callback(i, n) を各チャンク完了時に呼ぶ（UI の「生成中…（i/n）」用）。
    cancel_event が set されたら、その時点で停止する（次チャンクへ進まない）。
    """
    import soundfile as sf
    from .audio_utils import concat_with_silence

    chunks = split_text(text)
    n = len(chunks)

    # 1チャンクならそのまま（連結の手間を省く）
    if n == 1:
        path = _run_infer(checkpoint, chunks[0], voice_args, 1.0, tag=f"{tag} 1/1",
                          cancel_event=cancel_event)
        if progress_callback:
            try:
                progress_callback(1, 1)
            except Exception:
                pass
        return path

    audios, sr = [], None
    for i, ch in enumerate(chunks):
        if cancel_event is not None and cancel_event.is_set():
            raise GenerationCancelled()
        path = _run_infer(checkpoint, ch, voice_args, 1.0, tag=f"{tag} {i + 1}/{n}",
                          cancel_event=cancel_event)
        data, sr = sf.read(path, dtype="float32")
        audios.append(data)
        if progress_callback:
            try:
                progress_callback(i + 1, n)
            except Exception:
                pass

    merged = concat_with_silence(audios, sr, gap_sec=_CHUNK_GAP_SEC)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_path = OUTPUT_DIR / f"irodori_merged_{stamp}.wav"
    sf.write(str(out_path), merged, sr)
    print(f"[Irodori] {n} チャンクを連結しました: {out_path}")
    return str(out_path)


def synthesize(text: str, voice: str = DEFAULT_VOICE,
               language: str = DEFAULT_LANGUAGE, progress_callback=None,
               cancel_event=None) -> str:
    """日本語テキストを Irodori-TTS で読み上げ、生の wav ファイルのパスを返す。

    長文は約100文字ごとに分割して順に生成し、連結する（30秒上限対策）。
    速度・音量・ピッチは共通層（adapter）の後処理で適用する。
    """
    if voice not in VOICES:
        voice = DEFAULT_VOICE
    cfg = VOICES[voice]

    # 声の種類に応じて、使うモデルと引数を切り替える（チャンク間で共通）。
    caption = cfg.get("caption")
    if caption:
        checkpoint = HF_CHECKPOINT_VOICEDESIGN
        voice_args = ["--caption", caption, "--no-ref"]
    else:
        checkpoint = HF_CHECKPOINT
        ref = cfg.get("ref")
        if ref is None:
            voice_args = ["--no-ref"]
        else:
            ref_path = VOICES_DIR / ref
            if not ref_path.exists():
                raise FileNotFoundError(f"参照音声が見つかりません: {ref_path}")
            voice_args = ["--ref-wav", str(ref_path)]

    return _generate_chunked(checkpoint, text, voice_args, tag=f"声={voice}",
                             progress_callback=progress_callback, cancel_event=cancel_event)


def synthesize_clone(text: str, ref_wav: str, ref_text: str | None = None,
                     language: str = DEFAULT_LANGUAGE, progress_callback=None,
                     cancel_event=None) -> str:
    """参照音声（ref_wav）のクローンで読み上げる（長文分割あり）。Irodori は日本語のみ。

    infer.py に --ref-wav を渡して基本Irodoriモデルでクローン生成する。
    速度・音量・ピッチは共通層で後処理する。
    """
    if not Path(ref_wav).exists():
        raise FileNotFoundError(f"参照音声が見つかりません: {ref_wav}")
    voice_args = ["--ref-wav", str(ref_wav)]
    return _generate_chunked(HF_CHECKPOINT, text, voice_args, tag="クローン(ref)",
                             progress_callback=progress_callback, cancel_event=cancel_event)
