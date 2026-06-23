"""オフラインで使うために、必要なモデルを丸ごと先にダウンロードしておくスクリプト。

ダウンロードと、メモリへの読み込みは別物。これはダウンロードだけを先に済ませる。
途中まで落ちているモデルは続きから再開して完了させる（resume 対応）。

実行（.venv のPythonで）:
    # 全部ダウンロード
    .venv\\Scripts\\python scripts\\prefetch_models.py
    # 一部だけ（qwen / irodori / codec / all）
    .venv\\Scripts\\python scripts\\prefetch_models.py qwen
    # 不足チェックだけ（ダウンロードしない）
    .venv\\Scripts\\python scripts\\prefetch_models.py check

オフライン実行（同梱配布）時は、環境変数 MVS_OFFLINE=1 を立てると
アプリ／このスクリプトはネットを一切見に行かなくなる（キャッシュのみ使用）。
"""

from __future__ import annotations

import sys

# 役割 -> HuggingFace のモデル名
MODELS = {
    # Qwen3-TTS（プリセット＋保存した声クローン＋声を作る）
    "qwen": [
        "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",   # プリセットの声（＋喋り方instruct）
        "Qwen/Qwen3-TTS-12Hz-1.7B-Base",          # 保存した声（クローン）
        "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",   # 声を作る（VoiceDesign）
    ],
    # Irodori-TTS（基本＋VoiceDesign）
    "irodori": [
        "Aratako/Irodori-TTS-500M-v3",
        "Aratako/Irodori-TTS-600M-v3-VoiceDesign",
    ],
    # Irodori が使う音声コーデック
    "codec": [
        "Aratako/Semantic-DACVAE-Japanese-32dim",
    ],
    # Irodori が内部で使うテキストトークナイザ（モデル重みは不要。設定/トークナイザのみ）
    "tokenizer": [
        "llm-jp/llm-jp-3-150m",            # 本文のテキストトークナイザ
        "openai/clip-vit-large-patch14",  # caption（声の説明）のテキストトークナイザ
    ],
    # Irodori が使う補助モデル（重み込みで必要）
    "aux": [
        "sony/silentcipher",              # 音声透かし(watermark)モデル（.ckpt 重み）
    ],
}

# 重み（巨大）は不要で、設定・トークナイザのファイルだけ要るリポジトリ。
# これらは *.safetensors 等の重みを除外してダウンロードする（同梱サイズ削減）。
TOKENIZER_ONLY = {"llm-jp/llm-jp-3-150m", "openai/clip-vit-large-patch14"}
_WEIGHT_PATTERNS = ["*.safetensors", "*.bin", "*.pt", "*.pth", "*.h5", "*.msgpack",
                    "*.gguf", "*.onnx", "*.ckpt"]


def _all_repos() -> list[str]:
    seen, repos = set(), []
    for group in MODELS.values():
        for r in group:
            if r not in seen:
                seen.add(r)
                repos.append(r)
    return repos


def _resolve(which: str) -> list[str]:
    if which in ("all", "check"):
        return _all_repos()
    if which in MODELS:
        return list(MODELS[which])
    return []


def cmd_check() -> int:
    """各モデルがローカルキャッシュに揃っているかだけ調べる（DLしない）。"""
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import LocalEntryNotFoundError

    missing = []
    for repo in _all_repos():
        ignore = _WEIGHT_PATTERNS if repo in TOKENIZER_ONLY else None
        try:
            snapshot_download(repo_id=repo, local_files_only=True, ignore_patterns=ignore)
            print(f"OK   {repo}")
        except (LocalEntryNotFoundError, Exception):
            print(f"未取得 {repo}")
            missing.append(repo)
    if missing:
        print(f"\n不足: {len(missing)} 件。`prefetch_models.py` を実行して取得してください。")
        return 1
    print("\nすべて揃っています。オフラインで動かせます。")
    return 0


def cmd_download(repos: list[str]) -> int:
    from huggingface_hub import snapshot_download

    for repo in repos:
        ignore = _WEIGHT_PATTERNS if repo in TOKENIZER_ONLY else None
        note = "（トークナイザ/設定のみ・重み除外）" if ignore else "（途中まであれば続きから）"
        print(f"=== ダウンロード中: {repo} {note}===")
        path = snapshot_download(repo_id=repo, ignore_patterns=ignore)   # 既定のHFキャッシュへ。resume 対応。
        print(f"完了: {repo}\n  -> {path}\n")
    print("モデルの準備ができました。初回生成のダウンロード待ちは無くなります。")
    return 0


def main(argv: list[str]) -> int:
    which = (argv[0].lower() if argv else "all")
    if which == "check":
        return cmd_check()
    repos = _resolve(which)
    if not repos:
        print(f"不明な指定です: {which!r}（使えるのは: {', '.join(MODELS)} / all / check）")
        return 1
    return cmd_download(repos)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
