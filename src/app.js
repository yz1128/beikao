'use strict';

/* ============================================================
   备考 · 单科目应用
   每个科目一个页面、一份数据、一个独立存储库，互不干扰。
   ============================================================ */

const $ = id => document.getElementById(id);

// kind = 对外展示的题型（单选/多选/判断/选择/简答/背诵）；type = 内部交互方式。
const TYPE_LABEL = {
  single: '单选', multi: '多选', judge: '判断', choice: '选择', short: '简答', qa: '背诵',
};
const ALL_TYPES = ['single', 'multi', 'judge', 'choice', 'short', 'qa'];

// 各科目对外展示的题型顺序（缺的自动略过）。
const COURSE_TYPES = {
  '新中特': ['single', 'multi', 'judge', 'short', 'qa'],
  '自然辩证法': ['choice', 'judge', 'short', 'qa'],
};
const DAY = 86400000;
const MAX_DAYS = 36500;

const params = new URLSearchParams(location.search);
let shuffled = params.get('shuffle') === '1';
let typeFilter = ALL_TYPES.includes(params.get('type')) ? params.get('type') : null;

let states = Object.create(null);
let session = null;
let busy = false;
let database = null;
let saveChain = Promise.resolve();
let latestPayload = null;

const entries = DECKS.decks.flatMap(deck =>
  (deck.cards || []).map(card => ({deck, card, key: JSON.stringify([deck.id, card.id])}))
);

const courseName = PAGE_COURSE || '备考';

// 卡片声明的题型优先；老数据没有 kind 时退回内部 type。
function kindOf(card) {
  return card.kind || card.type;
}

// 各科目实际出现的题型，按固定顺序排，缺的自动略过。
function typeOrder() {
  const wanted = COURSE_TYPES[courseName] || ALL_TYPES;
  return wanted.filter(kind => entries.some(entry => kindOf(entry.card) === kind));
}
const dbName = `beikao-${PAGE_SLUG || 'all'}-v1`;
const LEGACY_DB = PAGE_COURSE ? 'beikao-progress-v1' : null;
const recoveryKey = `beikao-${PAGE_SLUG || 'all'}-recovery`;

/* ---------- 小工具 ---------- */

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function iconButton(label, path, handler) {
  const btn = element('button', 'icon-btn');
  btn.type = 'button';
  btn.setAttribute('aria-label', label);
  btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
  btn.addEventListener('click', handler);
  return btn;
}

let toastTimer = 0;
function toast(message) {
  const box = $('toast');
  box.textContent = message;
  box.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.remove('show'), 2400);
}

// 自绘进度条：极小比例（如 1/525）也保留可见的起点，不退化成一个点。
function meter(value, max, label) {
  const bar = element('div', 'meter');
  bar.setAttribute('role', 'progressbar');
  bar.setAttribute('aria-label', label);
  bar.setAttribute('aria-valuemin', '0');
  bar.setAttribute('aria-valuemax', String(Math.max(1, max)));
  bar.setAttribute('aria-valuenow', String(value));
  const fill = element('i');
  const ratio = Math.max(1, max) ? value / Math.max(1, max) : 0;
  fill.style.width = value > 0 ? `max(10px, ${(ratio * 100).toFixed(2)}%)` : '0';
  bar.append(fill);
  return bar;
}

/* ---------- FSRS-4.5 ---------- */

// FSRS-4.5：原作者 The-Algorithm 历史版本 bc401d9ed5093c66358738f4b8834f8d24ab211b。
const w = [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61];
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

function initDifficulty(rating) {
  return clamp(w[4] - Math.exp(w[5] * (rating - 1)) + 1, 1, 10);
}

function initStability(rating) {
  return Math.max(0.1, w[rating - 1]);
}

function elapsedDays(last, now) {
  return Math.max(0, (now - last) / DAY);
}

function retrievability(elapsed, stability) {
  return Math.pow(1 + elapsed / (9 * stability), -1);
}

function nextDifficulty(difficulty, rating) {
  const next = w[7] * initDifficulty(3) + (1 - w[7]) * (difficulty - w[6] * (rating - 3));
  return clamp(next, 1, 10);
}

