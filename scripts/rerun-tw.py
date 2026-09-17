"""用台灣語料把三支量測腳本跑一輪，並把結果收成一份報告。

原研究的頻率與倍率全部來自簡體語料，繁體版只換了用字，沒有重測。
要用台灣語料複核，缺的不是程式而是語料：這支腳本負責把語料目錄的規範、
環境檢查與三支腳本的執行串成一個指令，語料備齊後一行就能跑完。

用法：
    python3 scripts/rerun-tw.py --init <語料目錄>    # 建立目錄骨架與說明
    python3 scripts/rerun-tw.py <語料目錄>           # 檢查語料並跑完三支腳本
    python3 scripts/rerun-tw.py <語料目錄> --out <報告路徑>

目錄規範（與三支腳本的讀取慣例一致）：
    <語料目錄>/human/<來源>/*.md   每個子目錄是一個來源或作者，用來看組間穩定性
    <語料目錄>/ai/*.md             檔名寫成 <模型>-T<序號>.md，模型名用來分模型統計
    <語料目錄>/_meta/              說明與歷次報告放這裡，量測時會被略過

沒裝 opencc 也能跑，但簡體語料會漏抓；混用繁簡語料時請先 pip install opencc。
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
META_DIR = "_meta"
HUMAN_DIR = "human"
AI_DIR = "ai"

# 原研究的規模，用來提醒台灣語料是否夠大到值得下結論（RESEARCH.md §1）
REFERENCE_SCALE = {"人類篇數": 283, "AI 篇數": 180, "總漢字數（萬）": 283}
MIN_HUMAN_GROUPS = 2

META_README = """# 語料目錄說明

直接放在這個目錄下的檔案不會被量測腳本讀到（三支腳本會略過父目錄是 `_meta` 的檔案），
說明、授權紀錄與歷次報告放這裡。再往下開子目錄就不保證會被略過了。

