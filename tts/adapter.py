"""共通の窓口（アダプタ）。

UI はこのファイルの synthesize() を呼ぶだけでよい。
中で「どのエンジンを使うか」を見て、対応するアダプタに振り分ける。

後でエンジンを足したいときは、
1. 新しいエンジン用の xxx_engine.py を作り、
2. 下の ENGINES に1行足す
だけでよい。UI 側は何も変えなくてよい。
"""

from __future__ import annotations

# 使えるエンジンの一覧（UI のラジオボタンにもこの名前が並ぶ）
# key   … プログラム内部で使う名前（"qwen3" / "irodori"）
# label … 画面に表示する名前
ENGINES = {
    "qwen3": "Qwen3-TTS",
    "irodori": "Irodori-TTS",
}


def synthesize(text: str, engine: str) -> str:
    """文章を音声にして、できた wav ファイルのパスを返す共通の窓口。

    引数:
        text   … 読み上げたい日本語
        engine … "qwen3" か "irodori"

    戻り値:
        作られた wav ファイルのパス（文字列）
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("読み上げる文章が空です。テキストを入力してください。")

    if engine == "qwen3":
        # 重いライブラリは、そのエンジンを使うときだけ読み込む（起動を速くするため）
        from . import qwen_engine
        return qwen_engine.synthesize(text)

    if engine == "irodori":
        from . import irodori_engine
        return irodori_engine.synthesize(text)

    raise ValueError(f"知らないエンジンです: {engine!r}（使えるのは {list(ENGINES)} ）")