function nextStability(state, difficulty, rating, elapsed, r) {
  if (rating === 1) {
    const forget = w[11] * Math.pow(difficulty, -w[12]) * (Math.pow(state.s + 1, w[13]) - 1) * Math.exp((1 - r) * w[14]);
    return Math.min(forget, state.s);
  }
  const hard = rating === 2 ? w[15] : 1;
  const easy = rating === 4 ? w[16] : 1;
  const growth = Math.exp(w[8]) * (11 - difficulty) * Math.pow(state.s, -w[9]) * (Math.exp((1 - r) * w[10]) - 1);
  return state.s * (1 + growth * hard * easy);
}

// 返回新状态；首次学习与后续复习走不同分支。
function schedule(previous, rating, now) {
  const difficulty = previous ? nextDifficulty(previous.d, rating) : initDifficulty(rating);
  let stability;
  if (!previous) {
    stability = initStability(rating);
  } else {
    const elapsed = elapsedDays(Date.parse(previous.last), now);
    stability = nextStability(previous, difficulty, rating, elapsed, retrievability(elapsed, previous.s));
  }
  stability = clamp(stability, 0.1, MAX_DAYS);
  const interval = Math.min(MAX_DAYS, Math.max(1, Math.round(stability)));
  return {
    s: Number(stability.toFixed(4)),
    d: Number(difficulty.toFixed(4)),
    due: now + interval * DAY,
    reps: (previous ? previous.reps : 0) + 1,
    lapses: (previous ? previous.lapses : 0) + (rating === 1 ? 1 : 0),
    last: new Date(now).toISOString(),
    wrong: rating === 1
  };
}

/* ---------- 进度校验 ---------- */

function hasFields(value, fields) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === fields.length && fields.every(key => Object.hasOwn(value, key));
}

function validState(value) {
  if (!hasFields(value, ['s', 'd', 'due', 'reps', 'lapses', 'last', 'wrong'])) return false;
  if (!Number.isFinite(value.s) || value.s < 0.01 || value.s > MAX_DAYS) return false;
  if (!Number.isFinite(value.d) || value.d < 1 || value.d > 10) return false;
  if (!Number.isSafeInteger(value.due) || value.due < 0) return false;
  if (!Number.isSafeInteger(value.reps) || value.reps < 1) return false;
  if (!Number.isSafeInteger(value.lapses) || value.lapses < 0 || value.lapses > value.reps) return false;
  if (typeof value.wrong !== 'boolean' || typeof value.last !== 'string') return false;
  const last = Date.parse(value.last);
  return Number.isFinite(last) && new Date(last).toISOString() === value.last && value.due >= last;
}

function validateStates(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('进度集合无效');
  const clean = Object.create(null);
  Object.entries(raw).forEach(([key, state]) => {
    const ids = JSON.parse(key);
    if (!Array.isArray(ids) || ids.length !== 2 || ids.some(id => typeof id !== 'string' || !id.trim())) {
      throw new Error('进度索引无效');
    }
    if (!validState(state)) throw new Error('进度条目无效');
    clean[key] = state;
  });
  return clean;
}

/* ---------- 存储（每个科目独立） ---------- */

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(dbName, 1);
    request.onupgradeneeded = () => request.result.createObjectStore('progress');
    request.onerror = () => reject(new Error('存储连接失败'));
    request.onblocked = () => reject(new Error('存储被占用'));
    request.onsuccess = () => {
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
  });
}

function transaction(mode, payload) {
  return new Promise((resolve, reject) => {
    const tx = database.transaction('progress', mode);
    const store = tx.objectStore('progress');
    const request = mode === 'readonly' ? store.get('snapshot') : store.put(payload, 'snapshot');
    tx.oncomplete = () => resolve(request.result);
    tx.onabort = tx.onerror = () => reject(new Error('存储事务失败'));
  });
}

