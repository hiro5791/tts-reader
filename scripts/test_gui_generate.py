"""ボタン操作と同じ流れ（別スレッド生成→キュー受け取り→自動再生）を通しで確認する。

実際に「読み上げる」を押したのと同じ _on_speak を呼び、
生成が別スレッドで走っている間も画面が固まらず（mainloop が回り続け）、
完了して current_wav がセットされることを確かめる。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: E402


def main():
    win = app.TTSApp()
    win.engine_btn.set("Qwen3-TTS")
    win._on_engine_change("Qwen3-TTS")
    win.text_box.delete("1.0", "end")
    win.text_box.insert("1.0", "デスクトップ版の通しテストです。")

    state = {"start": time.time(), "frames": 0}

    def tick():
        state["frames"] += 1
        # 生成完了（busyが解けてwavができた）か、3分でタイムアウト
        if (not win._busy and win.current_wav) or (time.time() - state["start"] > 180):
            elapsed = round(time.time() - state["start"], 1)
            print(f"busy={win._busy}  current_wav={win.current_wav}")
            print(f"status={win.status_label.cget('text')!r}")
            print(f"mainloopは生成中も回り続けた（tick回数={state['frames']}, {elapsed}秒）")
            win.after(1200, win.destroy)  # 自動再生を少しだけ鳴らして終了
            return
        win.after(200, tick)

    win.after(300, win._on_speak)  # ボタンを押したのと同じ
    win.after(600, tick)
    win.mainloop()
    print("通しテスト完了")


if __name__ == "__main__":
    main()
