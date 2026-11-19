"""
用本地 wbm/hy4flash-free 审核题库的「答案 + 解析」是否正确。

- 每题独立判定：答案 ok / wrong / unsure；解析 ok / off（答非所问/串题）/ wrong / none
- 多路并发（默认 8），每路 5 题；边跑边落盘 data/_audit.json，中断重跑跳过已完成 id
- 判定为 wrong / off / unsure 的题，第二轮反序重审一次，两次都异常才保留

用法：
  python tools/audit_answers.py --limit 10   # 试水
  python tools/audit_answers.py              # 全量
"""
import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECKS = os.path.join(ROOT, "data", "decks.json")
OUT = os.path.join(ROOT, "data", "_audit.json")
ENDPOINT = "http://127.0.0.1:3425/v1/chat/completions"
MODEL = "wbm/hy4flash-free"
TARGET_KINDS = ("single", "multi", "judge", "choice")

lock = threading.Lock()


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_store(store):
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT)


def pack(card, explain):
    ans = card.get("answer")
    if card.get("kind") == "judge":
        ans = "正确(T)" if ans == "T" else "错误(F)"
    body = [f'[{card["id"]}] 题型:{card.get("kind")}']
    body.append(f'题干：{card.get("q")}')
    opts = card.get("options") or []
    if opts:
        body.append("选项：\n" + "\n".join(f'{o["k"]}. {o["t"]}' for o in opts))
    body.append(f"当前答案：{ans}")
    body.append(f"当前解析：{explain or '（无）'}")
    return "\n".join(body)


PROMPT = """[审核任务 {nonce}] 你是政治理论课（新中特 / 自然辩证法）题库审校员。逐题核对「当前答案」和「当前解析」。

判定标准：
1. answer：按教材通行表述，当前答案是否正确。正确 = ok；错误 = wrong（n 里写正确选项）；教材无定论或你无法确认 = unsure。
2. explain：解析是否与答案自洽、是否在解释本题。
   - 与答案一致且说清了理由 = ok
   - 答非所问、内容属于别的题（如问系统属性却讲民族精神）、空话套话没有信息 = off
   - 解析自身说错、与答案矛盾 = wrong
   - 没有解析 = none
3. 只判这两项，不重写解析。n 不超过 40 字，写关键理由或更正内容；ok 且无异常时 n 写 ""。

输出：每题一行 JSON，不要 markdown 代码块，不要任何其他文字：
{{"id":"zt-003","answer":"ok","explain":"ok","n":""}}

题目：
{body}
"""

FIX = {}


def parse(text, ids):
    out = {}
    for line in text.splitlines():
        line = line.strip().strip("`")
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            # 常见破损：中文引号 / 尾逗号 / 缺右括号
            s = line.replace("“", '"').replace("”", '"').replace("，", ",")
            s = re.sub(r",\s*}", "}", s)
            if not s.endswith("}"):
                s += "}"
            try:
                obj = json.loads(s)
            except Exception:
                continue
        if obj.get("id") in ids:
            a = str(obj.get("answer", "")).lower().strip()
            e = str(obj.get("explain", "")).lower().strip()
            if a in ("ok", "wrong", "unsure") and e in ("ok", "off", "wrong", "none"):
                out[obj["id"]] = {"answer": a, "explain": e, "n": str(obj.get("n", ""))[:80]}
    return out


def call(batch, nonce, timeout=600):
    body = PROMPT.format(
        nonce=nonce,
        body="\n\n".join(pack(c, c.get("_explain")) for c in batch),
    )
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({
            "model": MODEL,
            "messages": [{"role": "user", "content": body}],
            "max_tokens": 16000,
            "temperature": 0.1,
        }, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["choices"][0]["message"].get("content") or ""
    return parse(text, {c["id"] for c in batch})


def run_batch(batch, round_no):
    try:
        got = call(batch, f"{round_no}-{int(time.time()*1000)%100000}-{batch[0]['id']}")
    except Exception as exc:
        print(f"  批次失败 {batch[0]['id']}: {type(exc).__name__}", flush=True)
        got = {}
    missing = [c for c in batch if c["id"] not in got]
    if missing and len(batch) > 1:
        for c in missing:
            got.update(run_batch([c], round_no))
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--batch", type=int, default=5)
    args = ap.parse_args()

    data = load_json(DECKS, {"decks": []})
    explain = load_json(os.path.join(ROOT, "data", "explanations.json"), {})
    store = load_json(OUT, {})

    todo = []
    for deck in data["decks"]:
        for card in deck["cards"]:
            if card.get("kind") not in TARGET_KINDS:
                continue
            if card["id"] in store:
                continue
            card = dict(card)
            card["_explain"] = explain.get(card["id"]) or card.get("explain") or ""
            todo.append(card)
    if args.limit:
        todo = todo[: args.limit]
    if not todo:
        print(f"没有待审题目，已有结果 {len(store)} 条")
        return 0

    batches = [todo[i:i + args.batch] for i in range(0, len(todo), args.batch)]
    print(f"待审 {len(todo)} 题，{len(batches)} 批，{args.workers} 路并发", flush=True)
    started = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_batch, b, 1): b for b in batches}
        for fut in as_completed(futures):
            got = fut.result()
            with lock:
                store.update(got)
                save_store(store)
                done = len([c for c in todo if c["id"] in store])
                print(f"  {done:4d}/{len(todo):4d}  {time.time()-started:5.0f}s", flush=True)

    print(f"第一轮完成，共 {len(store)} 条，用时 {time.time()-started:.0f}s")

    # 第二轮：异常项反序重审
    flagged = [c for c in todo if c["id"] in store and (store[c["id"]]["answer"] != "ok" or store[c["id"]]["explain"] not in ("ok", "none"))]
    if flagged:
        print(f"重审 {len(flagged)} 条异常项……", flush=True)
        rounds = [flagged[i:i + args.batch] for i in range(0, len(flagged), args.batch)]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_batch, list(reversed(b)), 2): b for b in rounds}
            for fut in as_completed(futures):
                got = fut.result()
                with lock:
                    for k, v in got.items():
                        first = store.get(k)
                        if first and v["answer"] == "ok" and v["explain"] in ("ok", "none") and first["answer"] == "ok" and first["explain"] in ("ok", "none"):
                            continue
                        store[k] = {"answer": first["answer"], "explain": first["explain"], "n": first["n"],
                                    "recheck": v}
                    save_store(store)
    print(f"全部完成，{len(store)} 条，落盘 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