async function loadProgress() {
  let stored;
  try {
    database = await openDatabase();
    stored = await transaction('readonly');
  } catch {
    if (database) database.close();
    database = null;
  }
  if (stored !== undefined) {
    try { states = validateStates(JSON.parse(stored)); }
    catch { toast('本机进度格式异常，可导入备份恢复'); }
  }
  try {
    const recovery = localStorage.getItem(recoveryKey);
    if (recovery !== null) {
      states = validateStates(JSON.parse(recovery));
      await persist();
    }
  } catch {
    toast('本地恢复快照无法读取，请检查存储权限');
  }
  await migrateLegacy();
}

// 早先所有科目共用一个进度库；拆页后按卡的归属把旧进度分到各科目，避免升级丢进度。
async function migrateLegacy() {
  if (Object.keys(states).length || !LEGACY_DB) return;
  let snapshot;
  try {
    const legacy = await new Promise((resolve, reject) => {
      const request = indexedDB.open(LEGACY_DB, 1);
      request.onerror = () => reject(new Error('旧库不可读'));
      request.onsuccess = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains('progress')) { db.close(); resolve(undefined); return; }
        const tx = db.transaction('progress', 'readonly');
        const get = tx.objectStore('progress').get('snapshot');
        tx.oncomplete = () => { db.close(); resolve(get.result); };
        tx.onerror = () => { db.close(); reject(new Error('旧库读取失败')); };
      };
    });
    if (typeof legacy !== 'string') return;
    snapshot = validateStates(JSON.parse(legacy));
  } catch { return; }
  const owned = Object.create(null);
  entries.forEach(entry => { if (snapshot[entry.key]) owned[entry.key] = snapshot[entry.key]; });
  if (!Object.keys(owned).length) return;
  states = owned;
  try { await persist(); } catch { /* 迁移失败不影响新库使用。 */ }
  toast(`已从旧版本迁移 ${Object.keys(owned).length} 条进度`);
}

function persist() {
  const payload = JSON.stringify(states);
  latestPayload = payload;
  let recoverySaved = false;
  try { localStorage.setItem(recoveryKey, payload); recoverySaved = true; }
  catch { /* 数据库仍可写，忽略恢复副本失败。 */ }
  const operation = saveChain.then(() => writeProgress(payload, recoverySaved));
  saveChain = operation.catch(() => {});
  return operation;
}

async function writeProgress(payload, recoverySaved) {
  if (database) {
    try { await transaction('readwrite', payload); }
    catch {
      database.close();
      database = null;
    }
  }
  if (!database && !recoverySaved) {
    try { localStorage.setItem(recoveryKey, latestPayload); }
    catch { toast('保存失败，请导出备份'); throw new Error('无法保存'); }
  }
  if (database && recoverySaved) {
    try { if (localStorage.getItem(recoveryKey) === payload) localStorage.removeItem(recoveryKey); }
    catch { /* 保留恢复副本无害。 */ }
  }
}

/* ---------- 队列 ---------- */

function endOfToday(now = Date.now()) {
  const date = new Date(now);
  date.setHours(23, 59, 59, 999);
  return date.getTime();
}

function isDue(entry, cutoff, now) {
  return (states[entry.key]?.due ?? now) <= cutoff;
}

function reviewQueue(pool, now = Date.now()) {
  const cutoff = endOfToday(now);
  return pool
    .filter(entry => isDue(entry, cutoff, now))
    .sort((a, b) => (states[a.key]?.due ?? now) - (states[b.key]?.due ?? now) || a.card.num - b.card.num);
}

function practiceQueue(pool) {
  const queue = [...pool].sort((a, b) => a.card.num - b.card.num);
  if (!shuffled) return queue;
  for (let i = queue.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [queue[i], queue[j]] = [queue[j], queue[i]];
  }
  return queue;
}

function typedPool(pool) {
  return typeFilter ? pool.filter(entry => kindOf(entry.card) === typeFilter) : pool;
}

function currentEntry() {
  return session ? session.queue[session.index] : null;
}

/* ---------- 路由 ---------- */

function updateUrl() {
  const url = new URL(location.href);
  url.searchParams.delete('type');
  url.searchParams.delete('shuffle');
  if (typeFilter) url.searchParams.set('type', typeFilter);
  if (shuffled) url.searchParams.set('shuffle', '1');
  try { history.replaceState(null, '', url); } catch { /* 本地文件环境可能受限。 */ }
}

