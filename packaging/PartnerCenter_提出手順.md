# Multi Voice Studio — Partner Center 提出手順（実務）

ビルド／MSIX 化は完了済み（v1.0.0.2 安定動作確認）。本書は **Partner Center（開発者ダッシュボード）への提出作業**だけに絞った実務手順。
上から順に潰せば提出できる。各項目に「貼ればそのまま使える下書き」を付けてある。

> 識別子（マニフェストと一致必須）
> - **Name**: `9B6C9F60.MultiVoiceStudio`
> - **Publisher**: `CN=E5A55C73-7E5B-4BF9-B37E-C562F23A3A5E`
> - **PublisherDisplayName**: `Hiroyura`
> - **Version**: `1.0.0.2` / x64 / Windows.Desktop (Min 10.0.17763.0)

---

## 0. 提出前チェックリスト（これが全部 ✅ なら提出可）

- [ ] **WACK 合格**（後述 §6）— MSIX を Windows App Certification Kit で検証
- [ ] MSIX が x64 makeappx で正常に pack 済み（`packaging/build_msix.ps1`）
- [ ] アプリ名予約済み（§2）
- [ ] ストア掲載素材：アイコン／スクリーンショット／説明文（§3）
- [ ] 年齢レーティング（IARC アンケート）回答済み（§4）
- [ ] **プライバシーポリシー URL** が公開済み（§5 の下書きをそのまま公開可）
- [ ] 動作要件（GPU 推奨／モデル初回 DL）を説明文に明記（§3）
- [ ] 価格設定（無料 or 有料）決定（§7）

---

## 1. 開発者アカウント

- 個人 or 法人で登録（**登録料あり・一度きり**）。
- **PublisherDisplayName が `Hiroyura`** になっていること。MSIX の Identity Publisher
  （`CN=E5A55C73-...`）は Partner Center が発行した値。アカウントの Product Identity と
  一致していないと審査前に弾かれる。

---

## 2. アプリ名の予約

- Partner Center → 新しいアプリ → 名前 **「Multi Voice Studio」** を予約。
- 予約名と MSIX の DisplayName（`Multi Voice Studio`）を一致させる。

---

## 3. ストア掲載素材

### 3-1. 説明文（日本語）— 貼り付け用

> **Multi Voice Studio — AI 多言語テキスト読み上げ（TTS）**
>
> テキストを自然な音声に変換するデスクトップ TTS アプリです。プリセット音声に加え、
> あなた自身の声を登録して読み上げる「声のクローン」、言葉で声の雰囲気を指定する
> 「声を作る（Voice Design）」など、5 つのモードを搭載。長文の自動分割、読み上げ位置の
> ハイライト、txt / PDF / Word ファイルの読み込み、音量・ピッチ調整に対応します。
>
> **特長**
> - 多言語対応の UI とテキスト読み上げ
> - 自分の声を登録して読み上げる声のクローン
> - 言葉で声の雰囲気を設計する Voice Design
> - 長文のチャンク分割・読み上げハイライト
> - txt / PDF / Word の読み込み、音声ファイル（WAV）保存
>
> **動作環境（重要）**
> - 実用には **NVIDIA GPU（VRAM 8GB 以上）を推奨**。GPU が無い／VRAM が不足する場合は
>   自動的に CPU で動作しますが、生成が非常に低速になります。
> - **初回起動時に AI モデル（数 GB）を自動ダウンロード**します。初回はネット接続と
>   ストレージ空き容量が必要です（2 回目以降はオフラインで動作）。
>
> **ご利用にあたって**
> - 生成音声は AI による合成です。誤読・不自然さが生じる場合があります。
> - 他者へのなりすまし・偽情報・ディープフェイク等、第三者の権利を侵害する目的での
>   利用は禁止します。録音した声の登録は本人の同意が得られたものに限ってください。

### 3-2. 説明文（英語）— 貼り付け用

> **Multi Voice Studio — AI Multilingual Text-to-Speech**
>
> A desktop TTS app that turns text into natural-sounding speech. In addition to preset
> voices, it offers voice cloning from your own recordings and "Voice Design" (describe a
> voice in words). Five modes in total, with automatic long-text chunking, read-along
> highlighting, txt / PDF / Word import, and volume/pitch control.
>
> **System requirements (important)**
> - An **NVIDIA GPU (8GB+ VRAM) is recommended**. Without a capable GPU it falls back to
>   CPU automatically, but generation will be very slow.
> - **On first launch it downloads the AI models (several GB).** An internet connection and
>   free disk space are required the first time; it runs offline afterward.
>
> **Acceptable use**
> - Output is AI-synthesized and may contain mispronunciations. Do not use it to impersonate
>   others, spread misinformation, or create deepfakes. Only register a cloned voice with the
>   consent of the person speaking.

