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

**デスクトップアプリのウィンドウ**が開きます（ブラウザは使いません）。
文章を入れ、エンジン・声・速度を選び、「読み上げる」を押してください。
できた音声は自動で再生され、「▶ 再生」「■ 停止」でも操作できます。

- 生成は裏側（別スレッド）で行うので、生成中も画面は固まりません（ボタンは「生成中…」になります）。
- 画面下のステータスに「生成中…／生成完了／再生中…／準備OK」が表示され、エラー時は赤字で出ます。
- 生成すると音声の波形が表示され、再生中は赤い縦線（再生位置）が左から右へ動きます。
- ボタンは状況に応じて押せる／押せないが自動で切り替わります（誤操作防止）。
- 画面右上で表示言語を「日本語 / English」に切り替えられます（初期は日本語）。表示文字は i18n.py の辞書にまとまっており、言語を足すときはキーを追加するだけです。
- ブラウザ版（Gradio）を使いたいときは `python app_web.py` で起動できます（予備）。

### 選べるもの（フェーズ2で追加）

- **声（話者）**：エンジンを選ぶと、その声の一覧に自動で入れ替わります。
  - Qwen3 … 9種類（女性・男性）。初期値は日本語ネイティブの「おの あんな」。
  - Irodori … デフォルトの声1つ（許諾済みの参照音声を `voices/irodori/` に置き、
    `tts/irodori_engine.py` の `VOICE_PRESETS` に1行足せば声を増やせます）。
- **速度**：0.5〜2.0倍のスライダー（1.0が標準）。声の高さは変えずに速さだけ変わります。

※ 初回はモデルの読み込みで1〜数分かかります。2回目以降は速くなります。
