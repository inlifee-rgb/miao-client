/* ============================================================
   MIAO Console · 共享逻辑
   web 与桌面 App 共用；桌面端 window.dorimiNative 存在时走原生桥
   ============================================================ */

const D = {
  brand: 'MIAO',
  apiBase: '',           // 同源，由 gateway 提供 /api/*
  key: '',
  me: null,
  models: [],
};

/* ---------------- 小工具 ---------------- */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function toast(msg) {
  let t = $('.toast');
  if (!t) {
    t = document.createElement('div');
    t.className = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  requestAnimationFrame(() => t.classList.add('show'));
  clearTimeout(t._tm);
  t._tm = setTimeout(() => t.classList.remove('show'), 1900);
}

function fmtPts(n) {
  if (n == null) return '—';
  const v = Number(n);
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function maskKey(k) {
  if (!k) return '';
  if (k.length <= 18) return k;
  return k.slice(0, 8) + '******' + k.slice(-6);
}

async function copyText(t) {
  try {
    await navigator.clipboard.writeText(t);
    return true;
  } catch (e) {
    const ta = document.createElement('textarea');
    ta.value = t;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); return true; }
    catch (_) { return false; }
    finally { document.body.removeChild(ta); }
  }
}

function saveBlob(name, text, type = 'application/json') {
  const b = new Blob([text], { type: type + ';charset=utf-8' });
  const u = URL.createObjectURL(b);
  const a = document.createElement('a');
  a.href = u;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(u); a.remove(); }, 300);
}

/* ---------------- 接口 ---------------- */

async function api(path, opt = {}) {
  const url = D.apiBase + path;
  const init = { headers: { 'Content-Type': 'application/json' } };
  if (opt.method) init.method = opt.method;
  if (opt.body) init.body = JSON.stringify(opt.body);
  const r = await fetch(url, init);
  let j = null;
  try { j = await r.json(); } catch (_) {}
  if (!r.ok) {
    const msg = (j && (j.message || j.error)) || ('HTTP ' + r.status);
    throw new Error(msg);
  }
  return j;
}

async function loadMe(key) {
  const j = await api('/api/me?key=' + encodeURIComponent(key));
  if (!j || j.ok === false) throw new Error((j && j.message) || '查询失败');
  D.me = j;
  D.key = key;
  localStorage.setItem('dorimi_key', key);
  return j;
}

async function loadLogs(key, limit = 12) {
  const j = await api('/api/me/logs?key=' + encodeURIComponent(key) + '&limit=' + limit);
  return (j && j.rows) || [];
}

/* ---------------- 图标 ---------------- */

const ICON = {
  copy: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2.5"/><path d="M15 5.5A2.5 2.5 0 0 0 12.5 3H5.5A2.5 2.5 0 0 0 3 5.5v7A2.5 2.5 0 0 0 5.5 15"/></svg>',
  download: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M4 20h16"/></svg>',
  eye: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2.2 12S5.8 5.6 12 5.6 21.8 12 21.8 12 18.2 18.4 12 18.4 2.2 12 2.2 12Z"/><circle cx="12" cy="12" r="2.7"/></svg>',
  eyeOff: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l18 18"/><path d="M10.6 6c.5-.06 1-.1 1.4-.1 6.2 0 9.8 6.1 9.8 6.1a17 17 0 0 1-3.3 3.9"/><path d="M6.4 6.6A16.7 16.7 0 0 0 2.2 12S5.8 18.1 12 18.1c1.3 0 2.5-.26 3.6-.7"/></svg>',
  check: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="m4 12.5 5 5L20 6.5"/></svg>',
  warn: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2.6 20h18.8L12 3Z"/><path d="M12 9.5v4"/><circle cx="12" cy="17" r=".6" fill="currentColor"/></svg>',
  x: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 5l14 14M19 5 5 19"/></svg>',
  arrow: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h15"/><path d="m13 6 6 6-6 6"/></svg>',
  ext: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M18 14v4.5A2.5 2.5 0 0 1 15.5 21H5.5A2.5 2.5 0 0 1 3 18.5v-10A2.5 2.5 0 0 1 5.5 6H10"/></svg>',
  refresh: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1"/><path d="M20.7 4.2v4.6h-4.6"/></svg>',
  plug: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3v6"/><path d="M15 3v6"/><path d="M6.5 9h11v3.5A5.5 5.5 0 0 1 12 18a5.5 5.5 0 0 1-5.5-5.5V9Z"/><path d="M12 18v3"/></svg>',
  spark: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3Z"/></svg>',
  file: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M13 3H7a2.5 2.5 0 0 0-2.5 2.5v13A2.5 2.5 0 0 0 7 21h10a2.5 2.5 0 0 0 2.5-2.5V9.5L13 3Z"/><path d="M13 3v6.5h6.5"/></svg>',
  code: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m8.5 8-4 4 4 4"/><path d="m15.5 8 4 4-4 4"/></svg>',
  chev: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
  wechat: '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M8.8 3C5 3 2 5.5 2 8.6c0 1.8 1 3.4 2.7 4.4l-.7 2.2 2.4-1.2c.8.2 1.6.3 2.4.3h.6a5.3 5.3 0 0 1-.2-1.4c0-3 3-5.5 6.7-5.5h.6C16 5 12.8 3 8.8 3Zm-2.3 3a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8Zm4.6 0a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8Z"/><path d="M22 12.9c0-2.6-2.6-4.7-5.7-4.7s-5.7 2.1-5.7 4.7 2.6 4.7 5.7 4.7c.7 0 1.3-.1 1.9-.3l2 1-.6-1.8c1.5-.8 2.4-2.1 2.4-3.6Zm-7.6-1.5a.8.8 0 1 1 0 1.5.8.8 0 0 1 0-1.5Zm3.8 0a.8.8 0 1 1 0 1.5.8.8 0 0 1 0-1.5Z"/></svg>',
  gift: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10h16v10H4z"/><path d="M3 7h18v3H3z"/><path d="M12 7v13"/><path d="M12 7c-1-2-2.2-3-3.6-3A2.4 2.4 0 0 0 6 6.4C6 7 6.4 7 7 7h5Z"/></svg>',
};

/* ---------------- 弹层 ---------------- */

function openMask(id) { $('#' + id).classList.add('open'); }
function closeMask(id) { $('#' + id).classList.remove('open'); }

document.addEventListener('click', e => {
  const m = e.target.closest('.mask');
  if (m && e.target === m) m.classList.remove('open');
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') $$('.mask.open').forEach(m => m.classList.remove('open'));
});

/* ---------------- 生成 models.json ---------------- */

function buildModelsConfig(key, url) {
  // 网关里注册的前缀品牌名（models.json 的 id 前缀）
  const brand = D.brand === 'MIAO' ? 'Miao' : D.brand;
  return D.models.map((m, i) => ({
    name: brand + ':' + m.id,
    vendor: 'user',
    url: url || 'http://127.0.0.1:18085/v1',
    descriptionEn: 'Available through ' + brand + '. Rate ' + m.rate + '.',
    descriptionZh: '通过 ' + brand + ' 提供 · 费率 ' + m.rate,
    maxInputTokens: 200000,
    maxOutputTokens: 32000,
    temperature: 1,
    supportsToolCall: true,
    supportsImages: true,
    supportsReasoning: false,
    tags: ['custom', brand],
    disabled: false,
    id: brand + ':' + m.id,
    apiKey: key,
    isDefault: i === 0,
  }));
}
