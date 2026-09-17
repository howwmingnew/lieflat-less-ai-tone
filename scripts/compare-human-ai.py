"""人類語料 vs AI 語料的規則命中率對比報告。

用法：
    python3 scripts/compare-human-ai.py --human <目錄> [更多] --ai <目錄> [更多]

為什麼要這個腳本：SKILL.md 裡的「區分力 ×N」都來自一批已不可用的舊測量，
且切句邏輯有缺陷。本腳本用統一的測量方式同時跑人類側和 AI 側，
讓每條規則的倍率可復現。倍率 = 人類頻率 / AI 頻率（<1 表示 AI 用得更多）。
"""
import re
import sys
import collections
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

# 每條對應 SKILL.md 的一條規則，正則儘量貼規則的觸發標記
RULES = {
    "2 翻案腔": r"(?:不是|並非|不在於)[^，。！？\n]{1,20}[，]?(?:而是|而在於)",
    # 原正則禁空格與字母，漏掉「用哪個模型、Team Skill 開關、定時任務」這類並列
    "3 頓號羅列過密": r"[^，。！？；：、\n]{1,14}、[^，。！？；：、\n]{1,14}、[^，。！？；：、\n]{1,14}",
    # 句內同構排比已移出規則：實測人類用得不比 AI 少，保留測量供複查
    "(已刪)句內同構-更X": r"更[一-鿿]{1,3}[、，][^，。\n]{0,8}更[一-鿿]{1,3}",
    "(已刪)句內同構-同字兩項": r"([一-鿿]{1,2})[^，。、\n]{2,12}[、，]\1[^，。、\n]{2,12}",
    # 問句相關的規則已從 SKILL.md 刪除，此處不再統計。三輪測量結論都不穩定：
    #   問號總量 —— 人類看似多 2.5 倍，但由個別組貢獻，組間不一致
    #   自問自答 —— 倍率 1.03，寬正則還會誤抓「？這是另一個問題」這類新起句
    #   小標題問句 —— 每千字 32 倍，換成佔小標題比例後 AI 2.7% / 人類最高 3.6%，無差異
    # 教訓：涉及結構元素的指標，先確認分母可比。
    "4 破折號": r"——",
    # 只匹配提示語+冒號（引出總結/結論/原因/定義），不匹配對話、標題、列表和普通句中冒號
    "5 提示性冒號": (r"(?:一句話(?:總結|說|概括)|簡單說|簡單來說|說白了|講白了|總結|小結|結論|核心(?:是|在於|觀點)?"
                    r"|關鍵(?:是|在於)?|重點(?:是)?|原因(?:如下|有|在於)?|問題(?:是|在於)?"
                    r"|答案(?:是)?|本質(?:是|上)?|定義(?:是)?|具體(?:來說|如下|包括)?"
                    r"|舉例(?:來說)?|換句話說|也就是說|我的(?:觀點|判斷|結論)|建議(?:是)?)[：:]"),
    "6 序數詞當小標題": r"(?:^|\n)\s*(?:首先|其次|再次|最後|第一|第二|第三|一方面|另一方面)[，、]",
    "(已刪)就字": r"就",
    "(已刪)很字": r"很",
    "(已刪)了字": r"了",
    "(已刪)口語連接詞": r"但是|其實|不過|就是",
    "9 動詞名詞化": r"(?:完成|實現|進行|開展)了?(?:對)?[^，。\n]{0,10}的(?:優化|提升|調整|分析|改造|升級)",
    "11 過長前置定語": r"(?:一個|一種|一套|這種|這個)[^，。、；：！？\n]{15,}的[一-鿿]{2,5}",
    "11 當…時": r"當[^，。\n]{2,20}(?<!的時候)時，",
    "11 前置話題殼": r"(?:對於?[^，。\n]{2,15}來說|對[^，。\n]{2,15}而言|就[^，。\n]{2,15}而言|在[^，。\n]{2,12}方面)",
    "11 句首連接詞": r"(?:^|\n)\s*(?:然而|因此|此外|與此同時|換言之|總而言之)[，、]",
    "11 這意味著": r"(?:這意味著|這表明|這說明|換句話說)",
}


def load(dirs):
    out = []
    for d in dirs:
        for f in Path(d).rglob("*.md"):
            if f.parent.name == "_meta":
                continue
            try:
                out.append(normalize(f.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                continue
    return out


def measure(texts):
    joined = "\n".join(texts)
    k = len(re.findall(r"[一-鿿]", joined)) / 1000
    hits = {}
    for name, pat in RULES.items():
        rx = re.compile(pat)
        n = len(rx.findall(joined))
        docs = sum(1 for t in texts if rx.search(t))
        hits[name] = (n / k if k else 0, n, docs)
    return hits, k, len(texts)


def parse_args(argv):
    human, ai, cur = [], [], None
    for a in argv:
        if a == "--human":
            cur = human
        elif a == "--ai":
            cur = ai
        elif cur is not None:
            cur.append(a)
    return human, ai


def main():
    hd, ad = parse_args(sys.argv[1:])
    if not hd or not ad:
        print(__doc__)
        return

    # 每個人類目錄單獨測，用於判斷差異在語料內部是否穩定（不輸出各組明細）
    per_author = {}
    for d in hd:
        texts = load([d])
        if texts:
            # 不拿目錄名當標籤，也不輸出各組數值：語料目錄常帶來源信息，
            # 逐組列出等於公開語料構成。只用來算穩定性。
            per_author[f"g{len(per_author) + 1}"] = measure(texts)
    ha = load(ad)
    if not per_author or not ha:
        print(f"語料為空：human={len(per_author)} 組, ai={len(ha)} 篇")
        return

    all_human = [t for d in hd for t in load([d])]
    hh, hk, hn = measure(all_human)
    ah, ak, an = measure(ha)

    names = list(per_author)
    print(f"人類語料：{hn} 篇，{hk/10:.1f} 萬漢字")
    print(f"AI 語料：{an} 篇，{ak/10:.1f} 萬漢字\n")

    head = f"{'規則':<18}{'人類':>8}{'AI':>7}{'倍率':>8}{'穩定性':>8}  判讀"
    print(head)
    print("-" * (len(head) + 6))

    rows = []
    for name in RULES:
        h, a = hh[name][0], ah[name][0]
        ratio = h / a if a > 0.001 else float("inf")
        rows.append((ratio, name, h, a))

    for ratio, name, h, a in sorted(rows, key=lambda r: r[0]):
        disp = f"{ratio:>7.2f}" if ratio != float("inf") else "      ∞"
        # 各組數值只用來算穩定性，不打印——逐組列出等於公開語料構成
        vals = [per_author[n][0][name][0] for n in names]
        spread = max(vals) / max(min(vals), 0.01)
        stable = "穩定" if spread <= 5 else "波動大"
        if ratio < 0.5:
            verdict = "AI 明顯更多 → 值得改"
        elif ratio < 0.8:
            verdict = "AI 略多"
        elif ratio <= 1.25:
            verdict = "無差異 → 不該作為規則"
        elif ratio <= 3:
            verdict = "人類更多"
        else:
            verdict = "人類明顯更多 → 方向是補"
        if spread > 5 and ratio > 1.25:
            verdict += "（語料內部差異大，疑體裁）"
        print(f"{name:<18}{h:>8.2f}{a:>7.2f}{disp}{stable:>8}  {verdict}")


if __name__ == "__main__":
    main()
