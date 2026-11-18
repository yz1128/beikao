"""
把 src/ 下的源码与 data/decks.json 组装成每个科目一个自包含 HTML。

  index.html      科目目录
  zhongte.html    新中特
  ziran.html      自然辩证法

每个页面内联自己的 CSS、JS、题库，以及自己的存储库名，
所以两个科目在浏览器里进度、备份、错题本完全隔离。

改界面请改 src/shell.html、src/style.css、src/app.js，然后跑本脚本。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
DECKS = os.path.join(ROOT, "data", "decks.json")

DATA_START, DATA_END = "/*@DECK_DATA@*/", "/*@DECK_DATA_END@*/"
CSS_MARK, JS_MARK = "/*@CSS@*/", "/*@APP_JS@*/"
META_START, META_END = "/*@PAGE_META@*/", "/*@PAGE_META_END@*/"

# 输出文件 -> (科目名, 存储标识)
PAGES = {
    "index.html": (None, "all"),
    "zhongte.html": ("新中特", "zhongte"),
    "ziran.html": ("自然辩证法", "ziran"),
}

LINKS = {name: filename for filename, (name, _) in PAGES.items() if name}


def render_shell(shell, css, js, decks, course, slug, catalog, site):
    meta = (
        f"const PAGE_COURSE = {json.dumps(course, ensure_ascii=False) if course else 'null'};\n"
        f"const PAGE_SLUG = {json.dumps(slug)};\n"
        f"const PAGE_LINKS = {json.dumps(LINKS, ensure_ascii=False)};\n"
        f"const PAGE_HOME = 'index.html';\n"
        f"const CATALOG = {json.dumps(catalog, ensure_ascii=False)};\n"
        f"const SITE = {json.dumps(site, ensure_ascii=False)};"
    )
    payload = json.dumps(decks, ensure_ascii=False, indent=1).replace("</", "<\\/")
    out = shell.replace(CSS_MARK, css).replace(JS_MARK, js)
    # 用切片替换整段占位内容，避免残留旧 JSON 造成语法错误
    i = out.index(DATA_START) + len(DATA_START)
    j = out.index(DATA_END)
    out = out[:i] + payload + out[j:]
    mi = out.index(META_START) + len(META_START)
    mj = out.index(META_END)
    return out[:mi] + "\n" + meta + "\n" + out[mj:]


def check_once(text, marks):
    for mark in marks:
        count = text.count(mark)
        if count != 1:
            raise SystemExit(f"占位 {mark} 出现 {count} 次，应为 1 次")


def main():
    shell = open(os.path.join(SRC, "shell.html"), encoding="utf-8").read()
    css = open(os.path.join(SRC, "style.css"), encoding="utf-8").read()
    js = open(os.path.join(SRC, "app.js"), encoding="utf-8").read()
    check_once(shell, [DATA_START, DATA_END, CSS_MARK, JS_MARK, META_START, META_END])

    data = json.load(open(DECKS, encoding="utf-8"))
    for deck in data["decks"]:
        deck["count"] = len(deck["cards"])
    total = sum(len(d["cards"]) for d in data["decks"])
    print(f"题库 {len(data['decks'])} 个 / {total} 张卡")

    # 目录页的数据：科目文案来自 src/courses.json，规模数字从题库统计
    meta = json.load(open(os.path.join(SRC, "courses.json"), encoding="utf-8"))
    copies = {item["name"]: item for item in meta.get("courses", [])}
    catalog = []
    for name, filename in LINKS.items():
        cards = sum(len(d["cards"]) for d in data["decks"] if d["course"] == name)
        decks_count = sum(1 for d in data["decks"] if d["course"] == name)
        slug = next(s for f, (n, s) in PAGES.items() if n == name)
        item = copies.get(name, {})
        catalog.append({
            "name": name,
            "file": filename,
            "cards": cards,
            "decks": decks_count,
            "slug": slug,
            "desc": item.get("desc", ""),
        })
    site = {"title": meta.get("title", "备考"), "intro": meta.get("intro", "")}

    for filename, (course, slug) in PAGES.items():
        subset = dict(data)
        subset["decks"] = [d for d in data["decks"] if course is None or d["course"] == course]
        # 目录页不装题库，只列科目
        if course is None:
            subset["decks"] = []
        count = sum(len(d["cards"]) for d in subset["decks"])
        html = render_shell(shell, css, js, subset, course, slug, catalog, site)
        path = os.path.join(ROOT, filename)
        open(path, "w", encoding="utf-8").write(html)
        label = course or "科目目录"
        detail = f"{len(subset['decks'])} 个题库 / {count} 张" if course else "无题库"
        print(f"  {filename:14} {label:6} {detail:18} {os.path.getsize(path)/1024:.0f} KB")

    # 目录页也带字典，前端首屏要按科目跳转
    return 0


if __name__ == "__main__":
    sys.exit(main())
