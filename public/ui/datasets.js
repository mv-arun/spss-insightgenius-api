/* Dataset library (persistent files): the calls and placeholders the app's Dataset step uses.
   Needs ic.js. */
(function () {
  'use strict';
  const { el, icon, api } = IC;

  const Datasets = {
    async list() { return (await api('/v1/library/files')).files || []; },
    upload(file) {
      const form = new FormData();
      form.append('file', file);
      return api('/v1/library/upload', { method: 'POST', body: form });
    },
    name(f) { return f.display_name || f.filename || 'Untitled'; },
    /* Placeholder rows while loading. */
    skeleton(rows) {
      const wrap = el('div', { style: { padding: '16px 20px', display: 'grid', gap: '14px' } });
      for (let i = 0; i < (rows || 4); i++) wrap.append(el('div', { class: 'ic-skeleton', style: { width: (90 - i * 12) + '%' } }));
      return wrap;
    },
    empty(title, hint, action) {
      return el('div', { class: 'ic-empty' }, icon('database', 32), el('div', { text: title, style: { fontWeight: 600, color: 'var(--ic-text)' } }),
        hint ? el('div', { text: hint, style: { marginTop: '4px' } }) : null, action ? el('div', { style: { marginTop: '14px' } }, action) : null);
    },
    error(err, retry) {
      return el('div', { class: 'ic-empty' }, icon('alert', 28),
        el('div', { text: 'Couldn’t load datasets', style: { fontWeight: 600, color: 'var(--ic-text)' } }),
        el('div', { text: err.message, style: { marginTop: '4px' } }),
        retry ? el('button', { class: 'ic-btn ic-btn--secondary ic-btn--sm', type: 'button', style: { marginTop: '14px' }, onclick: retry }, icon('refresh', 14), 'Try again') : null);
    },
  };

  window.Datasets = Datasets;
})();
