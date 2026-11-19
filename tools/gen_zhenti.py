"""给「历年真题·选择题」16 题生成解析，并用独立模型复核答案。

模型：wbm/deepseek-v4.1-flash
输出：写回 decks.json 的 explain 字段 + data/explanations.json，审核结果落 data/_zhenti_check.json
"""
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DK = os.path.join(ROOT, "data")
ENDPOINT = "http://127.0.0.1:3425/v1/chat/completions"
MODEL = "wbm/deepseek-v4.1-flash"

decks = json.load(open(os.path.join(DK, "decks.json"), encoding="utf-8"))
cards = []
for deck in decks["decks"]:
    if deck["id"] == "zrb-zhenti":
        cards = deck["cards"]
print(f"真题卡 {len(cards)} 张")

EXPLAIN_PROMPT = """你在为一门政治理论课（自然辩证法）的真题写解析。答案已确定，不要质疑，也不要改动。

要求：
- 先看清问法：问「属于/正确/表明」还是「不属于/错误/不正确」，解析必须与问法方向一致。
- 多选题：逐项说明入选理由与未选项的错处；正确项占比多时不要把它们说成干扰项。
- 单选题：点出最易误选的干扰项，说明它错在哪。
- 不超过 100 字，不复述题干，不写「记住即可」「原文如此」这类空话，不编造文献名。

题目：
题型：{kind}
题干：{q}
选项：
{opts}
正确答案：{ans}

直接输出解析正文，不要任何前缀。
"""

CHECK_PROMPT = """独立判断这道自然辩证法题的标准答案是否正确。

题型：{kind}
题干：{q}
选项：
{opts}
给出的答案：{ans}

严格按教材和通行表述判断。输出一行 JSON，不要代码块：
{{"ok":true,"fix":"若答案有误写正确选项，否则留空","why":"≤30字依据"}}
"""


def pack(c):
    opts = "\n".join(f'{o["k"]}. {o["t"]}' for o in c["options"])
    return opts


def ask(prompt, max_tokens=600, timeout=180):
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": max_tokens, "temperature": 0.2}, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return (json.loads(r.read().decode())["choices"][0]["message"]["content"] or "").strip()


def work(c):
    p = EXPLAIN_PROMPT.format(kind=c["type"], q=c["q"], opts=pack(c), ans=c["answer"])
    exp = ask(p).replace("\n", " ").strip('"“” ')
    chk = ask(CHECK_PROMPT.format(kind=c["type"], q=c["q"], opts=pack(c), ans=c["answer"]))
    verdict = {}
    for line in chk.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                verdict = json.loads(line)
            except Exception:
                pass
    return c["id"], exp, verdict


explain = json.load(open(os.path.join(DK, "explanations.json"), encoding="utf-8"))
check, n_exp = {}, 0
with ThreadPoolExecutor(max_workers=4) as pool:
    for cid, exp, verdict in pool.map(work, cards):
        c = next(x for x in cards if x["id"] == cid)
        if exp and 10 < len(exp) < 260:
            c["explain"] = exp
            explain[cid] = exp
            n_exp += 1
        check[cid] = verdict
        flag = "" if verdict.get("ok") else f"  <<< {verdict.get('fix')} {verdict.get('why')}"
        print(f'{cid} 解析{len(exp)}字 {flag}')

json.dump(decks, open(os.path.join(DK, "decks.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(explain, open(os.path.join(DK, "explanations.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(check, open(os.path.join(DK, "_zhenti_check.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"解析 {n_exp}/{len(cards)} 条")
