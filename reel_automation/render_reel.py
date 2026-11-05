"""リール動画の自動編集（ffmpeg）。

generate_reel_plan.py が出力した reel_XX.json と、撮影したクリップから
縦1080x1920・テロップ入り・BGM付きの mp4 を作る。

フォルダ構成の例:
    clips/reel_01/cut_1.mp4   (写真 .jpg/.png でも可)
    clips/reel_01/cut_2.mov
    ...

使い方:
    python render_reel.py out/reel_01.json clips/reel_01 --bgm bgm.mp3 -o reel_01.mp4

必要なもの: ffmpeg（PATH に通っていること）、日本語フォント（--font で指定可）
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

W, H, FPS = 1080, 1920, 30
CLIP_EXTS = [".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png"]
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

FONT_CANDIDATES = [
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]


def find_font(user_font: str | None) -> str:
    if user_font:
        return user_font
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    sys.exit("日本語フォントが見つかりません。--font でフォントファイルを指定してください。")


def ff_path(p: Path | str) -> str:
    """ffmpeg フィルタ引数用のパスエスケープ（Windows のドライブ文字対策）。"""
    return str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def find_clip(clip_dir: Path, n: int) -> Path:
    for ext in CLIP_EXTS:
        for cand in (clip_dir / f"cut_{n}{ext}", clip_dir / f"cut_{n}{ext.upper()}"):
            if cand.exists():
                return cand
    sys.exit(f"{clip_dir}/cut_{n}.* が見つかりません（mp4/mov/jpg/png）。")


def drawtext(textfile: Path, font: str, y: str, size: int, box_color: str) -> str:
    return (
        f"drawtext=fontfile='{ff_path(font)}':textfile='{ff_path(textfile)}'"
        f":fontsize={size}:fontcolor=white:borderw=4:bordercolor=black@0.6"
        f":box=1:boxcolor={box_color}:boxborderw=24"
        f":x=(w-text_w)/2:y={y}"
    )


def wrap(text: str, width: int) -> str:
    """日本語を width 文字ごとに改行（テロップのはみ出し防止）。"""
    return "\n".join(text[i:i + width] for i in range(0, len(text), width)) or " "


def render_cut(src: Path, seconds: float, telop: str, hook: str | None,
               font: str, work: Path, idx: int) -> Path:
    out = work / f"seg_{idx}.mp4"
    telop_file = work / f"telop_{idx}.txt"
    telop_file.write_text(wrap(telop, 12), encoding="utf-8")

    vf = [
        f"scale={W}:{H}:force_original_aspect_ratio=increase",
        f"crop={W}:{H}",
        f"fps={FPS}",
        "format=yuv420p",
        drawtext(telop_file, font, "h*0.62", 72, "black@0.35"),
    ]
    if hook:  # 1カット目の冒頭1.5秒だけ大きくフックを出す
        hook_file = work / "hook.txt"
        hook_file.write_text(wrap(hook, 10), encoding="utf-8")
        vf.append(drawtext(hook_file, font, "h*0.16", 88, "0xE85D75@0.85")
                  + ":enable='lt(t,1.5)'")

    inp = ["-loop", "1", "-i", str(src)] if src.suffix.lower() in IMAGE_EXTS else ["-i", str(src)]
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", *inp,
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", f"{seconds:.2f}", "-vf", ",".join(vf),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-shortest", str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("plan_json", type=Path)
    p.add_argument("clip_dir", type=Path)
    p.add_argument("--bgm", type=Path, help="BGMファイル（商用利用可能な音源のみ）")
    p.add_argument("--font", help="日本語フォントファイルのパス")
    p.add_argument("-o", "--output", type=Path, default=Path("reel.mp4"))
    args = p.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg が見つかりません。https://ffmpeg.org からインストールしてください。")

    plan = json.loads(args.plan_json.read_text(encoding="utf-8"))
    font = find_font(args.font)

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        segs = []
        for i, cut in enumerate(plan["cuts"], 1):
            src = find_clip(args.clip_dir, i)
            segs.append(render_cut(src, float(cut["seconds"]), cut["telop"],
                                   plan["hook"] if i == 1 else None, font, work, i))

        concat_list = work / "list.txt"
        concat_list.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs), encoding="utf-8")
        joined = work / "joined.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", str(concat_list), "-c", "copy", str(joined)], check=True)

        total = sum(float(c["seconds"]) for c in plan["cuts"])
        if args.bgm:
            fade_st = max(total - 1.0, 0)
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(joined),
                "-stream_loop", "-1", "-i", str(args.bgm),
                "-filter_complex", f"[1:a]volume=0.6,afade=t=out:st={fade_st:.2f}:d=1[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                "-t", f"{total:.2f}", "-movflags", "+faststart", str(args.output),
            ], check=True)
        else:
            shutil.copy(joined, args.output)

    print(f"書き出し完了: {args.output}（{total:.1f}秒）")
    print("キャプション:\n" + plan["caption"] + "\n\n" + " ".join(plan["hashtags"]))


if __name__ == "__main__":
    main()