## 放法

    human/<來源>/*.md   每個子目錄是一個來源或作者。至少兩組，否則算不出組間穩定性。
    ai/*.md             檔名 <模型>-T<序號>.md，例如 claude-opus-5-T1.md；
                        `-T` 之後的部分不影響模型標籤。

## 收語料時要留意的事

1. 人類側與 AI 側的話題要盡量配對。原研究的已知缺陷就是話題未嚴格配對，
   兩側差異可能來自話題而非文本來源（RESEARCH.md §6）。
2. 人類側來源不要過度集中。原研究單一來源約佔 140 篇，這是它被外部指出的侷限。
3. 文體要對齊。部落格對部落格、新聞對新聞，不要拿新聞比對社群貼文。
4. 語料本身不要進版本庫，只留報告與來源說明。

## 跑法

    python3 scripts/rerun-tw.py <語料目錄>

報告會寫進 `_meta/`。報告本身也是 .md，放這裡才不會在下一次量測時被當成語料讀進去。
"""


def run_script(name, args):
    """跑一支量測腳本，回傳 (成功與否, 輸出字串)。"""
    path = SCRIPTS / name
    if not path.exists():
        return False, f"找不到腳本：{path}"
    try:
        proc = subprocess.run(
            [sys.executable, str(path), *args],
            capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, f"{name} 執行超過 600 秒，已中止"
    except OSError as exc:
        return False, f"{name} 無法執行：{exc}"
    output = proc.stdout.strip()
    if proc.returncode != 0:
        return False, f"{name} 結束碼 {proc.returncode}\n{proc.stderr.strip()}"
    return True, output or "（無輸出）"


def corpus_files(directory):
    """目錄下所有會被量測的 .md（與腳本一致，略過 _meta）。"""
    if not directory.is_dir():
        return ()
    return tuple(sorted(
        f for f in directory.rglob("*.md")
        if META_DIR not in f.relative_to(directory).parts
    ))


def human_groups(root):
    base = root / HUMAN_DIR
    if not base.is_dir():
        return ()
    return tuple(sorted(d for d in base.iterdir() if d.is_dir() and d.name != META_DIR))


def han_count(files):
    total = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        total += sum(1 for ch in text if "一" <= ch <= "鿿")
    return total


def opencc_state():
    try:
        import opencc  # noqa: F401
    except ImportError:
        return "未安裝（簡體語料會漏抓，繁體語料不受影響）"
    return "已安裝，輸入會先正規化為台灣繁體"


def inspect(root):
    """盤點語料，回傳一份不可變的檢查結果。"""
    groups = human_groups(root)
    human_files = tuple(f for g in groups for f in corpus_files(g))
    ai_files = corpus_files(root / AI_DIR)
    problems = []
    if not groups:
        problems.append(f"{root / HUMAN_DIR} 底下沒有任何來源子目錄")
    elif len(groups) < MIN_HUMAN_GROUPS:
        problems.append(f"人類側只有 {len(groups)} 組，至少要 {MIN_HUMAN_GROUPS} 組才算得出組間穩定性")
    if not human_files:
        problems.append("人類側沒有 .md 檔")
    if not ai_files:
        problems.append(f"{root / AI_DIR} 底下沒有 .md 檔")
    return {
        "groups": groups,
        "human_files": human_files,
        "ai_files": ai_files,
        "human_han": han_count(human_files),
        "ai_han": han_count(ai_files),
        "problems": tuple(problems),
    }


def scale_note(state):
    total_wan = (state["human_han"] + state["ai_han"]) / 10000
    ref = REFERENCE_SCALE["總漢字數（萬）"]
    if total_wan >= ref:
        return f"規模與原研究相當（{total_wan:.1f} 萬字 vs {ref} 萬字）"
    return (f"規模小於原研究（{total_wan:.1f} 萬字 vs {ref} 萬字），"
            "低頻規則的數字會不穩，判讀時以方向為主、不要直接取代原倍率")


def build_report(root, state, results):
    lines = [
        f"# 台灣語料重測報告　{datetime.now():%Y-%m-%d %H:%M}",
        "",
        "## 語料",
        "",
        f"- 語料目錄：`{root}`",
        f"- 人類側：{len(state['groups'])} 組、{len(state['human_files'])} 篇、"
        f"{state['human_han']/10000:.1f} 萬漢字",
        f"- AI 側：{len(state['ai_files'])} 篇、{state['ai_han']/10000:.1f} 萬漢字",
        f"- opencc：{opencc_state()}",
        f"- 規模對照：{scale_note(state)}",
        "",
        "## 量測結果",
        "",
    ]
    for title, ok, output in results:
        lines += [f"### {title}", "", "```", output, "```", ""]
    lines += [
        "## 判讀提醒",
        "",
        "- 倍率 = 人類頻率 / AI 頻率，<1 表示 AI 用得更多。",
        "- 標成「波動大」的規則代表組間差異大，先確認是不是體裁造成的，再談規則。",
        "- 與 RESEARCH.md 的數字不一致時，先查話題與文體是否對齊、分母是否與被測單位匹配。",
        "",
    ]
    return "\n".join(lines)


def init_corpus(root):
    for sub in (f"{HUMAN_DIR}/來源一", f"{HUMAN_DIR}/來源二", AI_DIR, META_DIR):
        (root / sub).mkdir(parents=True, exist_ok=True)
    readme = root / META_DIR / "README.md"
    if readme.exists():
        print(f"已存在，未覆寫：{readme}")
    else:
        readme.write_text(META_README, encoding="utf-8")
    print(f"語料骨架建好了：{root}")
    print(f"放法見 {readme}")
    return 0


def measure(root, out_path):
    state = inspect(root)
    if state["problems"]:
        print("語料還不完整：")
        for p in state["problems"]:
            print(f"  - {p}")
        print(f"\n目錄規範見 {root / META_DIR / 'README.md'}，或先跑 --init 建骨架。")
        return 1

    human_args = [str(g) for g in state["groups"]]
    ai_arg = str(root / AI_DIR)
    jobs = (
        ("句層：各特徵在兩側語料的頻率與比值", "compare-human-ai.py",
         ["--human", *human_args, "--ai", ai_arg]),
        ("段落層：相鄰句同構、段首零回指", "check-structure.py",
         ["--human", *human_args, "--ai", ai_arg]),
        ("生成側：譯文句式頻率", "check-translationese.py", [ai_arg]),
    )
    results = []
    failed = False
    for title, script, args in jobs:
        print(f"跑 {script} …")
        ok, output = run_script(script, args)
        failed = failed or not ok
        results.append((title, ok, output))
        if not ok:
            print(f"  失敗：{output.splitlines()[0] if output else '未知錯誤'}")

    report = build_report(root, state, tuple(results))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n報告：{out_path}")
    print(scale_note(state))
    return 1 if failed else 0


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="用台灣語料重跑三支量測腳本並產出報告",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("corpus", help="語料目錄")
    parser.add_argument("--init", action="store_true", help="只建立目錄骨架與說明，不量測")
    parser.add_argument("--out", help="報告輸出路徑，預設 <語料目錄>/_meta/rerun-<時間>.md")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    root = Path(args.corpus).expanduser()
    if args.init:
        root.mkdir(parents=True, exist_ok=True)
        return init_corpus(root)
    if not root.is_dir():
        print(f"找不到語料目錄：{root}\n先跑：python3 scripts/rerun-tw.py {args.corpus} --init")
        return 1
    default_out = root / META_DIR / f"rerun-{datetime.now():%Y%m%d-%H%M}.md"
    out_path = Path(args.out).expanduser() if args.out else default_out
    return measure(root, out_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
