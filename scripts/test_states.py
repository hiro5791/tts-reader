import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app

def btn(w):
    return (str(w.speak_btn.cget("state")), str(w.play_btn.cget("state")), str(w.stop_btn.cget("state")))

def main():
    w = app.TTSApp(); w.update()
    log = [("idle", w._state, btn(w), "cursor", w._cursor)]
    w.engine_btn.set("Qwen3-TTS"); w._on_engine_change("Qwen3-TTS")
    w.text_box.delete("1.0","end"); w.text_box.insert("1.0","joutai test")
    ph = {"t": time.time(), "stopped": False}
    def tick():
        st = w._state
        if st == app.STATE_PLAYING and not ph["stopped"]:
            log.append(("playing", st, btn(w), "cursor", w._cursor is not None, "dur", round(w._audio_duration,2)))
            ph["stopped"] = True; w.after(400, dostop); return
        if time.time()-ph["t"] > 180:
            log.append(("timeout", st)); w.destroy(); return
        w.after(150, tick)
    def dostop():
        w._on_stop(); w.update()
        log.append(("stopped", w._state, btn(w)))
        w.after(300, w.destroy)
    w.after(300, w._on_speak); w.after(600, tick); w.mainloop()
    print("=== state test ===")
    for r in log: print("  ", *r)

main()