function setTitle(text) {
  $('topbar-title').textContent = text;
  document.title = text === '备考' ? '备考' : `${text} · 备考`;
}

function showBack(show) {
  $('back-button').hidden = !show;
}

/* ---------- 首页 ---------- */

function renderHome() {
  const main = $('main');
  main.classList.remove('is-session');
  main.replaceChildren();
  setTitle(courseName);
  showBack(Boolean(PAGE_COURSE));
  $('data-button').hidden = !PAGE_COURSE;
  if (!PAGE_COURSE) { main.append(renderCatalog()); return; }
  if (!entries.length) {
    main.append(element('p', 'empty', '题库还没有准备好。'));
    return;
  }
  const wrap = element('div', 'stack-32');
  wrap.append(renderHero(), renderToday(), renderTypes(), renderDecks());
  main.append(wrap);
}

function renderHero() {
  const box = element('section', 'hero');
  const pool = typedPool(entries);
  const known = pool.filter(entry => states[entry.key]).length;
  const head = element('div', 'hero-head');
  const left = element('div');
  left.append(element('p', 'eyebrow', '总进度'), element('p', 'hero-stat', `${known} / ${pool.length}`));
  head.append(left);
  if (typeFilter) {
    const clear = element('button', 'text-btn', '取消筛选');
    clear.type = 'button';
    clear.addEventListener('click', () => { typeFilter = null; updateUrl(); renderHome(); });
    head.append(clear);
  }
  box.append(head, meter(known, Math.max(1, pool.length), '总进度'));
  return box;
}

// 科目目录：只放科目名与项目介绍，进度和入口都在各自科目页里。
function renderCatalog() {
  const wrap = element('div', 'stack-32');
  const hero = element('section', 'hero');
  hero.append(element('p', 'eyebrow', '科目'));
  if (SITE && SITE.intro) hero.append(element('p', 'intro', SITE.intro));
  wrap.append(hero);

  const list = element('div', 'course-list');
  (CATALOG || []).forEach(item => {
    const card = element('a', 'course-card');
    card.href = item.file;
    const head = element('div', 'course-head');
    const text = element('div');
    text.append(
      element('p', 'course-name', item.name),
      element('p', 'course-desc', item.desc || '')
    );
    if (item.tags && item.tags.length) {
      const tags = element('div', 'tag-row');
      item.tags.forEach(label => {
        const tag = element('span', 'tiny-tag');
        const [word, num] = label.split(' ');
        tag.append(document.createTextNode(word + ' '), element('b', '', num || ''));
        tags.append(tag);
      });
      text.append(tags);
    }
    const arrow = element('span', 'course-arrow');
    arrow.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>';
    head.append(text, arrow);
    card.append(head);
    list.append(card);
  });
  wrap.append(list);
  return wrap;
}

function renderToday() {
  const pool = typedPool(entries);
  const due = reviewQueue(pool).length;
  const wrong = pool.filter(entry => states[entry.key]?.wrong).length;
  const card = element('section', 'today');
  const top = element('div', 'today-top');
  const left = element('div');
  const num = element('p', 'today-num');
  num.append(document.createTextNode(String(due)), element('small', '', '张'));
  const fresh = pool.filter(entry => !states[entry.key]).length;
  const review = due - fresh;
  left.append(element('p', 'eyebrow', review > 0 ? '今日复习' : '今日新卡'), num);
  top.append(left);
  card.append(top, element('p', 'today-label', review > 0 ? `新卡 ${fresh} · 到期 ${review}` : '还没学过，从头开始'));
  card.append(renderOrder());
  const start = element('button', 'btn btn-primary btn-block', review > 0 ? '开始今日复习' : '开始学新卡');
  start.type = 'button';
  start.addEventListener('click', () => startSession(due ? 'review' : 'practice'));
  card.append(start);
  if (wrong) {
    const mistakes = element('button', 'btn btn-quiet btn-block', `错题本 · ${wrong}`);
    mistakes.type = 'button';
    mistakes.style.marginTop = '8px';
    mistakes.addEventListener('click', () => startSession('mistakes'));
    card.append(mistakes);
  }
  return card;
}

