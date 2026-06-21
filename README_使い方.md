# 読み上げアプリ（最小版）使い方

文章を貼り付けて、エンジン（Qwen3 / Irodori）を選び、ボタンを押すと音声で読み上げます。

## このフォルダの中身

- `app.py` … 画面（ブラウザで動くアプリ本体）
- `tts/` … 読み上げの中身
  - `adapter.py` … 共通の窓口（どのエンジンを使うか振り分ける）
  - `qwen_engine.py` … Qwen3-TTS を呼ぶ部分
  - `irodori_engine.py` … Irodori-TTS を呼ぶ部分
- `scripts/` … 準備やテスト用の小さなスクリプト
- `outputs/` … 作られた音声ファイルが入る

## 準備（初回だけ）

PowerShell をこのフォルダで開いて、順番に実行します。

### 1. メイン環境を作る（Qwen3 とアプリ画面）

```powershell
# 仮想環境を作って有効化
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# GPU 版の PyTorch を入れる（NVIDIA GPU 向け）
pip install torch --index-url https://download.pytorch.org/whl/cu128

# アプリに必要なものを入れる
pip install -r requirements.txt
```

### 2. Qwen3 だけ先に動作確認

```powershell
python scripts/test_qwen.py
```

`outputs/` に wav ができれば成功です。

### 3. Irodori を準備（後から）

`uv` と `git` が必要です。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_irodori.ps1
```

## 使う（毎回）

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

ブラウザで `http://127.0.0.1:7860` が開きます。
文章を入れ、エンジンを選び、「読み上げる」を押してください。

※ 初回はモデルの読み込みで1〜数分かかります。2回目以降は速くなります。
