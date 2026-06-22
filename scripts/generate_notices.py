"""THIRD-PARTY-NOTICES.md を生成する。

同梱するモデル（Qwen / Irodori / codec）・同梱コード（Irodori リポジトリ）・
Python 依存パッケージのライセンス情報とライセンス全文をまとめて1ファイルにする。
ストア配布などで必要な「サードパーティ ライセンス表示」用。

実行:
    .venv\\Scripts\\python scripts\\generate_notices.py

備考:
  - pip パッケージのライセンス全文は、各パッケージの配布物（dist-info）に同梱された
    LICENSE / NOTICE 等のファイルから取り出す（実際に配っているテキストそのもの）。
  - モデルや vendored リポジトリは、宣言ライセンス（Apache-2.0 / MIT）の正文を
    付録としてまとめ、各成果物には著作権表示とURLを併記する。
"""

from __future__ import annotations

import importlib.metadata as ilm
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "THIRD-PARTY-NOTICES.md"

# ---- 同梱モデル（重み）: (表示名, ライセンス, 著作権/権利者, 取得元URL) -------
MODELS = [
    ("Qwen3-TTS-12Hz-1.7B-CustomVoice（モデル重み）", "Apache-2.0",
     "Alibaba Cloud / Qwen Team", "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    ("Qwen3-TTS-12Hz-1.7B-Base（モデル重み）", "Apache-2.0",
     "Alibaba Cloud / Qwen Team", "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base"),
    ("Irodori-TTS-500M-v3（モデル重み）", "MIT",
     "Aratako", "https://huggingface.co/Aratako/Irodori-TTS-500M-v3"),
    ("Irodori-TTS-600M-v3-VoiceDesign（モデル重み）", "MIT",
     "Aratako", "https://huggingface.co/Aratako/Irodori-TTS-600M-v3-VoiceDesign"),
    ("Semantic-DACVAE-Japanese-32dim（codec 重み）", "MIT",
     "Aratako", "https://huggingface.co/Aratako/Semantic-DACVAE-Japanese-32dim"),
    ("facebook/dacvae-watermarked（codec のベース）", "Apache-2.0",
     "Meta Platforms, Inc.", "https://huggingface.co/facebook/dacvae-watermarked"),
]

# ---- 同梱コード（リポジトリ）-------------------------------------------------
REPOS = [
    ("Irodori-TTS（ソース・vendor 同梱）", "MIT", "2026 Aratako",
     "https://github.com/Aratako/Irodori-TTS"),
]

# ---- Python 依存（同梱するもの）---------------------------------------------
PIP_PACKAGES = [
    "qwen-tts", "torch", "customtkinter", "soundfile", "matplotlib",
    "numpy", "tkinterdnd2", "gradio", "huggingface-hub", "transformers",
    "librosa",
]

LICENSE_FILE_PREFIXES = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")


def _dist(name: str):
    for n in (name, name.replace("-", "_"), name.replace("_", "-")):
        try:
            return ilm.distribution(n)
        except ilm.PackageNotFoundError:
            continue
    return None


def _license_texts(dist) -> list[tuple[str, str]]:
    """dist-info に同梱された LICENSE/NOTICE 等の (ファイル名, 全文) を返す。

    同じ中身は1回だけ（重複除去）。読み出しは絶対パス経由で行う。
    """
    out: list[tuple[str, str]] = []
    seen: set[int] = set()
    try:
        files = dist.files or []
    except Exception:
        files = []
    for f in files:
        base = Path(f.name).name.upper()
        if not base.startswith(LICENSE_FILE_PREFIXES):
            continue
        try:
            p = Path(dist.locate_file(f))
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if not text or not text.strip():
            continue
        h = hash(text.strip())
        if h in seen:
            continue
        seen.add(h)
        out.append((Path(f.name).name, text))
    return out


