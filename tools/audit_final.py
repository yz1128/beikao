"""合并两模型判定，生成最终审核报告 data/审核报告.md。"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DK = os.path.join(ROOT, "data")


def j(n, d):
    p = os.path.join(DK, n)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


decks = j("decks.json", {"decks": []})
explain = j("explanations.json", {})
a1 = j("_audit.json", {})
a2 = j("_audit_recheck2.json", {})

meta, deck_of = {}, {}
for deck in decks["decks"]:
    for c in deck["cards"]:
        meta[c["id"]] = c
        deck_of[c["id"]] = deck["id"]

rows = []
for cid, v in a1.items():
    r1 = v.get("recheck") or {}
    if r1.get("answer") == "ok" and r1.get("explain") in ("ok", "none"):
        continue  # 第一轮报异常、重审洗白 → 噪声
    if v["answer"] == "ok" and v["explain"] in ("ok", "none"):
        continue
    rows.append({
        "id": cid,
        "deck": deck_of.get(cid, "?"),
        "card": meta.get(cid, {}),
        "exp": explain.get(cid) or meta.get(cid, {}).get("explain") or "",
        "m1": v, "m2": a2.get(cid) or {},
    })

A, B, C = [], [], []
for r in rows:
    m1, m2 = r["m1"], r["m2"]
    ans_bad_1, ans_bad_2 = m1["answer"] == "wrong", m2.get("answer") == "wrong"
    exp_bad_1 = m1["explain"] in ("off", "wrong")
    exp_bad_2 = m2.get("explain") in ("off", "wrong")
    if ans_bad_1 and ans_bad_2:
        A.append(r)
    elif ans_bad_1 or ans_bad_2:
        B.append(r)
    if exp_bad_1 or exp_bad_2:
        C.append(r)

exclude = {r["id"] for r in A} | {r["id"] for r in B}
C = [r for r in C if r["id"] not in exclude]

with_exp = sum(1 for cid in a1 if explain.get(cid) or meta.get(cid, {}).get("explain"))


def ans_text(card):
    a = card.get("answer")
    return ("正确(T)" if a == "T" else "错误(F)") if card.get("kind") == "judge" else a


L = ["# 题库审核报告", ""]
L.append(f"- 审核范围：{len(a1)} 道客观题（单选/多选/判断/填空式选择），其中有解析 {with_exp} 道")
L.append("- 初判模型：`wbm/hy4flash-free`（8 路并发，异常项反序重审）")
L.append("- 复核模型：`wbm/deepseek-v4.1-flash`（独立第二意见）")
L.append(f"- 结论：答案错误 **{len(A)}** 题，答案存疑 **{len(B)}** 题，解析需重写 **{len(C)}** 题")
L.append("")

L.append("## A. 答案错误（两模型一致）")
L.append("")
for r in A:
    c, m1, m2 = r["card"], r["m1"], r["m2"]
    L.append(f'**{r["id"]}**（{r["deck"]}）{c.get("q")}')
    for o in c.get("options") or []:
        L.append(f'- {o["k"]}. {o["t"]}')
    L.append(f'- 现答案：`{ans_text(c)}` → 应为：{m2.get("n") or m1.get("n")}')
    L.append("")

L.append("## B. 答案存疑（两模型分歧，需人工定夺）")
L.append("")
for r in B:
    c, m1, m2 = r["card"], r["m1"], r["m2"]
    L.append(f'**{r["id"]}**（{r["deck"]}）{c.get("q")}')
    for o in c.get("options") or []:
        L.append(f'- {o["k"]}. {o["t"]}')
    L.append(f'- 现答案：`{ans_text(c)}`')
    L.append(f'- hy4flash-free：{m1["answer"]}（{m1["n"]}）')
    if m2:
        L.append(f'- deepseek：{m2.get("answer")}（{m2.get("n")}）')
    L.append("")

L.append("## C. 解析需重写（串题 / 空泛 / 与答案矛盾）")
L.append("")
for r in C:
    c, m1, m2 = r["card"], r["m1"], r["m2"]
    L.append(f'**{r["id"]}**（{r["deck"]}）{c.get("q")}')
    L.append(f'- 现答案：`{ans_text(c)}`')
    L.append(f'- 现解析：{r["exp"] or "（无）"}')
    L.append(f'- 问题：{(m2 or {}).get("n") or m1.get("n") or "解析未解释本题"}')
    L.append("")

open(os.path.join(DK, "审核报告.md"), "w", encoding="utf-8").write("\n".join(L))
print(json.dumps({"audited": len(a1), "with_explain": with_exp,
                  "A": [r["id"] for r in A], "B": [r["id"] for r in B], "C": [r["id"] for r in C]},
                 ensure_ascii=False, indent=1))
