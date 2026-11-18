你是实现工程师。当前目录 C:/Users/Yanz/Projects/beikao-web 下已完成数据准备。

## 你的任务
读取 `SPEC.md`（实现规格，含数据结构、功能需求、算法要求、验收标准），产出：

1. **`index.html`** —— 单文件静态应用，全部 CSS/JS 内联，不引任何外部 CDN。
2. **`README.md`** —— 简短使用说明（iOS 风格简洁，中文）。

## 关键约束

### 题库数据占位
`data/decks.json` 有 305 KB / 565 张卡，**不要整份读进上下文**。在 `index.html` 里这样写占位：

```js
const DECKS = /*@DECK_DATA@*/{"version":1,"decks":[]}/*@DECK_DATA_END@*/;
```

我会在你产出后用脚本把真实 JSON 注入这段占位之间。所以：
- 占位标记必须**逐字**是 `/*@DECK_DATA@*/` 和 `/*@DECK_DATA_END@*/`
- 数据结构按 SPEC.md 的表，你自己造 3-5 条假的样例数据**只在心里推演**，不要写进文件
- 代码里所有对 `DECKS.decks[].cards[]` 的访问必须能容忍 `decks: []`（空数组时空态提示，不是报错）

### 技术栈
- 原生 HTML/CSS/JS，无框架、无构建、无 npm
- 存储：优先 IndexedDB，失败降级 localStorage
- 渲染：用 `textContent` 或转义后插入，禁止把题面直接拼进 innerHTML
- 深色主题，移动端优先（375px 宽不横向滚动）
- 缩进 ≤3 层，函数单一职责，中文注释

### 必须实现（P0）
1. 首页：按 course 分组，4 个题库卡片（title/desc/count/已学进度/今日待复习）
2. 抽卡作答 → 立即判分 → 显示正确答案 + explain → 下一题
3. 顺序 / 乱序 两种模式
4. 错题本（独立入口，答对移出）
5. 进度持久化（刷新不丢）
6. 进度导出 = Base64 字符串；导入 = 粘贴还原

### 必须实现（P1）
FSRS-4.5 简化调度（参数见 SPEC.md），支持 `?deck=zt-quiz` 与 `?shuffle=1` URL 参数。

### 交互细节（易错，务必落实）
- `single`：点选项立刻判分
- `multi`：多选后点「提交」判分，全对才算对
- `judge`：两个按钮「正确 / 错误」
- `qa`：先显示题干，点「看答案」展开答案，然后三档自评（忘了/模糊/记得）→ 分别映射 FSRS rating 1/2/3。答案区必须 `white-space: pre-wrap` 且可滚动，因为有的答案有几百字
- 键盘：A/B/C/D 选项、Enter 提交或下一题、Space 看答案、1/2/3 自评

## 完成前自检
- 用 `node --check` 或等效方式验证 JS 语法（可把 script 抽出来检查）
- 确认文件里没有 `TODO`、没有 `console.log` 调试残留、没有外部 URL（`http://` / `https://` 引用）
- 确认占位标记存在且只有一处

## 输出
直接写文件，不要只贴代码。完成后用 3 行内说明你做了什么。
