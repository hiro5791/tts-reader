# Multi Voice Studio — Microsoft Store 配布手順（まとめ）

このドキュメントは、開発環境で動いているアプリを **Microsoft Store** で配れる形
（モデル同梱・オフライン動作）にするための作業手順です。
**GPU 付きのビルド環境**で、上から順に進めてください。

> 重要：今動いている開発用 `.venv` は壊さないこと。**配布ビルドは専用環境**で行う。

---

## 0. 全体像（5 ステップ）

1. **統合ビルド環境を作る**（app + Qwen + Irodori を 1 つの Python 環境に）
2. **脱 uv の検証**（Irodori を「同一プロセス」で動かす）
3. **モデル同梱の準備**（オフライン動作）
4. **PyInstaller で単体化**（onedir）
5. **MSIX 化 → Partner Center 提出**

エンジンを別プロセス（uv）で動かす従来方式は配布パッケージでは動かないため、
コード側は既に「依存がそろえば同一プロセス実行、無ければ uv にフォールバック」に
対応済み（`tts/irodori_engine.py` の `_run_infer_inproc` / `_inproc_available`）。

---

## 1. 統合ビルド環境を作る

torch のピンは Irodori の `torchcodec<0.11`（＝ torch 2.10 系）だけ。Qwen / transformers は
torch に寛容なので、**torch 2.10 系 + torchcodec 0.10 系**で全部そろえる。

```powershell
# 専用の仮想環境（開発用 .venv とは別に）
py -3.11 -m venv .venv-build
.\.venv-build\Scripts\Activate.ps1

# torch 系を先に CUDA 版で（CUDA は環境に合わせて cu128 等）
pip install "torch==2.10.*" "torchaudio==2.10.*" "torchcodec==0.10.*" `
    --index-url https://download.pytorch.org/whl/cu128

# アプリ + Irodori 推論の依存
pip install -r requirements-build.txt

# Irodori 本体（irodori_tts パッケージ）を「依存なし」で導入
#   → PyInstaller が site-packages から irodori_tts を見つけられるようにする
pip install --no-deps .\vendor\Irodori-TTS

# ビルドツール
pip install pyinstaller
```

> `dacvae` / `silentcipher` は git 依存。**git** と（環境により）ビルドツールが必要。

---

## 2. 脱 uv の検証（最重要の関門）

```powershell
python app.py
```

- **Qwen** で生成できること。
- **Irodori** で生成し、コンソールに `[Irodori] 実行（in-process, …）` と出ること
  （＝ uv を使わず同一プロセスで動いた＝脱 uv 成功）。
- 長文（分割）・「声を作る」・「保存した声」も一通り確認。

ここが通れば、配布の最大の山を越えています。通らない場合は不足モジュールを
`requirements-build.txt` に足して再確認。

---

## 3. モデル同梱の準備（オフライン動作）

### 3-1. モデルを `models/` に集める

```powershell
$env:HF_HOME = "$PWD\models"
python scripts\prefetch_models.py        # 全モデルを models/ にダウンロード
Remove-Item Env:\HF_HOME
```

### 3-2. 実行時に同梱モデルを使う（app.py に追記）

`app.py` の先頭付近（既存の `MVS_OFFLINE` 判定の**前**）に、配布時だけ効く分岐を足す:

```python
# --- 配布（PyInstaller）同梱モデルを使う ---
import sys, os
from pathlib import Path
if getattr(sys, "frozen", False):
    _base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    _bundled_models = _base / "models"
    if _bundled_models.exists():
        os.environ.setdefault("HF_HOME", str(_bundled_models))
        os.environ.setdefault("MVS_OFFLINE", "1")   # → HF_HUB_OFFLINE=1
