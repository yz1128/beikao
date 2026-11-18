"""
给单选/多选/判断/填空式选择批量生成解析，调本地 magpie 的 wbm/hy4flash-free。

- 多路并发（默认 6），每路一次 8 题
- 结果边跑边落盘到 data/explanations.json，中断重跑会跳过已完成的 id
- 单个批次失败会拆小重试，仍失败就跳过并记录

用法：
  python tools/gen_explain.py            # 全量
  python tools/gen_explain.py --limit 40 # 只跑前 40 张（试水）
  python tools/gen_explain.py --workers 8
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
OUT = os.path.join(ROOT, "data", "explanations.json")
ENDPOINT = "http://127.0.0.1:3425/v1/chat/completions"
MODEL = "wbm/hy4flash-free"
TARGET_KINDS = ("single", "multi", "judge", "choice")

lock = threading.Lock()
done_count = 0


def load_store():
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_store(store):
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT)


def needs_explain(card, store):
    if card.get("kind") not in TARGET_KINDS:
        return False
    if str(card.get("explain") or "").strip():
        return False
    return not str(store.get(card["id"]) or "").strip()


def pack(card):
    if card["kind"] in ("single", "multi"):
        opts = "\n".join(f'{o["k"]}. {o["t"]}' for o in card.get("options") or [])
        label = "单选" if card["kind"] == "single" else "多选"
        return f'[{card["id"]}] {label}\n题干：{card["q"]}\n选项：\n{opts}\n答案：{card["answer"]}'
    if card["kind"] == "judge":
        ans = "正确" if card["answer"] == "T" else "错误"
        return f'[{card["id"]}] 判断\n题干：{card["q"]}\n答案：{ans}'
    return f'[{card["id"]}] 填空式选择\n题干：{card["q"]}\n答案：{card["answer"]}'


PROMPT = """[解析任务 {nonce}] 为下列 {n} 道政治课题写解析。每题 1-3 句，不超过 90 字。

要求：
- 说清正确项为什么成立；判断题指出对在何处，或错在哪个词。
- 单选点出最易误选的干扰项，说明它为什么不成立。
- 多选题的正确项都属于答案，不要把正确项说成干扰项；只针对未选中的选项说明为什么不该选。
- 先看清题干问的是「属于/是」还是「不属于/不是」，解析结论必须与问法一致。
- 不复述题干，不编造文件名称、会议届次、原文条文，不确定的不写。
- 全中文，写完立即停止，不要总结或重复题目。

输出格式（每个 id 一行标题，正文换行，无其他内容）：
### id
解析正文
### id
解析正文

题目：
{body}
"""

ID_LINE = re.compile(r"^#{0,3}\s*\[?([a-z]+-[\w\-]+)\]?\s*$")


def call(batch, max_tokens=12000, timeout=420):
    prompt = PROMPT.format(
        nonce=f"{int(time.time()*1000) % 100000}-{batch[0]['id']}",
        n=len(batch),
        body="\n".join(pack(c) for c in batch),
    )
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["choices"][0]["message"].get("content") or ""
    out, cur = {}, None
    for line in text.splitlines():
        line = line.strip()
        hit = ID_LINE.match(line)
        if hit:
            cur = hit.group(1)
            out[cur] = ""
        elif cur and line:
            out[cur] = (out[cur] + " " + line).strip()
    out = {k: v for k, v in out.items() if 8 <= len(v) <= 200}
    return out


def run_batch(batch):
    """跑一批；返回成功写出的解析。失败就拆半重试。"""
    try:
        got = call(batch)
    except Exception as exc:  # 网络/超时/解析失败都走重试
        got = {}
        print(f"  批次失败 {batch[0]['id']}..{batch[-1]['id']}: {type(exc).__name__}", flush=True)
    if len(got) >= len(batch):
        return got
    if len(batch) == 1:
        return got
    # 缺题的批次拆成两半再跑
    mid = len(batch) // 2
    merged = dict(got)
    for half in (batch[:mid], batch[mid:]):
        if any(c["id"] not in merged for c in half):
            merged.update(run_batch(half))
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()

    with open(DECKS, encoding="utf-8") as f:
        data = json.load(f)
    store = load_store()

    todo = [c for deck in data["decks"] for c in deck["cards"] if needs_explain(c, store)]
    if args.limit:
        todo = todo[: args.limit]
    if not todo:
        print("没有需要写解析的题了")
        return 0

    batches = [todo[i:i + args.batch] for i in range(0, len(todo), args.batch)]
    print(f"待写 {len(todo)} 张，{len(batches)} 批，{args.workers} 路并发", flush=True)
    started = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_batch, b): b for b in batches}
        for fut in as_completed(futures):
            got = fut.result()
            with lock:
                store.update(got)
                save_store(store)
                done = len([c for c in todo if c["id"] in store])
                pct = done / len(todo) * 100
                print(f"  {done:4d}/{len(todo)}  {pct:5.1f}%  {time.time()-started:6.0f}s", flush=True)

    print(f"完成 {len(store)} 条，用时 {time.time()-started:.0f}s，落盘 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
