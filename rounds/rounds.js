import * as store from './lib/store.js';
import { standModel, bySection, search, togglePlanned, isPlanned, plannedFor, daysBetween } from './lib/plan.js';
import { fetchStands, fetchFair } from './lib/string.js';

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let db, stands = [], plan = {}, settings = {}, day = null, screen = 'stands';

async function boot() {
  db = await store.openDb();
  settings = await store.getSettings(db);
  settings.stringUrl = settings.stringUrl || 'http://localhost:8100';
  plan = await store.getPlan(db);
  stands = (await store.cachedStands(db)).map(standModel);

  fillDays();
  wire();
  render();
  refresh();          // best-effort; the hall usually has no connection
}

function fillDays() {
  // Days come from the seeded fair event's span, cached alongside the stands.
  const days = settings.days || [];
  $('day').innerHTML = `<option value="">All days</option>`
    + days.map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
  $('day').value = day || '';
}

async function refresh() {
  try {
    // The fair event carries the run's span and name; without it the day
    // selector has nothing to offer, so read it before the stands.
    const fair = await fetchFair(settings.stringUrl, settings.token);
    if (fair) {
      settings.days = daysBetween(fair.body.startsAt, fair.body.endsAt);
      settings.fairName = fair.body.name || settings.fairName;
      const tag = (fair.body.tags || []).find(t => t.startsWith('fair:'));
      if (tag) settings.fairSlug = tag.slice('fair:'.length);
      await store.saveSettings(db, settings);
      fillDays();
    }
    const records = await fetchStands(settings.stringUrl, settings.token);
    if (records.length) {
      await store.cacheStands(db, records);
      stands = records.map(standModel);
      render();
      note(`${stands.length} stands cached`);
    }
  } catch {
    note('offline — using the cached plan');   // expected, not an error
  }
}

function note(msg) { $('queue-status').textContent = msg; }

function standRow(s) {
  const on = isPlanned(plan, s.id);
  return `<div class="stand">
    <div class="body">
      <div class="g">${esc(s.gallery)}</div>
      ${s.artists.length ? `<div class="a">${esc(s.artists.slice(0, 4).join(', '))}</div>` : ''}
    </div>
    <button class="mark" data-id="${esc(s.id)}" aria-pressed="${on}">${on ? '★' : '☆'}</button>
  </div>`;
}

function render() {
  $('screen-stands').classList.toggle('hidden', screen !== 'stands');
  $('screen-plan').classList.toggle('hidden', screen !== 'plan');
  $('screen-fair').classList.toggle('hidden', screen !== 'fair');
  for (const [t, name] of [['tab-stands', 'stands'], ['tab-plan', 'plan'], ['tab-fair', 'fair']]) {
    $(t).setAttribute('aria-current', String(screen === name));
  }

  if (screen === 'stands') {
    const found = search(stands, $('q').value);
    $('stands').innerHTML = bySection(found).map(g =>
      `<div class="section-title">${esc(g.section || 'Unsectioned')} · ${g.stands.length}</div>`
      + g.stands.map(standRow).join('')).join('')
      || `<p class="status">No stands yet. Seed the String, then reload.</p>`;
  }

  if (screen === 'plan') {
    const mine = plannedFor(stands, plan, day || null);
    $('plan-empty').classList.toggle('hidden', mine.length > 0);
    $('plan').innerHTML = bySection(mine).map(g =>
      `<div class="section-title">${esc(g.section || 'Unsectioned')}</div>`
      + g.stands.map(standRow).join('')).join('');
  }

  if (screen === 'fair') {
    $('fair-summary').textContent =
      `${stands.length} stands cached · ${Object.keys(plan).length} planned`;
  }
}

function wire() {
  $('tab-stands').onclick = () => { screen = 'stands'; render(); };
  $('tab-plan').onclick   = () => { screen = 'plan'; render(); };
  $('tab-fair').onclick   = () => { screen = 'fair'; render(); };
  $('q').oninput = () => render();
  $('day').onchange = e => { day = e.target.value || null; render(); };

  document.addEventListener('click', async e => {
    const btn = e.target.closest('.mark');
    if (!btn) return;
    plan = togglePlanned(plan, btn.dataset.id, day);
    await store.savePlan(db, plan);
    render();
  });
}

boot().catch(e => {
  // Storage can genuinely refuse: Safari private browsing, a blocked version
  // upgrade, a corrupted database. Without this the shell renders but nothing
  // is wired — an app that silently does nothing, which reads as broken
  // rather than as failed. fillDays(), wire(), render(), and refresh() never
  // ran, so nav clicks do nothing and the footer would otherwise still say
  // "ready" — write the explanation directly into the static elements that
  // exist before any script runs.
  const msg = 'This device would not open local storage, so Rounds cannot '
    + 'hold your plan. ' + (e?.message || '');
  note('local storage unavailable');
  const el = document.getElementById('stands');
  if (el) el.textContent = msg;
});

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch(() => {});
}
