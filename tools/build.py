"""
从 src/app.html 生成多页面：

  index.html      全部课程（首页）
  zhongte.html    新中特
  ziran.html      自然辩证法

三个页面共用同一份源码和同一份题库数据，只是 PAGE_COURSE 不同。
题库数据按页面只注入该课程，减小体积；进度按「题库 id + 卡 id」区分，跨页面共享。
改页面结构请改 src/app.html，不要直接改生成的三个 html。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "src", "app.html")
DECKS = os.path.join(ROOT, "data", "decks.json")

START = "/*@DECK_DATA@*/"
END = "/*@DECK_DATA_END@*/"
META_START = "//@PAGE_META@"
META_END = "//@PAGE_META_END@"

# 文件名 -> 课程名（None 表示全部课程）
PAGES = {
    "index.html": None,
    "zhongte.html": "新中特",
    "ziran.html": "自然辩证法",
}


def meta_block(course):
    """按页面替换导航常量块。"""
    # PAGES 是 {文件名: 课程名}，注入页面里要反过来成 {课程名: 文件名}
    pages = '{' + ', '.join(f'"{course}": "{filename}"'
                            for filename, course in PAGES.items() if course) + '}'
    page_course = "null" if course is None else json.dumps(course, ensure_ascii=False)
    return f"const PAGES = {pages};\nconst PAGE_COURSE = {page_course};"


def main():
    tpl = open(TEMPLATE, encoding="utf-8").read()
    if tpl.count(START) != 1 or tpl.count(END) != 1:
        print(f"数据占位异常：{START}x{tpl.count(START)} {END}x{tpl.count(END)}", file=sys.stderr)
        return 1
    if tpl.count(META_START) != 1 or tpl.count(META_END) != 1:
        print("页面元信息占位异常", file=sys.stderr)
        return 1

    data = json.load(open(DECKS, encoding="utf-8"))
    for deck in data["decks"]:
        deck["count"] = len(deck["cards"])

    total_all = sum(len(d["cards"]) for d in data["decks"])
    print(f"题库总计 {len(data['decks'])} 个 / {total_all} 张卡")

    for filename, course in PAGES.items():
        page = dict(data)
        page["decks"] = [d for d in data["decks"] if course is None or d["course"] == course]
        subtotal = sum(len(d["cards"]) for d in page["decks"])

        # 防止数据里出现 </script> 截断脚本
        payload = json.dumps(page, ensure_ascii=False, indent=1).replace("</", "<\\/")

        i = tpl.index(START) + len(START)
        j = tpl.index(END)
        out = tpl[:i] + payload + tpl[j:]

        mi = out.index(META_START) + len(META_START)
        mj = out.index(META_END)
        out = out[:mi] + "\n" + meta_block(course) + "\n" + out[mj:]

        path = os.path.join(ROOT, filename)
        open(path, "w", encoding="utf-8").write(out)
        label = course or "全部"
        print(f"  {filename:14} {label:6} {len(page['decks'])} 个题库 / {subtotal} 张  "
              f"({os.path.getsize(path) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
