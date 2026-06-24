"""Hugging Face キャッシュ内のシンボリックリンクを実ファイルに置き換える。

Windows では、HF キャッシュの snapshots/<rev>/<file> は blobs/<hash> への
シンボリックリンクになっている。これを PyInstaller でそのまま同梱すると、
リンクが壊れて配布先で「キャッシュにファイルが無い」エラーになる。
そこで同梱前に、リンクを実体コピーへ置き換えて実ファイル化する。

使い方:
    python scripts/dereference_cache.py F:\\mvs-build\\models\\hub

引数を省略すると、HF_HOME または ./models/hub を対象にする。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _default_root() -> Path:
    hf_home = os.environ.get("HF_HOME")
    base = Path(hf_home) if hf_home else (Path(__file__).resolve().parent.parent / "models")
    return base / "hub"


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_root()
    if not root.exists():
        print(f"対象が見つかりません: {root}")
        return 1

    print(f"シンボリックリンクを実ファイルに置換します: {root}")
    replaced = 0
    skipped = 0
    # follow_symlinks せずに走査（リンクのループを避ける）
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            p = Path(dirpath) / name
            if not p.is_symlink():
                continue
            try:
                target = p.resolve()
                if not target.is_file():
                    skipped += 1
                    continue
                p.unlink()
                shutil.copy2(target, p)   # リンク先の中身を実体としてコピー
                replaced += 1
                if replaced % 50 == 0:
                    print(f"  ... {replaced} 件置換")
            except Exception as e:  # noqa: BLE001
                print(f"  置換失敗: {p} ({e})")
                skipped += 1

    print(f"完了: 置換 {replaced} 件 / スキップ {skipped} 件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
