"""MSIX に必要な最小限のアイコン（ロゴ）PNG を生成する。

本番ではちゃんとしたアイコンに差し替える前提の「仮ロゴ」。アプリ色（青）の四角に
白い枠を描いただけのシンプルなもの。Pillow（matplotlib 依存で入っていることが多い）を使う。

出力先（既定）: packaging/Assets/
    StoreLogo.png        50x50
    Square44x44Logo.png  44x44
    Square150x150Logo.png 150x150

使い方:
    python scripts/make_msix_assets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# アプリ色（app.py の波形色に合わせた青）
BG = (31, 106, 165, 255)
FG = (255, 255, 255, 255)
SIZES = {
    "StoreLogo.png": 50,
    "Square44x44Logo.png": 44,
    "Square150x150Logo.png": 150,
}


def main() -> int:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        print("Pillow が必要です。 pip install pillow を実行してください。")
        return 1

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path(__file__).resolve().parent.parent / "packaging" / "Assets")
    out.mkdir(parents=True, exist_ok=True)

    for name, s in SIZES.items():
        img = Image.new("RGBA", (s, s), BG)
        d = ImageDraw.Draw(img)
        m = max(2, s // 6)              # 枠の内側マージン
        w = max(1, s // 16)             # 枠線の太さ
        d.rectangle([m, m, s - m - 1, s - m - 1], outline=FG, width=w)
        img.save(out / name)
        print(f"  生成: {out / name} ({s}x{s})")

    print(f"完了: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
