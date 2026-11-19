"""按审核结论修订题库：改答案、补解析、修数据缺陷。生成件与 decks.json 同步。"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DK = os.path.join(ROOT, "data")
DECKS = os.path.join(DK, "decks.json")


def load(p, d=None):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


FIX = load(os.path.join(DK, "_fix_apply.json"))
if not FIX:
    sys.exit("先跑 tools/gen_fix.py 生成 _fix_apply.json")

decks = load(DECKS)
explain = load(os.path.join(DK, "explanations.json"), {})
bak = DECKS + ".bak-audit"
if not os.path.exists(bak):
    open(bak, "w", encoding="utf-8").write(open(DECKS, encoding="utf-8").read())

changed = []
for deck in decks["decks"]:
    for card in deck["cards"]:
        f = FIX.get(card["id"])
        if not f:
            continue
        old_a, old_e = card.get("answer"), card.get("explain")
        if "answer" in f and f["answer"] != old_a:
            card["answer"] = f["answer"]
        if f.get("explain"):
            card["explain"] = f["explain"]
            explain[card["id"]] = f["explain"]
        if "kind" in f:
            card["kind"] = f["kind"]
            card["type"] = f["kind"]
            card["options"] = []
        changed.append((card["id"], old_a, card.get("answer"), bool(f.get("explain")), f.get("kind")))

json.dump(decks, open(DECKS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(explain, open(os.path.join(DK, "explanations.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

for cid, oa, na, newexp, kind in changed:
    print(f"{cid}: {oa!r} -> {na!r}{' [+解析]' if newexp else ''}{' [kind->'+kind+']' if kind else ''}")
print(f"共修改 {len(changed)} 张")
