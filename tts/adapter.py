"""共通の窓口（アダプタ）。

UI はこのファイルの関数を呼ぶだけでよい。
中で「どのエンジンを使うか」を見て、対応するアダプタに振り分ける。

後でエンジンを足したいときは、
1. 新しいエンジン用の xxx_engine.py を作り、
2. 下の ENGINES に1行足す
だけでよい。UI 側は何も変えなくてよい。
"""

from __future__ import annotations

from pathlib import Path

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


def _postprocess(raw_wav: str, speed: float, pitch: float, volume: float) -> str:
    """エンジンが返した生の音声に、共通の後処理（ピッチ→速度→音量）をかける。

    速度=1・ピッチ=0・音量=1 のときは何もせず素通し（無駄な読み書き・劣化を避ける）。
    後処理したときは、別ファイルに書き出してそのパスを返す。
    """
    from . import audio_utils
    need = (abs(float(speed) - 1.0) > 1e-3 or abs(float(pitch)) > 1e-6
            or abs(float(volume) - 1.0) > 1e-3)
    if not need:
        return raw_wav

    import soundfile as sf
    data, sr = sf.read(raw_wav, dtype="float32")
    out = audio_utils.apply_dsp(data, sr, speed=speed, pitch=pitch, volume=volume)
    p = Path(raw_wav)
    out_path = p.with_name(p.stem + "_dsp" + p.suffix)
    sf.write(str(out_path), out, sr)
    return str(out_path)


def synthesize(text: str, engine: str, voice: str | None = None, speed: float = 1.0,
               volume: float = 1.0, pitch: float = 0.0, language: str | None = None,
               progress_callback=None, cancel_event=None) -> str:
    """文章を音声にして、できた wav ファイルのパスを返す共通の窓口。

    引数:
        text     … 読み上げたい文章
        engine   … "qwen3" か "irodori"
        voice    … 声ID（None ならそのエンジンのデフォルト声）
        speed    … 読み上げ速度。1.0 が等倍（共通後処理で適用）
        volume   … 音量。1.0 が等倍（共通後処理で適用）
        pitch    … ピッチ。0 が変化なし。半音単位（共通後処理で適用）
        language … 何語として読み上げるか（None ならそのエンジンのデフォルト言語）
        progress_callback … 分割生成の進捗通知 callback(i, n)（Irodori 長文時）

    戻り値:
        作られた wav ファイルのパス（文字列）

    速度・音量・ピッチは「エンジンに頼らず」生成後の共通後処理で適用する。
    各エンジンは「生の音声を返す」ことだけに集中する（分割は Irodori 内に閉じる）。
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("読み上げる文章が空です。テキストを入力してください。")

    module = _engine_module(engine)
    if voice is None:
        voice = module.DEFAULT_VOICE
    if language is None:
        language = module.DEFAULT_LANGUAGE
    raw = module.synthesize(text, voice=voice, language=language,
                            progress_callback=progress_callback, cancel_event=cancel_event)
    return _postprocess(raw, speed, pitch, volume)


def synthesize_clone(engine: str, text: str, ref_wav: str, ref_text: str | None = None,
                     language: str | None = None, speed: float = 1.0,
                     volume: float = 1.0, pitch: float = 0.0,
                     progress_callback=None, cancel_event=None) -> str:
    """参照音声（ref_wav）のクローンで生成する共通の窓口（「保存した声」用）。

    engine に応じて各エンジンのクローン経路に振り分ける:
      - qwen3   … Base モデルの generate_voice_clone（別チェックポイント）
      - irodori … infer.py --ref-wav（日本語のみ）
    速度・音量・ピッチは共通後処理で適用する。
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("読み上げる文章が空です。テキストを入力してください。")

    if engine == "qwen3":
        from . import clone_engine
        if language is None:
            language = clone_engine.DEFAULT_LANGUAGE
        raw = clone_engine.synthesize_clone(
            text, ref_wav=ref_wav, ref_text=ref_text, language=language,
            progress_callback=progress_callback, cancel_event=cancel_event)
    elif engine == "irodori":
        from . import irodori_engine
        if language is None:
            language = irodori_engine.DEFAULT_LANGUAGE
        raw = irodori_engine.synthesize_clone(
            text, ref_wav=ref_wav, ref_text=ref_text, language=language,
            progress_callback=progress_callback, cancel_event=cancel_event)
    else:
        raise ValueError(f"知らないエンジンです: {engine!r}")
    return _postprocess(raw, speed, pitch, volume)