### 3-3. スクリーンショット
- 1280×720 以上推奨。最低 1 枚、できれば各モード（プリセット／クローン／Voice Design／
  ファイル読み込み／ハイライト）で 3〜5 枚。
- アプリ起動 → 各画面を撮るだけ。多言語対応なので日本語 UI のままで可。

### 3-4. アイコン／ロゴ
- `packaging/Assets/`（`scripts/make_msix_assets.py` 生成）の Store ロゴを流用。
- ストア用に 300×300 PNG が別途要求される場合あり。同スクリプトで生成可。

---

## 4. 年齢レーティング（IARC）

- アンケート形式。本アプリは暴力・性的表現・課金等なし。
- 注意点：**ユーザー生成音声＋ネット機能**の有無を正直に回答すること。本アプリは
  生成物を外部送信せず、ユーザー間通信機能も無い（初回モデル DL のみネット使用）。
  → 「ユーザー生成コンテンツの共有なし」「未調整のオンライン通信なし」で回答。

---

## 5. プライバシーポリシー（URL 必須）

**そのまま公開してよい下書き**（GitHub Pages / Gist / 自サイトいずれでも可。URL を提出欄に入力）。

> **Multi Voice Studio Privacy Policy / プライバシーポリシー**
>
> Multi Voice Studio（以下「本アプリ」）は、ユーザーの個人情報・入力テキスト・録音音声・
> 生成音声を、開発者や第三者のサーバーへ送信・収集・保存しません。すべての音声生成は
> ユーザーの PC 上（ローカル）で完結します。
>
> 本アプリは **初回起動時に限り**、AI モデルを取得するため Hugging Face のサーバーへ接続
> します。この通信でユーザーの入力内容が送信されることはありません。2 回目以降はネット
> 接続なしで動作します。
>
> ユーザーが作成した音声ファイル・登録した声・設定は、ユーザーの PC 内
> （`%LOCALAPPDATA%\MultiVoiceStudio`）にのみ保存され、外部に送信されません。
>
> ---
>
> Multi Voice Studio ("the App") does not send, collect, or store any personal data, input
> text, recorded audio, or generated audio on the developer's or any third-party servers.
> All speech generation runs locally on the user's PC.
>
> Only on first launch, the App connects to Hugging Face servers to download AI models. No
> user content is transmitted during this download. The App runs without an internet
> connection afterward.
>
> Files, registered voices, and settings created by the user are stored only on the user's
> PC (`%LOCALAPPDATA%\MultiVoiceStudio`) and are never transmitted externally.
>
> Contact: yuka2803v@gmail.com

---

## 6. WACK 検証（提出前必須）

```powershell
# Windows SDK 同梱。GUI 版でも可。
& "C:\Program Files (x86)\Windows Kits\10\App Certification Kit\appcert.exe" `
  reset
& "C:\Program Files (x86)\Windows Kits\10\App Certification Kit\appcert.exe" `
  test -appxpackagepath "F:\mvs-build\dist\MultiVoiceStudio.msix" `
  -reportoutputpath "F:\mvs-build\wack-report.xml"
```

- full-trust デスクトップ（`runFullTrust`）アプリは WACK の一部項目が緩い。
- 落ちた項目があればレポート（xml）を確認して対応。

---

## 7. 価格・提出

- 価格：無料 or 有料を決める。試用版を出すかも選択。
- パッケージ（MSIX）アップロード → 提出物（説明・素材・レーティング・プライバシー URL）を
  ひも付け → **審査提出**。
- 審査は数日〜。リジェクト時は理由が返るので個別対応。

---

## 参考：関連ファイル
- `packaging/AppxManifest.xml` … Identity / バージョン
- `packaging/build_msix.ps1` … MSIX pack（+ ローカルテスト用自己署名）
- `scripts/make_msix_assets.py` … ストア／タイル用ロゴ生成
- `配布手順_MicrosoftStore.md` … ビルド全体手順（§5 が提出概要）
