# リール自動化ツール（24スイーツショップ岡山店）

全体の設計・運用フローは [`../docs/24sweets-reel-automation-plan.md`](../docs/24sweets-reel-automation-plan.md) を参照。

## 準備（初回のみ）

1. Python 3.10以上 と ffmpeg をインストール
2. `pip install -r requirements.txt`
3. Claude APIキーを設定：`export ANTHROPIC_API_KEY=sk-ant-...`（Windowsは `setx ANTHROPIC_API_KEY sk-ant-...`）

## 毎週の使い方

### ① 企画を自動生成（月曜・1分）

```bash
python generate_reel_plan.py products.sample.csv --count 5 --notes "ハロウィン週・週末は雨予報" --out out/
```

出力：
- `out/reels.csv` … 企画一覧（確認用。Canvaの一括作成にもそのまま使える）
- `out/shooting_list.md` … 撮影指示書（スマホで見ながら撮る）
- `out/reel_01.json` … 編集用データ

### ② 撮影（火曜・30分）

撮影指示書どおりに撮って、`clips/reel_01/cut_1.mp4`、`cut_2.mp4`… の名前で保存（写真 .jpg でも可）。

### ③ 自動編集（1本数十秒）

```bash
python render_reel.py out/reel_01.json clips/reel_01 --bgm bgm/chill.mp3 -o reel_01.mp4
```

- 縦1080×1920、1カット目の冒頭1.5秒にフック、各カットにテロップを自動で入れる
- BGMは商用利用可能な音源のみ。Instagram内の音源を使う場合は `--bgm` なしで書き出し、アプリ側で追加
- 日本語フォントが見つからない場合は `--font C:/Windows/Fonts/meiryob.ttc` のように指定

### ④ 確認して予約投稿

価格・商品名・在庫を確認 → Meta Business Suite で予約投稿（キャプションは実行時に表示されるものをコピー）。

## 商品CSVの列

| 列 | 内容 |
|---|---|
| 商品名 / 価格 / 特徴 / 季節性 | AIはここに書いた情報だけを使う（書いていない効能などは作らせない設定） |
| 推したい度 | 0〜5。**0にすると企画に使われない**（売切れ・在庫僅少時） |
