"""为修订项生成新解析与新答案文本（wbm/deepseek-v4.1-flash，并发 4）。

输入：审核定稿的修订清单（写死在 ANSWERS）；
输出：data/_fix_apply.json，供 tools/apply_fix.py 应用。
"""
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DK = os.path.join(ROOT, "data")
ENDPOINT = "http://127.0.0.1:3425/v1/chat/completions"
MODEL = "wbm/deepseek-v4.1-flash"

# id: (新答案 或 None=不改, 是否重写解析)
PLAN = {
    "zt-063": ("BCD", True),
    "zt-202": ("F", True),
    "zt-283": ("F", True),
    "zt-295": ("F", True),
    "zt-409": ("B", True),
    "zt-411": ("BCD", True),
    "zt-414": ("BCD", True),
    "zt-422": ("CD", True),
    "zrb-pd-30": ("T", True),
    "zrb-x900": ("量子力学昭示的是概率性的因果观与统计性的规律观：在相同制备条件下，单次测量结果一般不能唯一确定，但各结果的概率分布遵循确定规律。", True),
    "zrb-x902": ("自然辩证法研究自然界和科学技术发展的一般规律、人类认识和改造自然的一般方法，以及科学技术与社会的关系；它是马克思主义哲学的重要组成部分，是具有哲学性质的交叉学科。", True),
    "zt-037": (None, True),
    "zt-109": (None, True),
    "zrb-pd-02": (None, True),
}

decks = json.load(open(os.path.join(DK, "decks.json"), encoding="utf-8"))
meta = {}
for deck in decks["decks"]:
    for c in deck["cards"]:
        meta[c["id"]] = c

PROMPT = """你在修订一门政治理论课题库的解析。题目、选项、**已经确定正确的答案**见下。请写一条新解析。

硬性要求：
- 与给定答案严格一致，不要质疑答案。
- 单选题：点明正确项依据，并指出最易误选的干扰项错在哪。
- 多选题：说明入选项为什么属于该范畴；未被选中的选项说明它为什么不属于（客观争议项只写关键区别）。
- 判断题：指出题干对在何处，或错在哪个词/哪个表述。
- 简答题（题型 qa/choice 且无选项）：直接给出完整参考答案要点，分号分隔，不超过 150 字，不要写"建议记忆"之类的话。
- 不复述题干，不写"本题表述正确""记住即可"这类空话，不编造文件名、会议届次、原文条文。
- 单条 ≤100 字（简答除外），中文，直接输出解析正文，不要任何前缀或标题。

题目信息：
{body}
"""


def body(card, ans):
    lines = [f'题型：{card.get("kind")}', f'题干：{card.get("q")}']
    if card.get("options"):
        lines.append("选项：\n" + "\n".join(f'{o["k"]}. {o["t"]}' for o in card["options"]))
    if card.get("kind") == "judge":
        lines.append("正确答案：" + ("正确(T)" if ans == "T" else "错误(F)"))
    else:
        lines.append(f"正确答案：{ans}")
    lines.append(f'原解析（仅供参考，可能错误）：{card.get("explain") or "（无）"}')
    return "\n".join(lines)


def gen(item):
    cid, (new_ans, _) = item
    card = meta[cid]
    ans = new_ans if new_ans is not None else card.get("answer")
    prompt = PROMPT.format(body=body(card, ans))
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": 1200, "temperature": 0.3}, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        txt = json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()
    txt = txt.strip().strip("“”\"'").replace("\n", " ")
    return cid, {"answer": new_ans, "explain": txt, "kind": "qa" if cid == "zrb-xz-03" else None}


out = {}
with ThreadPoolExecutor(max_workers=4) as pool:
    for cid, res in pool.map(gen, PLAN.items()):
        out[cid] = {k: v for k, v in res.items() if v is not None}
        print(f"{cid}: {len(res['explain'])} 字")

# 数据缺陷：选择题缺选项 → 按问答卡渲染
out.setdefault("zrb-xz-03", {})["kind"] = "qa"
out["zrb-xz-03"]["explain"] = "微分的哲学意义在于零与非零的统一：它趋于零，却在运算中保持非零的有效性，因而成为不同物质层次之间质变的关节点。"

json.dump(out, open(os.path.join(DK, "_fix_apply.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("已写 data/_fix_apply.json")
