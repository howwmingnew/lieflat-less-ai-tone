"""統計翻譯腔標記在 AI 語料中的出現頻率（每千漢字）。

用法：
    python3 scripts/check-translationese.py <語料目錄> [更多目錄...]

人類語料若不在本機，只能給出 AI 側絕對頻率：
某標記在 AI 文本裡都極少出現時，它不可能是 AI 味的判別特徵。
BASELINE 是研究已確認有區分力的規則，用同一腳本同一語料測量，作為收錄門檻。
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

# 輸入正規化：有安裝 opencc 時，先把簡體轉成台灣繁體字形，簡體語料也能直接套繁體 regex。
# 用 s2tw（字元層級）而非 s2twp（詞彙替換），避免「数据→資料」這類換詞影響命中數。
try:
    import opencc as _opencc
    try:
        _CC = _opencc.OpenCC("s2tw")
    except Exception:
        _CC = _opencc.OpenCC("s2tw.json")
    def normalize(text):
        return _CC.convert(text)
except ImportError:
    def normalize(text):
        # 沒裝 opencc 就原樣回傳；簡體語料會漏抓，請 pip install opencc
        return text

MARKERS = {
    "被動-抽象": r"被(認為|視為|稱為|設計為|應用於|賦予|看作)",
    "受到…的": r"受到[^，。]{0,12}的(關注|影響|重視|挑戰)",
    "形式主語": r"(值得注意的是|有必要指出的是|可以說的是|需要指出的是)",
    "存在著/有著": r"(存在著|有著)",
    "當…的時候": r"當[^，。]{2,20}(的時候|時)，",
    "在…的過程中": r"在[^，。]{2,20}(的過程中|的情況下)",
    "如果…的話": r"如果[^，。]{2,20}的話",
    "並列連詞密集": r"並且|而且",
    "輕動詞": r"(進行|作出|給予|予以)了?[^，。]{0,6}(分析|調整|優化|支持|評估|檢查|討論)",
    "不僅僅是": r"(不僅僅是|遠不止是|不過是|無非是)",
    "正是/恰恰是": r"(正是|恰恰是)",
    "複數硬譯": r"(一系列的|各種各樣的|諸多)",
    "程度直譯": r"(在某種程度上|一定程度上|從某種意義上說|在很大程度上|相對而言)",
    "句首連接詞": r"(?:^|\n)\s*(然而|因此|此外|與此同時|換言之|總而言之)[，、]",
    "這意味著": r"(這意味著|這表明|這說明|換句話說)",
    "前置話題殼": r"(對於?[^，。]{2,15}來說|對[^，。]{2,15}而言|就[^，。]{2,15}而言|在[^，。]{2,12}方面)",
    "扮演角色": r"(扮演|承擔)了?[^，。]{0,8}角色",
    "以一種…方式": r"以一種[^，。]{2,12}的(方式|形式)",
    "使得…能夠": r"使得?[^，。]{0,12}(能夠|可以)",
    "長前置定語": r"(?:一個|一種|一套|這種|這個)[^，。、；：！？\n]{15,}的[一-鿿]{2,5}",
    "的…的…的連用": r"的[^，。]{1,8}的[^，。]{1,8}的",
}

# 對照基準：研究已確認有區分力的規則，同一腳本同一語料
BASELINE = {
    "[基準]段首序數詞": r"(?:^|\n)\s*(首先|其次|再次|最後|第一|第二|第三|一方面|另一方面)",
    "[基準]不是…而是": r"(不是|並非)[^，。]{1,20}(，|)而是",
    "[基準]破折號": r"——",
    # 只匹配提示語+冒號；寬正則（任意漢字+冒號）會把標題、列表、對話一併算進來
    "[基準]提示性冒號": (r"(?:一句話(?:總結|說|概括)|簡單說|簡單來說|說白了|講白了|總結|小結|結論|核心(?:是|在於|觀點)?"
                       r"|關鍵(?:是|在於)?|重點(?:是)?|原因(?:如下|有|在於)?|問題(?:是|在於)?"
                       r"|答案(?:是)?|本質(?:是|上)?|定義(?:是)?|具體(?:來說|如下|包括)?"
                       r"|舉例(?:來說)?|換句話說|也就是說|我的(?:觀點|判斷|結論)|建議(?:是)?)[：:]"),
}


def model_of(path):
    return re.sub(r"-T\d.*", "", Path(path).stem)


def main():
    dirs = sys.argv[1:]
    if not dirs:
        print(__doc__)
        return
    files = [f for d in dirs for f in Path(d).rglob("*.md") if f.parent.name != "_meta"]
    if not files:
        print(f"找不到語料：{dirs}")
        return

    texts = {f: normalize(f.read_text(encoding="utf-8")) for f in files}
    joined = "\n".join(texts.values())
    kchars = len(re.findall(r"[一-鿿]", joined)) / 1000
    models = sorted({model_of(f) for f in files})
    print(f"語料 {len(files)} 篇，{kchars/10:.1f} 萬漢字，模型 {len(models)} 個：{', '.join(models)}\n")

    # 每模型漢字數，用於分模型頻率
    mk = defaultdict(float)
    for f, t in texts.items():
        mk[model_of(f)] += len(re.findall(r"[一-鿿]", t)) / 1000

    rows = []
    for name, pat in {**MARKERS, **BASELINE}.items():
        rx = re.compile(pat)
        total = len(rx.findall(joined))
        docs = sum(1 for t in texts.values() if rx.search(t))
        per_model = {m: len(rx.findall("\n".join(t for f, t in texts.items() if model_of(f) == m))) / mk[m]
                     for m in models}
        rows.append((total / kchars, total, docs, name, per_model))
    rows.sort(reverse=True)

    head = f"{'標記':<16}{'每千字':>8}{'總數':>7}{'覆蓋':>10}  " + "".join(f"{m[:11]:>12}" for m in models)
    print(head)
    print("-" * len(head))
    for per_k, total, docs, name, pm in rows:
        cov = f"{docs}/{len(files)}"
        line = f"{name:<16}{per_k:>8.2f}{total:>7}{cov:>10}  " + "".join(f"{pm[m]:>12.2f}" for m in models)
        print(line)


if __name__ == "__main__":
    main()
