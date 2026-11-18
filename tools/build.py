"""
把 data/decks.json 注入 index.html 的占位段，产出可发布的单文件。

占位：const DECKS = /*@DECK_DATA@*/ ... /*@DECK_DATA_END@*/;
改造后的 index.html 本身就带着完整数据，所以再跑一次也能正确替换（幂等）。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "index.html")
DECKS = os.path.join(ROOT, "data", "decks.json")

START = "/*@DECK_DATA@*/"
END = "/*@DECK_DATA_END@*/"


def main():
    html = open(HTML, encoding="utf-8").read()

    if html.count(START) != 1 or html.count(END) != 1:
        print(f"占位标记异常：START×{html.count(START)} END×{html.count(END)}", file=sys.stderr)
        return 1

    data = json.load(open(DECKS, encoding="utf-8"))
    total = sum(len(d["cards"]) for d in data["decks"])
    for d in data["decks"]:
        d["count"] = len(d["cards"])

    # 防止数据里出现 </script> 截断脚本
    payload = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")

    i = html.index(START) + len(START)
    j = html.index(END)
    out = html[:i] + payload + html[j:]

    open(HTML, "w", encoding="utf-8").write(out)

    print(f"已注入 {len(data['decks'])} 个题库 / {total} 张卡")
    for d in data["decks"]:
        print(f"  {d['id']:12} {d['course']} · {d['title']} — {d['count']} 张")
    print(f"index.html 体积：{os.path.getsize(HTML) / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
