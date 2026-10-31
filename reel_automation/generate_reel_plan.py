"""24スイーツショップ岡山店 リール企画の自動生成。

商品CSV → Claude → 1週間分のリール企画（フック・カット割り・テロップ・
キャプション・ハッシュタグ・撮影指示）を JSON / CSV / 撮影指示書(Markdown) で出力する。

使い方:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...
    python generate_reel_plan.py products.sample.csv --count 5 --out out/
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

import anthropic

MODEL = "claude-opus-5-5"

STORE_PROFILE = """\
店舗名: 24スイーツショップ岡山店
業態: 24時間営業の無人スイーツ販売店（冷凍自販機・キャッシュレス対応）
強み: 深夜・早朝でも買える／非対面で気軽／手土産にも使える
所在地: 岡山県（キャプションには「岡山」を必ず入れる。番地は書かない）
主なターゲット: 岡山市周辺の20〜40代、夜にスイーツを買いたい人、手土産を探す人
"""

PATTERNS = [
    "深夜・早朝訴求（24時間買える強み）",
    "開封・断面ASMR（箱を開けて断面アップ）",
    "買い方ガイド（自販機の使い方を15秒で）",
    "新商品・季節限定（今週から入荷）",
    "ランキング（売れ筋TOP3）",
    "手土産提案（急な手土産に）",
]

SYSTEM_PROMPT = f"""あなたは岡山の無人スイーツ店のInstagramリール担当ディレクターです。
来店（ルート検索・プロフィールアクセス）につながる15〜20秒の縦型リールを企画します。

# 店舗情報
{STORE_PROFILE}
# 企画の型（できるだけ偏らないように割り振る）
{chr(10).join(f"- {p}" for p in PATTERNS)}

# ルール
- 冒頭1.5秒で指が止まるフックにする（疑問・共感・意外性）。
- カットは3〜5個、合計15〜20秒。各カットは実店舗でスマホ1台・1人で撮れる内容にする。
- テロップは1カット15文字以内、読みやすい口語。
- 価格・商品の特徴は入力された情報だけを使う。書かれていない効能・産地・
  「無添加」「低糖質」などの表現、アレルギーに関する記述は絶対に作らない。
- キャプションは「フック1行 → 商品の魅力 → 24時間買える・岡山の店舗であること → 行動喚起（保存・来店）」の順。
- ハッシュタグは地域系（#岡山スイーツ 等）とジャンル系を混ぜて8〜12個。
- 推したい度が0の商品は使わない。推したい度が高い商品を優先する。
"""

REEL_SCHEMA = {
    "type": "object",
    "properties": {
        "reels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "管理用の短いタイトル"},
                    "pattern": {"type": "string", "description": "企画の型"},
                    "product": {"type": "string"},
                    "hook": {"type": "string", "description": "冒頭1.5秒のフック文言"},
                    "cuts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "seconds": {"type": "number"},
                                "shot": {"type": "string", "description": "撮影指示（何を・どの角度で・どう動かす）"},
                                "telop": {"type": "string", "description": "画面テロップ"},
                            },
                            "required": ["seconds", "shot", "telop"],
                            "additionalProperties": False,
                        },
                    },
                    "caption": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "bgm_mood": {"type": "string"},
                    "post_time": {"type": "string", "description": "推奨投稿曜日・時間帯"},
                },
                "required": [
                    "title", "pattern", "product", "hook", "cuts",
                    "caption", "hashtags", "bgm_mood", "post_time",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["reels"],
    "additionalProperties": False,
}


def load_products(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f)]
    return [r for r in rows if (r.get("推したい度") or "1").strip() != "0"]


def generate(products: list[dict[str, str]], count: int, notes: str) -> list[dict]:
    client = anthropic.Anthropic()
    user_msg = (
        f"今日の日付: {date.today().isoformat()}\n"
        f"作成本数: {count}本\n"
        f"今週のメモ: {notes or '特になし'}\n\n"
        "# 商品リスト(JSON)\n"
        f"{json.dumps(products, ensure_ascii=False, indent=2)}\n\n"
        f"上記から{count}本のリール企画を作成してください。"
    )
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM_PROMPT,
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": REEL_SCHEMA},
        },
        messages=[{"role": "user", "content": user_msg}],
    )
    if response.stop_reason == "refusal":
        sys.exit("Claude が生成を断りました。商品情報の表現を見直してください。")
    if response.stop_reason == "max_tokens":
        sys.exit("出力が長すぎて途中で切れました。--count を減らしてください。")
    text = "".join(b.text for b in response.content if b.type == "text")
    return json.loads(text)["reels"]


def write_outputs(reels: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 編集スクリプト用 JSON（1本ずつ）
    for i, reel in enumerate(reels, 1):
        (out_dir / f"reel_{i:02d}.json").write_text(
            json.dumps(reel, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 2) 確認・Canva一括作成用 CSV
    with (out_dir / "reels.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["No", "タイトル", "型", "商品", "フック", "テロップ", "キャプション", "ハッシュタグ", "BGM", "投稿時間"])
        for i, r in enumerate(reels, 1):
            w.writerow([
                i, r["title"], r["pattern"], r["product"], r["hook"],
                " / ".join(c["telop"] for c in r["cuts"]),
                r["caption"], " ".join(r["hashtags"]), r["bgm_mood"], r["post_time"],
            ])

    # 3) 撮影指示書（現場でスマホで見る用）
    lines = [f"# 撮影指示書（{date.today().isoformat()}）", "",
             "縦向き・明るい場所・1カット3〜5秒。撮ったら `reel_XX/cut_1.mp4` のように保存。", ""]
    for i, r in enumerate(reels, 1):
        lines += [f"## reel_{i:02d}：{r['title']}（{r['product']}）", ""]
        for j, c in enumerate(r["cuts"], 1):
            lines.append(f"- [ ] cut_{j}（{c['seconds']}秒）: {c['shot']}")
        lines.append("")
    (out_dir / "shooting_list.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("products_csv", type=Path)
    p.add_argument("--count", type=int, default=5, help="作成本数（既定5）")
    p.add_argument("--notes", default="", help="今週のメモ（例: 雨の予報、ハロウィン週）")
    p.add_argument("--out", type=Path, default=Path("out"))
    args = p.parse_args()

    products = load_products(args.products_csv)
    if not products:
        sys.exit("推したい度が1以上の商品がありません。")
    reels = generate(products, args.count, args.notes)
    write_outputs(reels, args.out)
    print(f"{len(reels)}本の企画を {args.out}/ に出力しました（reels.csv / shooting_list.md / reel_XX.json）")


if __name__ == "__main__":
    main()
