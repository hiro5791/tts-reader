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


# モデルを保持し続ける Qwen 系エンジン（それぞれ別チェックポイント＝VRAMを大きく使う）
_MODEL_HOLDERS = ("tts.qwen_engine", "tts.qwen_design_engine", "tts.clone_engine")


def _free_models(keep: str | None = None) -> None:
    """読み込み済みモデルをメモリ（VRAM/RAM）から解放する。

    各エンジンは一度読み込んだモデルを保持し続けるため、プリセット→声を作る→
    クローン…と切り替えると VRAM が累積し、8GB 級GPUでは枯渇してクラッシュする。
    そこで「新しいモデルを読む前に、今使わないモデルを解放」して、同時に載るのを
    実質1モデルに保つ。keep に渡したモジュールだけは残す（同じ操作の連続を速くする）。
    """
    import sys
    import gc

    for name in _MODEL_HOLDERS:
        if name == keep:
            continue
        mod = sys.modules.get(name)
        if mod is None:
            continue
        if getattr(mod, "_model", None) is not None:
            mod._model = None
        pc = getattr(mod, "_prompt_cache", None)
        if isinstance(pc, dict):
            pc.clear()
    # Irodori（同一プロセス実行）のランタイムキャッシュも解放（あれば）
    try:
        irt = sys.modules.get("irodori_tts.inference_runtime")
        if irt is not None and hasattr(irt, "clear_cached_runtime"):
            irt.clear_cached_runtime()
    except Exception:
        pass
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


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
               volume: float = 1.0, pitch: float = 0.0, mode: str = "preset",
               voice_description: str | None = None, style: str | None = None,
               language: str | None = None,
               progress_callback=None, cancel_event=None) -> str:
    """文章を音声にして、できた wav ファイルのパスを返す共通の窓口。

    引数:
        text     … 読み上げたい文章
        engine   … "qwen3" か "irodori"
        voice    … 声ID（None ならそのエンジンのデフォルト声）。mode="preset" で使う。
        speed/volume/pitch … 共通後処理で適用（1.0/1.0/0）
        mode     … "preset"（プリセット声）か "voice_design"（説明文で声を作る）
        voice_description … 声を作るときの説明文（Qwen=instruct / Irodori=caption）
        style    … 喋り方（感情・スタイル）。Qwen のプリセットで instruct として使う。
                   Irodori は独立指定不可のため未使用。
        language … 何語として読み上げるか（None ならそのエンジンのデフォルト言語）
        progress_callback … 分割生成の進捗通知 callback(i, n)（Irodori 長文時）

    どの引数を使うかは engine と mode の組み合わせで、ここ（共通層）で振り分ける。
    速度・音量・ピッチは生成後の共通後処理で適用し、各エンジンは生の音声を返す。
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("読み上げる文章が空です。テキストを入力してください。")

    module = _engine_module(engine)
    if language is None:
        language = module.DEFAULT_LANGUAGE

    if mode == "voice_design":
        # 声を作る：Qwen=VoiceDesignモデル / Irodori=VoiceDesign版モデル(caption)
        if engine == "qwen3":
            from . import qwen_design_engine
            _free_models(keep="tts.qwen_design_engine")  # 他モデルを解放してVRAM枯渇を防ぐ
            raw = qwen_design_engine.synthesize_design(
                text, instruct=(voice_description or ""), language=language,
                progress_callback=progress_callback, cancel_event=cancel_event)
        elif engine == "irodori":
            _free_models(keep=None)   # Qwen系を全解放（Irodoriはランタイムを都度作る）
            raw = module.synthesize_design(
                text, caption=(voice_description or ""), language=language,
                progress_callback=progress_callback, cancel_event=cancel_event)
        else:
            raise ValueError(f"知らないエンジンです: {engine!r}")
    else:
        # プリセット声。Qwen は style を instruct として渡せる（Irodori は無視）。
        if voice is None:
            voice = module.DEFAULT_VOICE
        if engine == "qwen3":
            _free_models(keep="tts.qwen_engine")
            raw = module.synthesize(
                text, voice=voice, language=language, style=style,
                progress_callback=progress_callback, cancel_event=cancel_event)
        else:
            _free_models(keep=None)
            raw = module.synthesize(
                text, voice=voice, language=language,
                progress_callback=progress_callback, cancel_event=cancel_event)
    return _postprocess(raw, speed, pitch, volume)


def synthesize_clone(engine: str, text: str, ref_wav: str, ref_text: str | None = None,
                     language: str | None = None, speed: float = 1.0,
                     volume: float = 1.0, pitch: float = 0.0, style: str | None = None,
                     progress_callback=None, cancel_event=None) -> str:
    """参照音声（ref_wav）のクローンで生成する共通の窓口（「保存した声」用）。

    engine に応じて各エンジンのクローン経路に振り分ける:
      - qwen3   … Base モデルの generate_voice_clone（別チェックポイント）
      - irodori … infer.py --ref-wav（日本語のみ）
    速度・音量・ピッチは共通後処理で適用する。
    style（喋り方）… UI から渡ってくるが、現在のクローンAPI（generate_voice_clone /
      Irodori の --ref-wav）は instruct を受け取らないため、ここでは適用されない
      （仕様どおり「クローンでは感情の効きが弱い／limited」）。
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("読み上げる文章が空です。テキストを入力してください。")

    if engine == "qwen3":
        from . import clone_engine
        if language is None:
            language = clone_engine.DEFAULT_LANGUAGE
        _free_models(keep="tts.clone_engine")  # 他モデルを解放（Baseはfp32で重いので特に重要）
        raw = clone_engine.synthesize_clone(
            text, ref_wav=ref_wav, ref_text=ref_text, language=language,
            progress_callback=progress_callback, cancel_event=cancel_event)
    elif engine == "irodori":
        from . import irodori_engine
        if language is None:
            language = irodori_engine.DEFAULT_LANGUAGE
        _free_models(keep=None)
        raw = irodori_engine.synthesize_clone(
            text, ref_wav=ref_wav, ref_text=ref_text, language=language,
            progress_callback=progress_callback, cancel_event=cancel_event)
    else:
        raise ValueError(f"知らないエンジンです: {engine!r}")
    return _postprocess(raw, speed, pitch, volume)
