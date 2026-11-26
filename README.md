# DXペディション予定（3か月以内）

NG3K の Announced DX Operations（ADXO）をもとに、3か月以内に運用中・運用予定の
DXペディションを、スマートフォンで見やすい一覧ページにします。
GitHub Actions が1日2回（05:20 と 17:20 UTC）ADXO を取得してページを作り直し、
GitHub Pages で公開します。

- 出典: NG3K Announced DX Operations（Bill Feidt, NG3K） https://www.ng3k.com/Misc/adxo.html
- 作成: JA1BBE
- `docs/ng3k.html` は、NG3K（Bill Feidt）へのクリスマスの贈り物の版です（英語、自局の既定は NG3K・FM19ka）。

## 公開までの手順

1. **アカウントを作る**: https://github.com/signup で無料のアカウントを作ります。
2. **リポジトリを作る**: 右上の「＋」→「New repository」。名前を `dxpeditions`、
   公開範囲を **Public** にして「Create repository」。
3. **スクリプトを置く**: 画面の「uploading an existing file」を押し、
   `build_adxo_page.py` と `README.md` をドラッグして「Commit changes」。
4. **自動実行の設定を置く**: 「Add file」→「Create new file」。ファイル名の欄に
   `.github/workflows/build.yml` と入力し（「/」を打つとフォルダになります）、
   `build.yml` の中身を貼り付けて「Commit changes」。
5. **書き込みを許可する**: 「Settings」→「Actions」→「General」→ 一番下の
   「Workflow permissions」で「Read and write permissions」を選び「Save」。
6. **初回の実行**: 「Actions」タブ →「DXペディション予定ページの更新」→
   「Run workflow」。緑のチェックが付けば、`docs/index.html` ができています。
7. **公開する**（NG3Kの了承を得てから）: 「Settings」→「Pages」→ Source を
   「Deploy from a branch」、Branch を `main`、フォルダを `/docs` にして「Save」。
   数分後に `https://（ユーザー名）.github.io/dxpeditions/` で見られます。
8. **ホームページからリンクする**: Wix のボタンのリンク先を、7 のアドレスにします。

## 注意

- 公開リポジトリでも、60日間まったく動きがないと、GitHub が定期実行を止めることがあります。
  止まったときは「Actions」タブで有効にし直してください。
- ADXO のページの形式が変わって1件も読み取れなかった場合は、ページを書き換えずに
  前回のページを残します（Actions に赤い×が付きます）。
- バンドとモードの表示は、各運用の説明文（Info）からの推定です。
- 先頭の地図（自局はコールサインかグリッドで指定。オーロラ帯・D層の吸収・嵐の広がり・地磁気緯度線を重ねる）と
  各運用の方位・「望ましいバンドと時間帯の目安」（検証中）は、宇宙天気ナウキャスト（ja1bbe-iono）の
  land.json・cty.json、NOAA SWPC の宇宙天気と、伝搬研究（ja1bbe/propagation）の paths.json を、ページを開いたブラウザが読み込んで描きます。
  運用の位置は、ページを作るときに cty.json から求めて埋め込みます（取得できないときは地図に載せず、一覧だけ作ります）。
  表示の言語は、自局が日本国内なら日本語、国外なら英語です（自局を入れていないときは、そのページの言語）。
