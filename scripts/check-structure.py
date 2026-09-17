"""段落級結構特徵對比：相鄰句結構同款、段首零主語評論。

用法：
    python3 scripts/check-structure.py --human <目錄...> --ai <目錄...>

為什麼單獨一個腳本：這兩項的分母是段數，不是字數。
用「每千字」會被結構差異帶偏——AI 平均每篇 10 個小標題、人類 1-2 個，
按字數算問句小標題會虛高 30 倍，換成佔小標題比例後差異消失。
涉及結構元素的指標，分母必須是同類元素的總數。
"""
import re
import sys
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

# 段首評論語：省掉回指成分時讀者要翻回上一段
COMMENT = re.compile(
    r"^(?:聽起來|看起來|看上去|聽上去|說白了|講白了|說到底|換句話說|意味著|值得注意|"
    r"不難看出|細看|再看|回過頭看|問題在於|原因在於|結果是|有意思的是|"
    r"更重要的是|關鍵在於|真正的)"
)
# 回指成分：把上文接回來
ANAPHOR = re.compile(r"^(?:這|那|其|此|上面|前面|剛才|以上|該|它|他|她|它們|他們|同樣|類似|相比|反過來|但|不過|所以|因此|於是|而|另|除此|與此)")
# 比喻起段（對照項，實測人類更多）
METAPHOR = re.compile(r"^(?:像|就像|好比|好像|彷彿|如同|這就像)")


def paragraphs(text):
    out = []
    for p in text.split("\n"):
        p = p.strip()
        if len(p) < 8 or p.startswith(("#", "|", "```", ">", "- ", "* ", "!", "[")):
            continue
        out.append(p)
    return out


def signature(sent):
    """句子結構指紋：逗號數、有無冒號、有無括號、長度檔"""
    return (sent.count("，"), "：" in sent, ("（" in sent or "(" in sent), len(sent) // 15)


def isomorphic(para, n):
    """段內是否有連續 n 句結構指紋相同"""
    sents = [s.strip() for s in re.split(r"[。！？]", para) if len(s.strip()) > 10]
    hits = 0
    for i in range(len(sents) - n + 1):
        sigs = [signature(s) for s in sents[i:i + n]]
        if all(s == sigs[0] for s in sigs) and sigs[0][0] >= 1:
            hits += 1
    return hits


def measure(texts):
    total = iso2 = iso3 = zero = meta = nonfirst = 0
    for t in texts:
        ps = paragraphs(t)
        total += len(ps)
        for i, p in enumerate(ps):
            iso2 += isomorphic(p, 2)
            iso3 += isomorphic(p, 3)
            if METAPHOR.match(p):
                meta += 1
            if i == 0:
                continue
            nonfirst += 1
            if COMMENT.match(p) and not ANAPHOR.match(p):
                zero += 1
    return {
        "段數": total,
        "連續兩句同構/百段": iso2 / total * 100 if total else 0,
        "連續三句同構/百段": iso3 / total * 100 if total else 0,
        "段首零主語評論/非首段%": zero / nonfirst * 100 if nonfirst else 0,
        "比喻起段/百段(對照)": meta / total * 100 if total else 0,
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


def main():
    human, ai, cur = [], [], None
    for a in sys.argv[1:]:
        if a == "--human":
            cur = human
        elif a == "--ai":
            cur = ai
        elif cur is not None:
            cur.append(a)
    if not human or not ai:
        print(__doc__)
        return

    groups = []
    for d in human:
        ts = load([d])
        if ts:
            groups.append((f"g{len(groups) + 1}", measure(ts)))
    hm = measure([t for d in human for t in load([d])])
    am = measure(load(ai))

    keys = [k for k in am if k != "段數"]
    print(f"AI {am['段數']} 段，人類 {hm['段數']} 段\n")
    head = f"{'指標':<26}{'AI':>8}{'人類':>8}{'倍率':>7}{'穩定性':>8}"
    print(head)
    print("-" * len(head))
    for k in keys:
        a, h = am[k], hm[k]
        r = a / h if h > 0.001 else float("inf")
        # 各組數值只用來算穩定性，不打印
        vals = [m[k] for _, m in groups]
        spread = max(vals) / max(min(vals), 0.01)
        print(f"{k:<26}{a:>8.2f}{h:>8.2f}{r:>6.2f}×{'穩定' if spread <= 5 else '波動大':>8}")


if __name__ == "__main__":
    main()
