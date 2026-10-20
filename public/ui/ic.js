/* Indico Crosstab UI kit — shared components and helpers.
   <ic-icon name="database" size="18">   outline icon
   <ic-sidebar active="datasets">        app navigation (auto-detects the section from the URL)
   <ic-topbar>                           search + signed-in user menu
   window.IC                             DOM, API, format and toast helpers
   Everything that shows data builds DOM nodes and sets textContent, never markup. */
(function () {
  'use strict';

  const ICONS = {
    home: '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    repeat: '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    workflow: '<rect x="3" y="3" width="8" height="8" rx="2"/><path d="M7 11v4a2 2 0 0 0 2 2h4"/><rect x="13" y="13" width="8" height="8" rx="2"/>',
    settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'chevron-up': '<path d="m18 15-6-6-6 6"/>',
    'chevron-right': '<path d="m9 18 6-6-6-6"/>',
    'arrow-left': '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    'arrow-right': '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    'upload-cloud': '<path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2"/><path d="M12 12v9"/><path d="m16 16-4-4-4 4"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    file: '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><path d="M14 2v6h6"/>',
    'file-text': '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    'file-sheet': '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><path d="M14 2v6h6"/><path d="M8 13h2"/><path d="M14 13h2"/><path d="M8 17h2"/><path d="M14 17h2"/>',
    plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
    more: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    'check-circle': '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    pencil: '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
    copy: '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    'log-out': '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    table: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/>',
    layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
    filter: '<path d="M22 3H2l8 9.46V19l4 2v-8.54z"/>',
    sliders: '<path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/><path d="M20 21v-5"/><path d="M20 12V3"/><path d="M1 14h6"/><path d="M9 8h6"/><path d="M17 16h6"/>',
    sparkles: '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/>',
    alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    undo: '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>',
    book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>',
    chart: '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    grid: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    list: '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
    zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 5L2 7"/>',
    eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    'eye-off': '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.53 13.53 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><path d="m2 2 20 20"/>',
    send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    scale: '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
    columns: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 3v18"/>',
    refresh: '<path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/>',
    grip: '<circle cx="9" cy="5" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="19" r="1"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    code: '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>',
    logo: '<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M3.5 9.5h17"/><path d="M9.5 3.5v17"/>',
  };

  class IcIcon extends HTMLElement {
    static get observedAttributes() { return ['name', 'size']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.isConnected) this.render(); }
    render() {
      const size = this.getAttribute('size') || '18';
      const body = ICONS[this.getAttribute('name')] || '';
      this.style.display = 'inline-flex';
      this.style.flexShrink = '0';
      // Icon markup comes only from the static table above.
      this.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
    }
  }

  // ── DOM helpers ────────────────────────────────────────────
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(node.style, v);
      else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }
  const icon = (name, size) => el('ic-icon', { name, size: size || 18 });

  // ── Nav ────────────────────────────────────────────────────
  // Optional features (served by /static/config.js); everything on if it hasn't loaded
  const FEATURES = Object.assign({ datasets: true, chat: true }, window.__INDICO_FEATURES__ || {});
  const NAV = [
    { key: 'home', label: 'Home', href: '/home', icon: 'home', paths: ['/home'] },
    ...(FEATURES.datasets ? [{ key: 'datasets', label: 'Datasets', href: '/datasets', icon: 'database', paths: ['/datasets'] }] : []),
    { key: 'transformations', label: 'Transformations', href: '/review', icon: 'repeat', paths: ['/review'] },
    { key: 'workflows', label: 'Workflows', href: '/workflows', icon: 'workflow', paths: ['/workflows', '/export', '/app', '/express', '/wizard', '/export-mcp'] },
    { key: 'settings', label: 'Settings', href: '/settings', icon: 'settings', paths: ['/settings'] },
  ];
  function activeSection() {
    const p = location.pathname.replace(/\/+$/, '') || '/';
    const hit = NAV.find(n => n.paths.some(x => p === x || p.startsWith(x + '/')));
    return hit ? hit.key : '';
  }

  const brand = (href) => el('a', { class: 'ic-brand', href: href || '/home' },
    el('span', { class: 'ic-brand-mark' }, icon('logo', 16)), 'Indico Crosstab');

  class IcSidebar extends HTMLElement {
    connectedCallback() {
      if (this.dataset.ready) return;
      this.dataset.ready = '1';
      const active = this.getAttribute('active') || activeSection();
      const nav = el('nav', { class: 'ic-nav', 'aria-label': 'Main' },
        NAV.map(n => el('a', { class: 'ic-nav-link', href: n.href, 'aria-current': n.key === active ? 'page' : null },
          icon(n.icon, 18), n.label)));
      const wave = '<svg viewBox="0 0 200 40" preserveAspectRatio="none" aria-hidden="true"><path d="M0 30 C 30 10, 50 38, 80 24 S 130 6, 160 22 S 190 30, 200 18" fill="none" stroke="#8ea3e6" stroke-width="2"/><path d="M0 36 C 40 22, 70 40, 110 30 S 170 18, 200 30" fill="none" stroke="#c5d1f3" stroke-width="2"/></svg>';
      const promo = el('div', { class: 'ic-sidebar-promo' },
        el('strong', { text: 'Better data.' }), el('strong', { text: 'Sharper insights.' }),
        el('p', { text: 'Prepare your market research data for deeper analysis.' }));
      promo.insertAdjacentHTML('beforeend', wave);
      this.append(brand(), nav, promo);
    }
  }

  // ── Session (who is signed in) ─────────────────────────────
  let mePromise = null;
  function me() {
    if (!mePromise) {
      mePromise = fetch('/auth/me', { credentials: 'same-origin' })
        .then(r => (r.ok ? r.json() : null))
        .then(j => (j && j.success ? j.data : null))
        .catch(() => null);
    }
    return mePromise;
  }
  async function signOut() {
    try { await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' }); } catch (_) { /* leave anyway */ }
    location.href = '/';
  }
  function initials(name) {
    const parts = String(name || '').trim().split(/[\s@._-]+/).filter(Boolean);
    return ((parts[0] || '?')[0] + (parts[1] ? parts[1][0] : '')).toUpperCase();
  }
  function firstName(name) { return String(name || '').trim().split(/\s+/)[0] || ''; }

  class IcTopbar extends HTMLElement {
    connectedCallback() {
      if (this.dataset.ready) return;
      this.dataset.ready = '1';
      const input = el('input', { type: 'search', placeholder: 'Search datasets…', 'aria-label': 'Search datasets' });
      const q = new URLSearchParams(location.search).get('q');
      if (q && location.pathname.startsWith('/datasets')) input.value = q;
      input.addEventListener('keydown', e => {
        if (e.key !== 'Enter') return;
        const v = input.value.trim();
        location.href = '/datasets' + (v ? '?q=' + encodeURIComponent(v) : '');
      });
      const search = el('div', { class: 'ic-search', role: 'search', hidden: !FEATURES.datasets }, icon('search', 16), input);

      const avatar = el('span', { class: 'ic-avatar', 'aria-hidden': 'true' });
      const name = el('span', { class: 'ic-user-name' });
      const btn = el('button', { class: 'ic-user-btn', type: 'button', 'aria-haspopup': 'menu', 'aria-expanded': 'false' },
        avatar, name, icon('chevron-down', 16));
      const label = el('div', { class: 'ic-menu-label' });
      const menu = el('div', { class: 'ic-menu', role: 'menu', hidden: true }, label,
        el('a', { class: 'ic-menu-item', href: '/settings', role: 'menuitem' }, icon('settings', 16), 'Settings'),
        el('button', { class: 'ic-menu-item', type: 'button', role: 'menuitem', onclick: signOut }, icon('log-out', 16), 'Sign out'));
      btn.addEventListener('click', e => {
        e.stopPropagation();
        menu.hidden = !menu.hidden;
        btn.setAttribute('aria-expanded', String(!menu.hidden));
      });
      document.addEventListener('click', () => { menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); });
      const user = el('div', { class: 'ic-user' }, btn, menu);
      this.append(this.hasAttribute('no-search') ? el('div') : search, user);

      me().then(u => {
        if (!u) return;
        avatar.textContent = initials(u.name || u.email);
        name.textContent = u.name || u.email;
        label.textContent = u.email;
      });
    }
  }

  // Decorative illustration: stacked data sheets with a trend chart (hero + sign-in).
  const ART = `<svg viewBox="0 0 220 170" fill="none" aria-hidden="true">
    <rect x="58" y="10" width="140" height="104" rx="12" fill="#dfe6fa" stroke="#c8d3f3"/>
    <rect x="40" y="26" width="140" height="104" rx="12" fill="#eef2fd" stroke="#c8d3f3"/>
    <rect x="22" y="42" width="140" height="104" rx="12" fill="#fff" stroke="#c8d3f3"/>
    <rect x="36" y="58" width="60" height="7" rx="3.5" fill="#c8d3f3"/>
    <rect x="36" y="74" width="96" height="5" rx="2.5" fill="#e7ecfa"/>
    <rect x="36" y="86" width="80" height="5" rx="2.5" fill="#e7ecfa"/>
    <rect x="36" y="98" width="88" height="5" rx="2.5" fill="#e7ecfa"/>
    <rect x="116" y="96" width="70" height="62" rx="12" fill="#2f4fb3"/>
    <path d="M128 144 L142 128 L154 136 L174 112" stroke="#fff" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="174" cy="112" r="4" fill="#fff"/>
  </svg>`;
  class IcIllustration extends HTMLElement {
    connectedCallback() { if (!this.firstChild) this.innerHTML = ART; }
  }

  customElements.define('ic-illustration', IcIllustration);
  customElements.define('ic-icon', IcIcon);
  customElements.define('ic-sidebar', IcSidebar);
  customElements.define('ic-topbar', IcTopbar);

  // ── API ────────────────────────────────────────────────────
  function apiKey() { return window.__INDICO_CROSSTAB_DEMO_KEY__ || 'demo'; }
  async function api(path, opts) {
    const o = Object.assign({}, opts || {});
    o.headers = Object.assign({ Authorization: `Bearer ${apiKey()}` }, o.headers || {});
    const res = await fetch(path, o);
    let body = null;
    try { body = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok || (body && body.success === false)) {
      const err = body && (body.error || body.detail);
      const msg = (err && (err.message || (typeof err === 'string' ? err : ''))) || `Request failed (${res.status})`;
      const e = new Error(msg);
      e.status = res.status;
      e.code = err && err.code;
      throw e;
    }
    return body && 'data' in body ? body.data : body;
  }

  // ── Format ─────────────────────────────────────────────────
  const nf = new Intl.NumberFormat();
  function number(n) { return n == null || n === '' || isNaN(n) ? '—' : nf.format(Number(n)); }
  function bytes(b) {
    if (b == null || isNaN(b)) return '—';
    const u = ['B', 'KB', 'MB', 'GB'];
    let i = 0, v = Number(b);
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return `${v.toFixed(v < 10 && i ? 1 : 0)} ${u[i]}`;
  }
  function timeAgo(iso) {
    if (!iso) return '—';
    const t = new Date(iso).getTime();
    if (isNaN(t)) return '—';
    const s = Math.max(0, (Date.now() - t) / 1000);
    const steps = [[60, 'second'], [60, 'minute'], [24, 'hour'], [7, 'day'], [4.35, 'week'], [12, 'month'], [Infinity, 'year']];
    let v = s;
    for (const [div, unit] of steps) {
      if (v < div) {
        const n = Math.floor(v);
        return n <= 0 && unit === 'second' ? 'just now' : `${n} ${unit}${n === 1 ? '' : 's'} ago`;
      }
      v /= div;
    }
    return '—';
  }
  function greeting(date) {
    const h = (date || new Date()).getHours();
    return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
  }
  function fileIcon(name) {
    const ext = String(name || '').split('.').pop().toLowerCase();
    return ['xlsx', 'xls', 'csv', 'tsv'].includes(ext) ? 'file-sheet' : 'file-text';
  }

  // ── Toast ──────────────────────────────────────────────────
  function toast(message, tone) {
    let stack = document.querySelector('.ic-toast-stack');
    if (!stack) { stack = el('div', { class: 'ic-toast-stack', 'aria-live': 'polite' }); document.body.append(stack); }
    const t = el('div', { class: 'ic-toast' + (tone === 'danger' ? ' ic-toast--danger' : ''), text: message });
    stack.append(t);
    setTimeout(() => t.remove(), 3600);
  }

  // ── Stepper ────────────────────────────────────────────────
  // IC.stepper(container, ['Banners', 'Stubs'], currentIndex, { onSelect(i), vertical })
  function stepper(container, steps, current, opts) {
    const o = opts || {};
    container.replaceChildren();
    container.className = 'ic-stepper' + (o.vertical ? ' ic-stepper--vertical' : '');
    steps.forEach((label, i) => {
      if (i) container.append(el('span', { class: 'ic-step-line', 'aria-hidden': 'true' }));
      const state = i < current ? 'is-done' : i === current ? 'is-current' : '';
      const tag = o.onSelect ? 'button' : 'span';
      const node = el(tag, { class: 'ic-step ' + state, type: o.onSelect ? 'button' : null, 'aria-current': i === current ? 'step' : null },
        el('span', { class: 'ic-step-num' }, i < current ? icon('check', 12) : String(i + 1)), label);
      if (o.onSelect) node.addEventListener('click', () => o.onSelect(i));
      container.append(node);
    });
  }

  window.IC = { el, icon, api, apiKey, me, signOut, initials, firstName, number, bytes, timeAgo, greeting, fileIcon, toast, stepper, NAV, FEATURES };
})();
