"""共通の窓口（アダプタ）。

UI はこのファイルの関数を呼ぶだけでよい。
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


def _engine_module(engine: str):
    """エンジン名から、対応するアダプタ（モジュール）を返す。

    重いライブラリは、そのエンジンを使うときだけ読み込む（起動を速くするため）。
    """
    if engine == "qwen3":
        from . import qwen_engine
        return qwen_engine
    if engine == "irodori":
        from . import irodori_engine
        return irodori_engine
    raise ValueError(f"知らないエンジンです: {engine!r}（使えるのは {list(ENGINES)} ）")


def list_voices(engine: str) -> list[tuple[str, str]]:
    """そのエンジンで選べる声の一覧を返す。

    戻り値は (表示名の i18n キー, 内部の声ID) の組のリスト。
    表示名は i18n.py の辞書に持たせ、UI 側で表示言語に合わせて解決する。
    """
    return _engine_module(engine).list_voices()


def default_voice(engine: str) -> str:
    """そのエンジンの初期選択にする声ID。"""
    return _engine_module(engine).DEFAULT_VOICE


def list_languages(engine: str) -> list[tuple[str, str]]:
    """そのエンジンで選べる音声の言語の一覧を返す。

    戻り値は (表示名の i18n キー, エンジンに渡す言語名) の組のリスト。
    表示名は i18n.py の辞書に持たせ、UI 側で表示言語に合わせて解決する。
    """
    return _engine_module(engine).list_languages()


def default_language(engine: str) -> str:
    """そのエンジンの初期選択にする言語名。"""
    return _engine_module(engine).DEFAULT_LANGUAGE


def synthesize(text: str, engine: str, voice: str | None = None, speed: float = 1.0,
               language: str | None = None) -> str:
    """文章を音声にして、できた wav ファイルのパスを返す共通の窓口。

    引数:
        text     … 読み上げたい文章
        engine   … "qwen3" か "irodori"
        voice    … 声ID（None ならそのエンジンのデフォルト声）
        speed    … 読み上げ速度。1.0 が等倍、2.0 で2倍速、0.5 で半分の速さ
        language … 何語として読み上げるか（None ならそのエンジンのデフォルト言語）

    戻り値:
        作られた wav ファイルのパス（文字列）
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("読み上げる文章が空です。テキストを入力してください。")

    module = _engine_module(engine)
    if voice is None:
        voice = module.DEFAULT_VOICE
    if language is None:
        language = module.DEFAULT_LANGUAGE
    return module.synthesize(text, voice=voice, speed=float(speed), language=language)


def synthesize_clone(engine: str, text: str, ref_wav: str, ref_text: str | None = None,
                     language: str | None = None, speed: float = 1.0) -> str:
    """参照音声（ref_wav）のクローンで生成する共通の窓口（「保存した声」用）。

    engine に応じて各エンジンのクローン経路に振り分ける:
      - qwen3   … Base モデルの generate_voice_clone（別チェックポイント）
      - irodori … infer.py --ref-wav（日本語のみ）
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("読み上げる文章が空です。テキストを入力してください。")

    if engine == "qwen3":
        from . import clone_engine
        if language is None:
            language = clone_engine.DEFAULT_LANGUAGE
        return clone_engine.synthesize_clone(
            text, ref_wav=ref_wav, ref_text=ref_text, language=language, speed=float(speed),
        )
    if engine == "irodori":
        from . import irodori_engine
        if language is None:
            language = irodori_engine.DEFAULT_LANGUAGE
        return irodori_engine.synthesize_clone(
            text, ref_wav=ref_wav, ref_text=ref_text, language=language, speed=float(speed),
        )
    raise ValueError(f"知らないエンジンです: {engine!r}")
