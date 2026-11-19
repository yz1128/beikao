"""导出供 ChatGPT 独立复核的题面：18 条异常项 + 30 条均匀抽样（假阴性检查）。"""
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

meta = {}
for deck in decks["decks"]:
    for c in deck["cards"]:
        meta[c["id"]] = c

RUBRIC = """你是政治理论课（新时代中国特色社会主义 / 自然辩证法）题库的独立审校员。
对每题判断两件事：
1. answer：按教材与中央文件通行表述，当前答案是否正确 → ok / wrong / unsure；wrong 时在 fix 里写正确答案。
2. explain：解析是否与答案自洽、是否真的在解释本题 → ok / off（属于别的题、纯背诵清单未解释本题）/ wrong（自身说错或与答案矛盾）/ none。
不要因为答案来自原题库就默认它对，就题论题。判不准给 unsure。

输出：每题一行 JSON，不要代码块、不要解释其他内容：
{"id":"zt-003","answer":"ok","explain":"ok","fix":"","why":"≤30字"}
"""


def block(c, note=""):
    a = c.get("answer")
    if c.get("kind") == "judge":
        a = "正确(T)" if a == "T" else "错误(F)"
    lines = [f'### {c["id"]}（{c.get("kind")}）']
    lines.append(f'题干：{c.get("q")}')
    if c.get("options"):
        lines.append("\n".join(f'- {o["k"]}. {o["t"]}' for o in c["options"]))
    lines.append(f'当前答案：{a}')
    lines.append(f'当前解析：{explain.get(c["id"]) or "（无）"}')
    if note:
        lines.append(f'备注：{note}')
    return "\n".join(lines)


# 1) 异常项
flagged = []
for cid, v in a1.items():
    r1 = v.get("recheck") or {}
    if r1.get("answer") == "ok" and r1.get("explain") in ("ok", "none"):
        continue
    if v["answer"] == "ok" and v["explain"] in ("ok", "none"):
        continue
    note = f'本地初审：答案 {v["answer"]} / 解析 {v["explain"]}｜{v["n"]}'
    if a2.get(cid):
        note += f'；复核模型：答案 {a2[cid].get("answer")}｜{a2[cid].get("n")}'
    flagged.append((cid, note))

# 2) 抽样：判为 ok 的按 id 排序均匀取 30 条
ok_ids = sorted(cid for cid, v in a1.items()
                if v["answer"] == "ok" and v["explain"] in ("ok", "none")
                and not ((v.get("recheck") or {}).get("answer") not in (None, "ok")))
if len(ok_ids) > 30:
    step = len(ok_ids) / 30
    ok_ids = [ok_ids[int(i * step)] for i in range(30)]

b1 = [RUBRIC, "## 待复核：本地已标记为可能有问题（共 %d 题）" % len(flagged), ""]
for cid, note in flagged:
    b1.append(block(meta[cid], note))
    b1.append("")

b2 = [RUBRIC, "## 待复核：本地判为正常、抽取复查（共 %d 题，请重点找漏判）" % len(ok_ids), ""]
for cid in ok_ids:
    b2.append(block(meta[cid]))
    b2.append("")

open(os.path.join(DK, "chatgpt_复核_异常项.md"), "w", encoding="utf-8").write("\n".join(b1))
open(os.path.join(DK, "chatgpt_复核_抽样.md"), "w", encoding="utf-8").write("\n".join(b2))
print(f"异常项 {len(flagged)} 题、抽样 {len(ok_ids)} 题已导出")
