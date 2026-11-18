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

| 题库 | 课程 | 张数 | 题型 |
|---|---|---|---|
| zt-quiz | 新中特·章节测验 | 429 | 单选 159 / 多选 113 / 判断 157 |
| zt-backs | 新中特·背诵指南 | 96 | 简答 47 / 背诵 49 |
| zrb-quiz | 自然辩证法·选择与判断 | 54 | 选择 21 / 判断 33 |
| zrb-backs | 自然辩证法·背诵与简答 | 99 | 简答 60 / 背诵 39 |
| zrb-yilan | 自然辩证法·考前速览 | 9 | 一页纸提纲（独立，不计入总进度） |

「考前速览」的 9 张是各章提纲，与 `zrb-backs` 的详解卡覆盖同一批知识点但粒度不同。
它在数据里标 `standalone: true`，不进总进度、今日新卡和按题型统计，只在题库区单列。
