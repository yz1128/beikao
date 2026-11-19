"""对 hy4flash-free 判为异常的题目做第二意见复核（wbm/deepseek-v4.1-flash）。

输出 data/_audit_recheck2.json，供 audit_report.py 合并。
"""
import json
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DK = os.path.join(ROOT, "data")
ENDPOINT = "http://127.0.0.1:3425/v1/chat/completions"
MODEL = "wbm/deepseek-v4.1-flash"


def j(name, default):
    p = os.path.join(DK, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


PROMPT = """你是政治理论课（新中特 / 自然辩证法）题库的独立审校员。逐题判断「当前答案」和「当前解析」是否正确。

严格标准：
- answer: 与教材/中央文件通行表述完全一致才算 ok；与通行表述有实质出入 = wrong，并在 n 写正确选项或正确表述；表述本身有争议 = unsure。
- explain: 与答案自洽且确实在解释本题 = ok；内容属于别的题或纯背诵清单未解释本题 = off；与答案矛盾或说错 = wrong；无解析 = none。
- 只判这两项。n ≤ 40 字，写关键依据；没问题写 ""。
- 不要因为「答案看起来来自原题库」就默认它对，就题论题。

每题输出一行 JSON（不要代码块、不要其他文字）：
{{"id":"zt-003","answer":"ok","explain":"ok","n":""}}

题目：
{body}
"""


def load_all():
    decks = j("decks.json", {"decks": []})
    explain = j("explanations.json", {})
    meta = {}
    for deck in decks["decks"]:
        for c in deck["cards"]:
            meta[c["id"]] = c
    return meta, explain


def pack(card, explain):
    ans = card.get("answer")
    if card.get("kind") == "judge":
        ans = "正确(T)" if ans == "T" else "错误(F)"
    lines = [f'[{card["id"]}] 题型:{card.get("kind")}', f'题干：{card.get("q")}']
    if card.get("options"):
        lines.append("选项：\n" + "\n".join(f'{o["k"]}. {o["t"]}' for o in card["options"]))
    lines.append(f"当前答案：{ans}")
    lines.append(f"当前解析：{explain or '（无）'}")
    return "\n".join(lines)


def call(items, timeout=600):
    body = PROMPT.format(body="\n\n".join(pack(c, c["_exp"]) for c in items))
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({"model": MODEL, "messages": [{"role": "user", "content": body}],
                         "max_tokens": 8000, "temperature": 0.1}, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        txt = json.loads(r.read().decode())["choices"][0]["message"]["content"] or ""
    out = {}
    for line in txt.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("id"):
            out[o["id"]] = {"answer": o.get("answer"), "explain": o.get("explain"), "n": str(o.get("n", ""))[:80]}
    return out


def main():
    meta, explain = load_all()
    audit = j("_audit.json", {})
    targets = []
    for cid, v in audit.items():
        r2 = v.get("recheck") or {}
        if r2.get("answer") == "ok" and r2.get("explain") in ("ok", "none"):
            continue  # 第二轮已洗白
        if v["answer"] != "ok" or v["explain"] not in ("ok", "none"):
            c = dict(meta[cid])
            c["_exp"] = explain.get(cid) or meta[cid].get("explain") or ""
            targets.append(c)
    print(f"送第二意见 {len(targets)} 题，模型 {MODEL}")
    out = j("_audit_recheck2.json", {})
    todo = [c for c in targets if c["id"] not in out]
    batches = [todo[i:i + 4] for i in range(0, len(todo), 4)]
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(call, b): b for b in batches}
        for f in futs:
            pass
        for f in list(futs):
            try:
                got = f.result()
            except Exception as exc:
                print("  批失败", type(exc).__name__)
                continue
            with lock:
                out.update(got)
                json.dump(out, open(os.path.join(DK, "_audit_recheck2.json"), "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
                print(f"  {len(out)}/{len(targets)}")
    print("完成", len(out))


if __name__ == "__main__":
    sys.exit(main())