```

- 開発時（非 frozen）は何もしないので影響なし。
- これで配布版は同梱 `models/` から読み、ネット不要で起動できる。

---

## 4. PyInstaller で単体化

```powershell
pyinstaller MultiVoiceStudio.spec
# 出力: dist\MultiVoiceStudio\MultiVoiceStudio.exe（onedir）
```

- `MultiVoiceStudio.spec` は雛形。**不足モジュール/データはビルド機で追記**（spec 末尾のコメント参照）。
- まず `dist\MultiVoiceStudio\MultiVoiceStudio.exe` を直接起動して、
  Qwen / Irodori 両方の生成・再生・保存・ファイル読み込みを確認する。
- 起動しない/落ちる場合は、一時的に spec の `console=True` にしてエラーを見る。

### サイズの目安
モデル同梱で **約 15〜18GB**。Store のパッケージ上限内だが大きいので、初回 DL/インストールは重い。

---

## 5. MSIX 化 → Microsoft Store 提出

### 5-1. MSIX パッケージを作る
`dist\MultiVoiceStudio\` を MSIX に包む。いずれかの方法で:

- **MSIX Packaging Tool**（Store から入手・GUI）
- **Advanced Installer**（無料版で MSIX 可・おすすめ、設定が楽）
- **makeappx.exe + AppxManifest.xml**（Windows SDK・CLI）

ポイント:
- **コード署名**：Store 提出版は **Partner Center 側で署名**されるので、自前の証明書は不要
  （ローカルでテスト起動するだけなら自己署名証明書が要る）。
- AppxManifest に **アプリ ID / 表示名 / バージョン / アイコン / 機能** を記載。
- 大容量のため、可能なら不要ファイルを削いでサイズを抑える。

### 5-2. Partner Center（開発者ダッシュボード）
1. **開発者アカウント登録**（個人 or 法人。登録料あり）。
2. **アプリ名を予約**。
3. **ストア掲載素材**：アイコン、スクリーンショット、説明文（多言語可：本アプリは 20 言語 UI）。
4. **年齢レーティング**（IARC アンケート）。
5. **プライバシーポリシー URL**（ネット送信が無いなら「収集しない」旨で可。要 URL）。
6. **動作要件の明記**：本アプリは実用に **NVIDIA GPU 推奨/必須**（CPU は非常に遅い）。
   ストア説明に明記しておく。
7. **WACK 検証**：Windows App Certification Kit でパッケージを事前チェック。
8. MSIX をアップロードして審査提出。

### 5-3. 注意書き（説明文/利用規約に入れる）
- Irodori の**倫理ガイドライン**（なりすまし・偽情報・ディープフェイク禁止）に沿った利用を促す一文。
- 生成音声の品質・誤読は AI 由来であること（情報ダイアログの注意書きと整合）。

---

## 6. チェックリスト

- [ ] `.venv-build` で torch 2.10 系 + torchcodec 0.10 系に統一
- [ ] `pip install -r requirements-build.txt` ＋ `pip install --no-deps .\vendor\Irodori-TTS`
- [ ] `python app.py` で Irodori が **in-process** で動く（脱 uv）
- [ ] `models/` にモデルを prefetch、app.py に frozen 用の同梱モデル分岐を追記
- [ ] `pyinstaller MultiVoiceStudio.spec` で onedir ビルド、exe 単体で全機能確認
- [ ] `THIRD-PARTY-NOTICES.md` を同梱（spec で対応済み）
- [ ] MSIX 化（署名は Store 側）
- [ ] Partner Center：アカウント / アプリ名 / 素材 / レーティング / プライバシー / 要件明記 / WACK
- [ ] 審査提出

---

## 参考：関連ファイル
- `requirements-build.txt` … 統合ビルド環境の依存
- `MultiVoiceStudio.spec` … PyInstaller 定義（雛形）
- `scripts/prefetch_models.py` … モデル一括ダウンロード
- `THIRD-PARTY-NOTICES.md` … 同梱物のライセンス表示（モデル重み 7 点を含む）
- `tts/irodori_engine.py` … in-process 実行（`_run_infer_inproc` / 自動フォールバック）
