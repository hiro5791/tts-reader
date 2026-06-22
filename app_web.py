"""【旧UI／参考用】ブラウザ版（Gradio）の画面。

デスクトップ版（app.py）に作り替えたため、こちらは予備として残してある。
ブラウザ版を使いたいときだけ:
    python app_web.py
"""

from __future__ import annotations

import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

import gradio as gr

import i18n
from tts import synthesize, list_voices, default_voice, ENGINES

ENGINE_CHOICES = [(label, key) for key, label in ENGINES.items()]
DEFAULT_ENGINE = "qwen3"

# このブラウザ版は言語切り替えを持たないので、声の表示名は日本語で出す。
_WEB_LANG = "ja"


def _voice_choices(engine: str):
    """list_voices は (表示名キー, 声ID) を返すので、表示名に解決して (表示名, 声ID) にする。"""
    return [(i18n.t(_WEB_LANG, key), vid) for key, vid in list_voices(engine)]


def on_engine_change(engine: str):
    return gr.update(choices=_voice_choices(engine), value=default_voice(engine))


def on_speak(text: str, engine: str, voice: str, speed: float):
    try:
        if not text or not text.strip():
            return None, "⚠️ 文章が空です。読み上げたいテキストを入力してください。"
        wav_path = synthesize(text, engine, voice=voice, speed=speed)
        engine_label = ENGINES.get(engine, engine)
        return wav_path, f"✅ 完了しました（エンジン: {engine_label} / 速度: {speed}倍）。"
    except Exception as e:
        return None, f"❌ エラーが出ました:\n{e}"


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="読み上げアプリ") as demo:
        gr.Markdown("# 読み上げアプリ（ブラウザ版）")
        text_in = gr.Textbox(label="読み上げる文章", lines=6)
        with gr.Row():
            engine_in = gr.Radio(choices=ENGINE_CHOICES, value=DEFAULT_ENGINE, label="読み上げエンジン")
            voice_in = gr.Dropdown(choices=_voice_choices(DEFAULT_ENGINE), value=default_voice(DEFAULT_ENGINE), label="声（話者）")
        speed_in = gr.Slider(minimum=0.5, maximum=2.0, value=1.0, step=0.1, label="読み上げ速度")
        speak_btn = gr.Button("読み上げる", variant="primary")
        status = gr.Markdown("準備OK。")
        audio_out = gr.Audio(label="再生", type="filepath", autoplay=True)
        engine_in.change(fn=on_engine_change, inputs=engine_in, outputs=voice_in)
        speak_btn.click(fn=on_speak, inputs=[text_in, engine_in, voice_in, speed_in], outputs=[audio_out, status])
    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="127.0.0.1", server_port=7860, inbrowser=True)
