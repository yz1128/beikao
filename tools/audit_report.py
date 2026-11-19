"""把 data/_audit.json 汇总成可读报告 data/审核报告.md。"""
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DK = os.path.join(ROOT, "data")


def j(name, default):
    p = os.path.join(DK, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


decks = j("decks.json", {"decks": []})
explain = j("explanations.json", {})
audit = j("_audit.json", {})

meta = {}
for deck in decks["decks"]:
    for c in deck["cards"]:
        meta[c["id"]] = (deck["id"], c)

ORDER = {"不是": 0, "wrong": 0, "off": 1, "unsure": 2}
rows = []
for cid, v in audit.items():
    deck_id, card = meta.get(cid, ("?", {}))
    v2 = v.get("recheck") or {}
    ans = v["answer"]
    exp = v["explain"]
    # 两轮都异常才算问题，第二轮能洗白的降级为待确认
    if v2:
        if v2.get("answer") == "ok" and ans != "ok":
            ans = "unsure"
        if v2.get("explain") in ("ok", "none") and exp not in ("ok", "none"):
            exp = "unsure"
    bad = []
    if ans == "wrong":
        bad.append("答案错")
    elif ans == "unsure":
        bad.append("答案待核")
    if exp == "off":
        bad.append("解析串题")
    elif exp == "wrong":
        bad.append("解析错")
    elif exp == "unsure":
        bad.append("解析待核")
    if bad:
        rows.append((ORDER.get(ans, 3), deck_id, cid, card, v, "、".join(bad)))

rows.sort(key=lambda r: (r[0], r[1], r[2]))
kinds = Counter(r[5] for r in rows)

L = []
L.append("# 题库审核报告")
L.append("")
L.append(f"- 已审 {len(audit)} 题，检出异常 {len(rows)} 题")
L.append(f"- 分布：{dict(kinds)}")
L.append(f"- 判定模型：wbm/hy4flash-free；异常项经反序重审，两轮一致才计入")
L.append("")
cur = None
for _, deck_id, cid, card, v, bad in rows:
    if deck_id != cur:
        L.append(f"## {deck_id}")
        cur = deck_id
    L.append(f'### {cid} ｜ {bad}')
    L.append(f'- 题干：{card.get("q")}')
    for o in card.get("options") or []:
        L.append(f'  - {o["k"]}. {o["t"]}')
    a = card.get("answer")
    if card.get("kind") == "judge":
        a = "正确(T)" if a == "T" else "错误(F)"
    L.append(f"- 当前答案：{a}")
    L.append(f'- 当前解析：{explain.get(cid) or card.get("explain") or "（无）"}')
    L.append(f'- 模型判定：答案 {v["answer"]} / 解析 {v["explain"]} ｜ {v["n"]}')
    r2 = v.get("recheck")
    if r2:
        L.append(f'- 重审：答案 {r2["answer"]} / 解析 {r2["explain"]} ｜ {r2["n"]}')
    L.append("")

out = os.path.join(DK, "审核报告.md")
open(out, "w", encoding="utf-8").write("\n".join(L))
print(f"{len(audit)} 题已审，异常 {len(rows)} 题 -> {out}")
print(dict(kinds))