def _meta(dist):
    md = dist.metadata
    # 新メタdata（PEP 639）の License-Expression を最優先
    lic = (md.get("License-Expression") or "").strip()
    if not lic:
        lic = (md.get("License") or "").strip()
    # License 欄に全文が入っている場合があるので、分類子があればそちらを優先
    cls = [c for c in (md.get_all("Classifier") or []) if c.startswith("License ::")]
    if md.get("License-Expression"):
        pass   # すでに簡潔な式が入っているのでそのまま使う
    elif cls:
        lic = "; ".join(c.split("::")[-1].strip() for c in cls)
    elif lic:
        lic = lic.splitlines()[0].strip()   # 表が崩れないよう1行目だけにする
    else:
        lic = "（メタdataに記載なし）"
    if len(lic) > 60:
        lic = lic[:57] + "…"
    author = (md.get("Author") or md.get("Author-email") or "").splitlines()[0] if (md.get("Author") or md.get("Author-email")) else ""
    return md.get("Name", "?"), md.get("Version", "?"), lic, author


def _find_canonical(marker: str) -> str | None:
    """インストール済みパッケージから、指定文言を含むライセンス全文を1つ探す。"""
    for d in ilm.distributions():
        for _name, text in _license_texts(d):
            if marker in text:
                return text
    return None


def build() -> str:
    lines: list[str] = []
    add = lines.append

    add("# サードパーティ ライセンス表示（THIRD-PARTY NOTICES）\n")
    add("本アプリ（Multi Voice Studio）は、以下の第三者の成果物を同梱・利用しています。")
    add("各成果物の著作権は各権利者に帰属します。ライセンス全文は本書末尾の付録、")
    add("または各成果物に同梱のテキストを参照してください。\n")
    add("> このファイルは scripts/generate_notices.py で自動生成しています。\n")

    add("\n## 1. 同梱モデル（重み）\n")
    add("| 成果物 | ライセンス | 権利者 | 取得元 |")
    add("|---|---|---|---|")
    for name, lic, holder, url in MODELS:
        add(f"| {name} | {lic} | {holder} | {url} |")

    add("\n## 2. 同梱コード（リポジトリ）\n")
    add("| 成果物 | ライセンス | 著作権 | 取得元 |")
    add("|---|---|---|---|")
    for name, lic, holder, url in REPOS:
        add(f"| {name} | {lic} | © {holder} | {url} |")

    add("\n## 3. Python 依存パッケージ\n")
    add("各パッケージが配布物に同梱しているライセンス全文を、後ろの「個別ライセンス」に収録しています。\n")
    add("| パッケージ | バージョン | ライセンス | 作者 |")
    add("|---|---|---|---|")
    pkg_license_blocks: list[tuple[str, list[tuple[str, str]]]] = []
    for pkg in PIP_PACKAGES:
        d = _dist(pkg)
        if d is None:
            add(f"| {pkg} | （未インストール） | - | - |")
            continue
        name, ver, lic, author = _meta(d)
        add(f"| {name} | {ver} | {lic} | {author} |")
        texts = _license_texts(d)
        if texts:
            pkg_license_blocks.append((f"{name} {ver}", texts))

    # ---- 付録A：モデル/コードの宣言ライセンス正文（Apache-2.0 / MIT）--------
    add("\n---\n\n## 付録A：モデル・同梱コードのライセンス正文\n")
    apache = _find_canonical("Apache License")
    mit = _find_canonical("Permission is hereby granted, free of charge")
    add("### Apache License 2.0（Qwen3-TTS 各モデル / facebook dacvae のベース 等）\n")
    if apache:
        add("```\n" + apache.strip() + "\n```\n")
    else:
        add("（正文は https://www.apache.org/licenses/LICENSE-2.0 を参照）\n")
    add("### MIT License（Irodori-TTS モデル・コード / Semantic-DACVAE codec 等）\n")
    add("各成果物の著作権表示（© Aratako 等）と併せて、以下の MIT License 条文が適用されます。\n")
    if mit:
        add("```\n" + mit.strip() + "\n```\n")
    else:
        add("（MIT License 標準条文を参照）\n")

    # ---- 付録B：各 Python パッケージ同梱のライセンス全文 --------------------
    add("\n---\n\n## 付録B：Python 依存パッケージの個別ライセンス\n")
    for title, texts in pkg_license_blocks:
        add(f"\n### {title}\n")
        for fname, text in texts:
            add(f"<details><summary>{fname}</summary>\n")
            add("```\n" + text.strip() + "\n```\n")
            add("</details>\n")

    return "\n".join(lines) + "\n"


def main() -> int:
    content = build()
    OUT.write_text(content, encoding="utf-8")
    print(f"生成しました: {OUT}")
    print(f"  行数: {content.count(chr(10))} / 文字数: {len(content)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