// 出题顺序：顺序走题库原始次序，随机每次开始重新洗牌。
function renderOrder() {
  const row = element('div', 'order-row');
  row.style.margin = '16px 0 14px';
  const label = element('span', 'order-label', '出题顺序');
  const group = element('div', 'segmented');
  group.setAttribute('role', 'group');
  group.setAttribute('aria-label', '出题顺序');
  [['sequential', '顺序'], ['random', '随机']].forEach(([value, text]) => {
    const on = (value === 'random') === shuffled;
    const button = element('button', 'segment', text);
    button.type = 'button';
    button.setAttribute('aria-pressed', String(on));
    button.addEventListener('click', () => {
      shuffled = value === 'random';
      updateUrl();
      renderHome();
    });
    group.append(button);
  });
  row.append(label, group);
  return row;
}

function renderTypes() {
  const section = element('section');
  const label = element('div', 'section-label');
  label.append(element('h2', '', '按题型背'));
  const grid = element('div', 'chip-grid');
  typeOrder().forEach(type => {
    const part = entries.filter(entry => kindOf(entry.card) === type);
    if (!part.length) return;
    const chip = element('button', 'chip');
    chip.type = 'button';
    chip.setAttribute('aria-pressed', String(typeFilter === type));
    const name = element('span', 'chip-label', TYPE_LABEL[type]);
    const count = element('span', 'chip-count', String(part.length));
    chip.append(name, count);
    chip.addEventListener('click', () => {
      typeFilter = typeFilter === type ? null : type;
      updateUrl();
      renderHome();
    });
    grid.append(chip);
  });
  section.append(label, grid);
  return section;
}

// 题库副标题：总数 + 题型分布（多于一种题型时才列）。
function deckSub(pool, known) {
  const kinds = typeOrder().filter(kind => pool.some(entry => kindOf(entry.card) === kind));
  const mix = kinds.length > 1 ? ' · ' + kinds.map(kind => TYPE_LABEL[kind]).join('/') : '';
  const learned = known ? ` · 已学 ${known}` : '';
  return `${pool.length} 张${mix}${learned}`;
}

function renderDecks() {
  const section = element('section');
  const label = element('div', 'section-label');
  label.append(element('h2', '', '题库'));
  section.append(label);
  DECKS.decks.forEach(deck => {
    const pool = typedPool(entries.filter(entry => entry.deck.id === deck.id));
    if (!pool.length) return;
    const known = pool.filter(entry => states[entry.key]).length;
    const card = element('button', 'deck-card');
    card.type = 'button';
    card.disabled = !pool.length;
    const row = element('div', 'deck-row');
    const text = element('div');
    text.append(
      element('p', 'deck-title', deck.title.replace(/\s*\d+\s*题$/, '')),
      element('p', 'deck-sub', deckSub(pool, known))
    );
    const arrow = element('span', 'course-arrow');
    arrow.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>';
    row.append(text, arrow);
    card.append(row);
    card.append(meter(known, Math.max(1, pool.length), `${deck.title}已学进度`));
    card.addEventListener('click', () => startSession('practice', deck.id));
    section.append(card);
  });
  return section;
}

/* ---------- 会话 ---------- */

function startSession(kind, deckId) {
  const base = deckId ? entries.filter(entry => entry.deck.id === deckId) : entries;
  const pool = typedPool(base);
  let queue = kind === 'review' ? reviewQueue(pool)
    : kind === 'mistakes' ? practiceQueue(pool.filter(entry => states[entry.key]?.wrong))
    : orderedPool(pool);
  if (shuffled) queue = shuffle(queue);
  if (!queue.length) {
    toast(kind === 'mistakes' ? '还没有错题' : '这一类暂时没有需要复习的卡');
    return;
  }
  session = {queue, index: 0, phase: 'question', selected: new Set(), done: 0, label: labelFor(kind)};
  renderSession();
}

// 顺序模式严格按题库原始次序走，不受「没学过/待复习」筛选影响。
function orderedPool(pool) {
  return pool.slice();
}

