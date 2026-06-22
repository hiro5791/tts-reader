import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app

def snap(w):
    return {
        "lang_btn": w.lang_btn.get(),
        "lbl_text": w.lbl_text.cget("text"),
        "lbl_engine": w.lbl_engine.cget("text"),
        "lbl_voice": w.lbl_voice.cget("text"),
        "lbl_speed": w.lbl_speed.cget("text"),
        "lbl_wave": w.lbl_waveform.cget("text"),
        "lbl_lang": w.lbl_language.cget("text"),
        "speak": w.speak_btn.cget("text"),
        "play": w.play_btn.cget("text"),
        "stop": w.stop_btn.cget("text"),
        "speed_val": w.speed_value_label.cget("text"),
        "status": w.status_label.cget("text"),
        "placeholder": w.text_box.get("1.0","end").strip(),
    }

w = app.TTSApp(); w.update()
print("=== JA (default) ===")
for k,v in snap(w).items(): print(f"  {k}: {v}")

w._on_language_change("English"); w.update()
print("=== EN ===")
for k,v in snap(w).items(): print(f"  {k}: {v}")

w._on_language_change("日本語"); w.update()
print("=== back to JA ===")
s = snap(w)
print("  lbl_text:", s["lbl_text"], "| speak:", s["speak"], "| status:", s["status"])
w.destroy()
