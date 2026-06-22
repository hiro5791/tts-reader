"""ウィンドウの位置保存・画面外補正・タイトル・見出し削除の確認。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: E402

STATE = app.WINDOW_STATE_FILE
if STATE.exists():
    STATE.unlink()


def main():
    w = app.TTSApp()
    w.update()
    sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()

    print("title =", w.title())
    print("parse '660x600+100+50' ->", app.TTSApp._parse_geometry("660x600+100+50"))
    print("parse offscreen '660x600+-50+-80' ->", app.TTSApp._parse_geometry("660x600+-50+-80"))
    print("screen =", sw, sh)
    print("clamp +9999+9999 ->", w._clamp_to_screen(660, 600, 9999, 9999))
    print("clamp -50,-80   ->", w._clamp_to_screen(660, 600, -50, -80))

    # わざと画面外に動かして保存
    w.geometry("660x600+9999+9999")
    w.update()
    w._save_window_state()
    w.destroy()
    print("saved =", json.loads(STATE.read_text(encoding="utf-8")))

    # 開き直したら画面内に補正されるはず
    w2 = app.TTSApp()
    w2.update()
    g = w2.geometry()
    ww, hh, xx, yy = app.TTSApp._parse_geometry(g)
    on_screen = (0 <= xx) and (0 <= yy) and (xx + ww <= sw) and (yy + hh <= sh)
    print("restored geometry =", g, " -> 画面内?", on_screen)
    w2.destroy()


if __name__ == "__main__":
    main()
