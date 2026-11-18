# 备考

两门课的背诵与刷题，离线单文件，进度存在本机。

- 科目目录：https://yz1128.github.io/beikao/
- 新中特：https://yz1128.github.io/beikao/zhongte.html
- 自然辩证法：https://yz1128.github.io/beikao/ziran.html

## 结构

每个科目一个独立页面、一份独立进度库（`beikao-zhongte-v1` / `beikao-ziran-v1`）。
换科目不串进度，导出备份也只认自己科目的。

## 维护

改界面改 `src/`（`shell.html` / `style.css` / `app.js`），不要直接改生成的 html。

```powershell
python tools/build.py      # 从 src/ + data/decks.json 生成三个页面
python tools/publish.py    # 构建并上传
python tools/add_cards.py --deck zt-quiz --file 新题.json
```

## 题库

| 题库 | 课程 | 张数 |
|---|---|---|
| zt-quiz | 新中特·章节测验 | 429 |
| zt-backs | 新中特·背诵指南 | 96 |
| zrb-quiz | 自然辩证法·选择与判断 | 50 |
| zrb-backs | 自然辩证法·背诵与简答 | 112 |
