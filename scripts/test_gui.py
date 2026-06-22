"""デスクトップ画面が、エラーなく組み立てられて表示できるかの確認用。

実際のウィンドウを一瞬だけ開き、エンジン切替で声の一覧が入れ替わるかを確かめ、
自動で閉じる。音声生成はしない（画面の組み立て確認だけ）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: E402


def main():
    win = app.TTSApp()
    win.update()  # 一度描画

    results = []

    def check_irodori():
        win.engine_btn.set("Irodori-TTS")
        win._on_engine_change("Irodori-TTS")
        win.update()
        results.append(("irodori voices", win.voice_menu.cget("values"), win.voice_menu.get()))

    def check_qwen():
        win.engine_btn.set("Qwen3-TTS")
        win._on_engine_change("Qwen3-TTS")
        win.update()
        results.append(("qwen3 voices", win.voice_menu.cget("values"), win.voice_menu.get()))

    win.after(200, check_irodori)
    win.after(400, check_qwen)
    win.after(700, win.destroy)
    win.mainloop()

    print("GUI smoke test OK")
    for name, values, current in results:
        print(f"  {name}: 選択肢={values} / 既定={current}")


if __name__ == "__main__":
    main()
