# 备考 · 背诵网页

https://yz1128.github.io/beikao/

双击 `index.html` 也能用，**完全离线**，无外部依赖。

## 题库

| 课程 | 题库 | 题量 |
|---|---|---|
| 新中特 | 章节测验 442 题 | 429 |
| 新中特 | 背诵指南（三轮题 + 概念卡 + 自测） | 48 |
| 自然辩证法 | 选择与判断 | 50 |
| 自然辩证法 | 背诵与简答（一页纸 + 简答论述） | 38 |

合计 565 张卡，四种题型：单选 / 多选 / 判断 / 问答。

- 单选、判断：点完立即判分
- 多选：选完点「提交」，全对才算对
- 问答：先自己回想，点「看答案」再自评（忘了 / 模糊 / 记得）

答错或「忘了」进错题本，答对或「记得」移出。今日复习 = 未学卡 + 今天到期卡。

## 进度

进度存在浏览器本地（IndexedDB，降级 localStorage）。**换设备、换浏览器、移动文件都会丢进度**，走备份：

1. 「进度备份」→「导出进度」→ 复制那串 Base64
2. 新设备打开同一页面 →「进度备份」→ 粘贴 → 勾选「替换全部本机进度」→ 导入

导入是整体替换，不合并。

## 补题 / 纠错

见 [CONTRIBUTING.md](CONTRIBUTING.md)。一题一 Issue，或者邮件发整份资料到 **871022082@qq.com**。

## 快捷键

`A`–`D` 选项 ｜ `Enter` 提交 / 下一题 ｜ `Space` 看答案 ｜ `1/2/3` 自评

URL 参数：`?deck=zt-quiz` 直进题库，`?shuffle=1` 乱序，可组合。

## 维护

```bash
# 加题（自动校验字段、自动重建）
python tools/add_cards.py --deck zt-quiz --file 新题.json

# 只重建单文件
python tools/build.py

# 构建并上线
python tools/publish.py
```

题库内联在 `index.html` 的 `/*@DECK_DATA@*/ ... /*@DECK_DATA_END@*/` 之间，由 `tools/build.py` 从 `data/decks.json` 生成，不要手改那段 JSON。卡片字段与约束见 `CONTRIBUTING.md` 和 `SPEC.md`。
