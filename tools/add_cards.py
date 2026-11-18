"""
把手写或抓取的新卡片追加进 decks.json，然后重建 index.html。

用法：
  python tools/add_cards.py --deck zt-quiz --file new_cards.json
  python tools/add_cards.py --deck zt-quiz --interactive

兼容两种输入格式：
  1) 卡片数组 [ {...}, {...} ]
  2) 单个题库对象 {"id":..., "cards":[...]}（只取 cards）
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECKS = os.path.join(ROOT, "data", "decks.json")

VALID_TYPES = {"single", "multi", "judge", "qa"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize(card, deck_id):
    """校验并补齐字段，缺关键字段就抛错，不静默丢弃。"""
    c = dict(card)
    ctype = c.get("type")
    if ctype not in VALID_TYPES:
        raise ValueError(f"type 必须是 {VALID_TYPES}，收到 {ctype!r}（卡 id={c.get('id')}）")

    q = (c.get("q") or "").strip()
    if not q:
        raise ValueError(f"缺题干 q（卡 id={c.get('id')}）")
    c["q"] = q

    ans = c.get("answer")
    if isinstance(ans, list):
        ans = "".join(ans)
    ans = (ans or "").strip() if ctype != "qa" else (c.get("answer") or "").strip()

    if ctype in ("single", "multi"):
        opts = c.get("options") or []
        if len(opts) != 4:
            raise ValueError(f"选择题必须 4 个选项，收到 {len(opts)} 个（卡 id={c.get('id')}）")
        keys = {o.get("k") for o in opts}
        if keys != {"A", "B", "C", "D"}:
            raise ValueError(f"选项 key 必须是 A/B/C/D（卡 id={c.get('id')}）")
        if ctype == "single" and ans not in keys:
            raise ValueError(f"单选 answer 必须是单个 A-D，收到 {ans!r}（卡 id={c.get('id')}）")
        if ctype == "multi" and (not ans or any(ch not in keys for ch in ans)):
            raise ValueError(f"多选 answer 必须是 A-D 组合如 'ACD'，收到 {ans!r}（卡 id={c.get('id')}）")
        c["options"] = opts
    elif ctype == "judge":
        if ans in ("对", "√", "T", "true", "True"):
            ans = "T"
        elif ans in ("错", "×", "F", "false", "False"):
            ans = "F"
        if ans not in ("T", "F"):
            raise ValueError(f"判断题 answer 必须是 T/F 或 对/错，收到 {ans!r}（卡 id={c.get('id')}）")
        c["options"] = []
    else:  # qa
        if len(ans) < 2:
            raise ValueError(f"问答卡 answer 不能为空（卡 id={c.get('id')}）")
        c["options"] = []

    c["answer"] = ans
    c["explain"] = (c.get("explain") or "").strip()
    c["source"] = (c.get("source") or "").strip()

    # 没给 id 就按题库自动编号，避免和已有卡冲突
    if not c.get("id"):
        c["id"] = f"{deck_id}-new-{c.get('num') or abs(hash(q)) % 100000}"
    if "num" not in c:
        c["num"] = 0
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True, help="目标题库 id，如 zt-quiz")
    ap.add_argument("--file", help="新卡片 JSON 文件")
    ap.add_argument("--dry-run", action="store_true", help="只校验不写入")
    args = ap.parse_args()

    data = load(DECKS)
    deck = next((d for d in data["decks"] if d["id"] == args.deck), None)
    if deck is None:
        ids = [d["id"] for d in data["decks"]]
        print(f"找不到题库 {args.deck!r}，现有：{ids}", file=sys.stderr)
        return 1

    raw = load(args.file)
    incoming = raw if isinstance(raw, list) else raw.get("cards", [])

    existing = {c["id"] for c in deck["cards"]}
    added, updated = [], []
    for item in incoming:
        card = normalize(item, args.deck)
        if card["id"] in existing:
            # 同 id 视为更新，覆盖原卡（改错字、补解析都用它）
            deck["cards"] = [card if c["id"] == card["id"] else c for c in deck["cards"]]
            updated.append(card["id"])
        else:
            deck["cards"].append(card)
            existing.add(card["id"])
            added.append(card["id"])

    deck["cards"].sort(key=lambda c: (c.get("num") or 0))
    deck["count"] = len(deck["cards"])
    deck["desc"] = deck.get("desc") or ""

    print(f"题库 {args.deck}：新增 {len(added)} 张，更新 {len(updated)} 张，现共 {deck['count']} 张")
    if added:
        print("  新增 id:", ", ".join(added))
    if updated:
        print("  更新 id:", ", ".join(updated))

    if args.dry_run:
        print("(dry-run，未写入)")
        return 0

    with open(DECKS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"已写入 {DECKS}")

    # 自动重建，省掉一步
    build = os.path.join(ROOT, "tools", "build.py")
    if os.path.exists(build):
        print("\n重建 index.html ...")
        os.system(f'"{sys.executable}" "{build}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
