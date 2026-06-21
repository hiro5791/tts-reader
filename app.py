"""読み上げアプリ（最小版）の画面。

ブラウザで動く、シンプルな画面を作る。
  1. テキスト入力欄（複数行）
  2. エンジン選択（Qwen3 / Irodori）
  3. 「読み上げる」ボタン
  4. 音声プレイヤー（再生バー）
  5. 処理中／結果の表示

起動方法（PowerShell）:
    python app.py
表示された http://127.0.0.1:7860 をブラウザで開く。
"""

from __future__ import annotations

import gradio as gr

from tts import synthesize, ENGINES

# ラジオボタンに出す選択肢。 (画面表示名, 内部の名前) の組にする。
ENGINE_CHOICES = [(label, key) for key, label in ENGINES.items()]


def on_speak(text: str, engine: str):
    """「読み上げる」ボタンが押されたときの処理。

    戻り値は (音声プレイヤーに渡すwavパス, 状態メッセージ) の2つ。
    """
    try:
        if not text or not text.strip():
            return None, "⚠️ 文章が空です。読み上げたいテキストを入力してください。"

        wav_path = synthesize(text, engine)
        label = ENGINES.get(engine, engine)
        return wav_path, f"✅ 完了しました（エンジン: {label}）。下のプレイヤーで再生できます。"

    except Exception as e:  # エラーは画面にそのまま日本語で見せる
        return None, f"❌ エラーが出ました:\n{e}"


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="読み上げアプリ（最小版）") as demo:
        gr.Markdown(
            "# 読み上げアプリ（最小版）\n"
            "文章を貼り付けて、エンジンを選び、「読み上げる」を押してください。\n"
            "**初回はモデルの読み込みで1〜数分かかります**（2回目以降は速くなります）。"
        )

        text_in = gr.Textbox(
            label="読み上げる文章",
            placeholder="ここに日本語の文章を貼り付けてください。",
            lines=6,
        )
        engine_in = gr.Radio(
            choices=ENGINE_CHOICES,
            value="qwen3",
            label="読み上げエンジン",
            info="Qwen3 と Irodori を切り替えて聞き比べられます。",
        )
        speak_btn = gr.Button("読み上げる", variant="primary")

        status = gr.Markdown("準備OK。文章を入れて「読み上げる」を押してください。")
        audio_out = gr.Audio(label="再生", type="filepath", autoplay=True)

        speak_btn.click(
            fn=on_speak,
            inputs=[text_in, engine_in],
            outputs=[audio_out, status],
        )

    return demo


if __name__ == "__main__":
    app = build_ui()
    # ローカルPCのブラウザで開く
    app.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True)