function shuffle(list) {
  const out = list.slice();
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function labelFor(kind) {
  const base = kind === 'review' ? '今日复习' : kind === 'mistakes' ? '错题本' : (shuffled ? '乱序练习' : '顺序练习');
  return typeFilter ? `${base} · ${TYPE_LABEL[typeFilter]}` : base;
}

function renderSession(focus = true) {
  const main = $('main');
  main.classList.add('is-session');
  main.replaceChildren();
  const entry = currentEntry();
  if (!entry) { renderDone(); return; }
  main.append(renderSessionBar(), renderQuestion(entry));
  if (entry.card.type === 'qa' && session.phase !== 'question') main.append(renderAnswer(entry.card));
  if (session.phase === 'feedback' && entry.card.type !== 'qa') main.append(renderFeedback(entry));
  main.append(renderActionBar(entry));
  if (focus) {
    main.scrollIntoView({block: 'start'});
    window.scrollTo(0, 0);
  }
}

function renderSessionBar() {
  const box = element('div', 'session-progress');
  const fill = element('i');
  fill.style.width = `${(session.done / session.queue.length) * 100}%`;
  box.append(fill);
  return box;
}

function renderQuestion(entry) {
  const {card, deck} = entry;
  const section = element('section');
  const head = element('div', 'q-head');
  head.append(
    element('span', 'tag', TYPE_LABEL[kindOf(card)]),
    element('span', 'tag tag-neutral', card.num ? `第 ${card.num} 题` : deck.title),
    element('span', 'q-count', `${session.index + 1} / ${session.queue.length}`)
  );
  section.append(head, element('p', 'q-text', card.q));
  if (card.type === 'multi') section.append(element('p', 'muted q-hint', '选出所有正确选项'));
  if (card.type !== 'qa') section.append(renderOptions(card));
  if (card.source && card.source !== deck.title) section.append(element('p', 'source', card.source));
  return section;
}

function optionList(card) {
  return card.type === 'judge' ? [{k: 'T', t: '正确'}, {k: 'F', t: '错误'}] : (card.options || []);
}

function renderOptions(card) {
  const list = element('div', 'options');
  const answered = session.phase !== 'question';
  optionList(card).forEach(option => {
    const btn = element('button', 'option');
    btn.type = 'button';
    const selected = session.selected.has(option.k);
    const correct = (card.answer || '').includes(option.k);
    btn.classList.toggle('selected', selected && !answered);
    btn.setAttribute('aria-pressed', String(selected));
    btn.disabled = answered || busy;
    const letter = element('span', 'letter', option.k === 'T' ? '对' : option.k === 'F' ? '错' : option.k);
    const body = element('span', 'body', option.t);
    if (answered) {
      btn.classList.toggle('correct', correct);
      btn.classList.toggle('incorrect', selected && !correct);
      if (correct) body.append(element('span', 'flag', '正确答案'));
      else if (selected) body.append(element('span', 'flag', '你的选择'));
    }
    btn.append(letter, body);
    btn.addEventListener('click', () => chooseOption(option.k));
    list.append(btn);
  });
  return list;
}

function renderAnswer(card) {
  const box = element('div', 'answer');
  box.tabIndex = 0;
  box.setAttribute('role', 'region');
  box.setAttribute('aria-label', '参考答案');
  box.textContent = card.answer || '（无参考答案）';
  return box;
}

function renderFeedback(entry) {
  const {card} = entry;
  const ok = session.selected && isCorrect(card, session.selected);
  const box = element('div', `feedback${ok ? '' : ' bad'}`);
  box.append(element('p', 'feedback-title', ok ? '答对了' : '答错了'));
  const detail = element('p', 'feedback-text');
  const parts = [];
  if (card.type !== 'qa') parts.push(`正确答案：${formatAnswer(card)}`);
  if (card.explain) parts.push(card.explain);
  detail.textContent = parts.join('\n');
  if (detail.textContent) box.append(detail);
  return box;
}

function formatAnswer(card) {
  return optionList(card)
    .filter(option => (card.answer || '').includes(option.k))
    .map(option => `${option.k === 'T' ? '对' : option.k === 'F' ? '错' : option.k}. ${option.t}`)
    .join('\n');
}

function isCorrect(card, selected) {
  const answer = card.type === 'judge'
    ? card.answer
    : [...(card.answer || '')].filter(ch => /[A-Z]/.test(ch)).sort().join('');
  const picked = [...selected].filter(ch => card.type === 'judge' ? true : /[A-Z]/.test(ch)).sort().join('');
  return answer === picked;
}

// 触屏设备上没有空格/回车，快捷键提示只在桌面显示。
function kbdHint(text) {
  const fine = window.matchMedia && window.matchMedia('(pointer: fine)').matches;
  return fine ? element('p', 'kbd-hint', text) : null;
}

function renderActionBar(entry) {
  const bar = element('div', 'actionbar');
  const {card} = entry;
  const kind = kindOf(card);
  const hint = text => {
    const node = kbdHint(text);
    if (node) bar.append(node);
  };

  if (session.phase === 'question') {
    if (card.type === 'single' || card.type === 'judge') {
      hint(card.type === 'judge' ? '点「对」或「错」即判分' : '点选项即判分');
      return bar;
    }
    if (card.type === 'qa') {
      const show = element('button', 'btn btn-primary btn-block', kind === 'qa' ? '看答案' : '查看参考答案');
      show.type = 'button';
      show.addEventListener('click', () => { session.phase = 'answer'; renderSession(false); });
      bar.append(show);
      hint('空格看答案');
      return bar;
    }
    const submit = element('button', 'btn btn-primary btn-block', '提交答案');
    submit.type = 'button';
    submit.disabled = busy || session.selected.size === 0;
    submit.addEventListener('click', submitAnswer);
    bar.append(submit);
    hint('A–D 选择 · 回车提交');
    return bar;
  }

  if (session.phase === 'answer') {
    const row = element('div', 'btn-row');
    [['忘了', 1], ['模糊', 2], ['记得', 3]].forEach(([label, rating]) => {
      const btn = element('button', `btn ${rating === 3 ? 'btn-primary' : 'btn-secondary'}`, label);
      btn.type = 'button';
      btn.addEventListener('click', () => rate(rating));
      row.append(btn);
    });
    bar.append(row);
    hint('1 忘了 · 2 模糊 · 3 记得');
    return bar;
  }

  const next = element('button', 'btn btn-primary btn-block',
    session.index + 1 >= session.queue.length ? '完成' : '下一题');
  next.type = 'button';
  next.addEventListener('click', nextCard);
  bar.append(next);
  hint('回车继续');
  return bar;
}

function renderDone() {
  const main = $('main');
  main.replaceChildren();
  const box = element('section', 'done');
  const icon = element('div', 'done-icon');
  icon.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>';
  box.append(icon, element('h2', '', '这一轮完成了'), element('p', '', `共复习 ${session ? session.done : 0} 张`));
  const row = element('div', 'btn-row');
  const again = element('button', 'btn btn-primary', '再来一轮');
  again.type = 'button';
  again.addEventListener('click', renderHome);
  const home = element('button', 'btn btn-quiet', '回到题库');
  home.type = 'button';
  home.addEventListener('click', renderHome);
  row.append(again, home);
  box.append(row);
  main.append(box);
  session = null;
  showBack(Boolean(PAGE_COURSE));
}

/* ---------- 作答 ---------- */

function chooseOption(key) {
  const entry = currentEntry();
  if (!entry || session.phase !== 'question' || busy) return;
  const {card} = entry;
  if (card.type === 'multi') {
    if (session.selected.has(key)) session.selected.delete(key);
    else session.selected.add(key);
    renderSession(false);
    return;
  }
  session.selected = new Set([key]);
  submitAnswer();
}

async function submitAnswer() {
  const entry = currentEntry();
  if (!entry || busy) return;
  const {card, key} = entry;
  const correct = isCorrect(card, session.selected);
  session.phase = 'feedback';
  session.done += 1;
  await record(key, correct ? 3 : 1, correct);
  renderSession(false);
}

async function rate(rating) {
  const entry = currentEntry();
  if (!entry || busy) return;
  session.phase = 'feedback';
  session.done += 1;
  await record(entry.key, rating, rating >= 2);
  renderSession(false);
}

async function record(key, rating, correct) {
  busy = true;
  const next = schedule(states[key], rating, Date.now());
  states[key] = {...next, wrong: !correct};
  try { await persist(); }
  catch { toast('保存失败，请导出备份'); }
  busy = false;
}

function nextCard() {
  if (!session) return;
  if (session.index + 1 >= session.queue.length) {
    renderDone();
    return;
  }
  session.index += 1;
  session.phase = 'question';
  session.selected = new Set();
  renderSession();
}

/* ---------- 数据管理 ---------- */

function openData() {
  const dialog = $('data-dialog');
  $('data-note').textContent = `当前科目：${courseName}。进度只在本页面内使用，导出后可带到其他设备。`;
  $('data-field').value = '';
  $('data-status').textContent = '';
  dialog.showModal();
}

function exportData() {
  const payload = {app: 'beikao', course: PAGE_COURSE || courseName, version: 1, states};
  const text = btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
  $('data-field').value = text;
  $('data-field').select();
  navigator.clipboard?.writeText(text).then(
    () => { $('data-status').textContent = `已导出并复制 ${Object.keys(states).length} 条进度`; },
    () => { $('data-status').textContent = '已导出，请手动复制'; }
  );
}

async function importData() {
  const text = $('data-field').value.trim();
  if (!text) { $('data-status').textContent = '请先粘贴备份文本'; return; }
  try {
    const json = decodeURIComponent(escape(atob(text)));
    const parsed = JSON.parse(json);
    if (parsed.app !== 'beikao' || parsed.version !== 1) throw new Error('不是本应用的备份');
    if ((parsed.course || '') !== (PAGE_COURSE || courseName)) {
      throw new Error(`这是「${parsed.course}」的备份，不能导入到「${courseName}」`);
    }
    states = validateStates(parsed.states);
    await persist();
    $('data-status').textContent = `已导入 ${Object.keys(states).length} 条进度`;
    renderHome();
  } catch (error) {
    $('data-status').textContent = `导入失败：${error.message}`;
  }
}

/* ---------- 启动 ---------- */

function bindControls() {
  $('data-button').addEventListener('click', openData);
  $('data-close').addEventListener('click', () => $('data-dialog').close());
  $('export-button').addEventListener('click', exportData);
  $('import-button').addEventListener('click', importData);
  $('data-apply').addEventListener('click', importData);
  // 返回：答题中先退到本科目首页，科目首页再退回科目目录。
  $('back-button').addEventListener('click', goBack);
  $('main').addEventListener('keydown', handleKeys);
}

function goBack() {
  if (session) {
    session = null;
    updateUrl();
    renderHome();
    return;
  }
  if (typeof PAGE_HOME === 'string' && PAGE_HOME) location.assign(PAGE_HOME);
}

function handleKeys(event) {
  if (event.target.matches('input, textarea')) return;
  if (!session) return;
  const entry = currentEntry();
  if (!entry) return;
  const {card} = entry;
  if (event.key === ' ' && card.type === 'qa' && session.phase === 'question') {
    event.preventDefault();
    session.phase = 'answer';
    renderSession(false);
    return;
  }
  if (session.phase === 'answer') {
    if (['1', '2', '3'].includes(event.key)) {
      event.preventDefault();
      rate(Number(event.key));
    }
    return;
  }
  if (event.key === 'Enter') {
    event.preventDefault();
    if (session.phase === 'feedback') nextCard();
    else if (card.type === 'multi' && session.selected.size) submitAnswer();
    return;
  }
  if (session.phase !== 'question' || card.type === 'qa') return;
  const key = event.key.toUpperCase();
  if (card.type === 'judge') {
    if (key === 'T' || key === 'A' || key === '1') { event.preventDefault(); chooseOption('T'); }
    if (key === 'F' || key === 'B' || key === '2') { event.preventDefault(); chooseOption('F'); }
    return;
  }
  if (optionList(card).some(option => option.k === key)) {
    event.preventDefault();
    chooseOption(key);
  }
}

async function boot() {
  bindControls();
  await loadProgress();
  const deckId = params.get('deck');
  if (deckId && DECKS.decks.some(deck => deck.id === deckId)) {
    startSession('practice', deckId);
    return;
  }
  renderHome();
}

boot();
