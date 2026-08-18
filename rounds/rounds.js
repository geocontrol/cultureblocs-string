import * as store from './lib/store.js';
import { standModel, bySection, search, togglePlanned, isPlanned, plannedFor, daysBetween } from './lib/plan.js';
import { beadBody, makeDedupeKey } from './lib/records.js';
import { fetchStands, fetchFair, flush } from './lib/string.js';

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
  await updateQueue();
  flushQueue();
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
      netNote(`${stands.length} stands cached`);
    }
  } catch {
    netNote('offline — using the cached plan');   // expected, not an error
  }
}

function note(msg) { $('queue-status').textContent = msg; }
// Separate channel from note(): the footer's queue-status is the only place
// that tells someone their note survived, so the stands/fair fetch status
// must not be able to clobber it by finishing last.
function netNote(msg) { $('net-status').textContent = msg; }

function standRow(s) {
  const on = isPlanned(plan, s.id);
  return `<div class="stand">
    <div class="body">
      <div class="g">${esc(s.gallery)}</div>
      ${s.artists.length ? `<div class="a">${esc(s.artists.slice(0, 4).join(', '))}</div>` : ''}
    </div>
    <button class="mark" data-id="${esc(s.id)}" aria-pressed="${on}">${on ? '★' : '☆'}</button>
    <button class="mark note-btn" data-note="${esc(s.id)}">✎</button>
  </div>`;
}

let capturingFor = null;

async function openCapture(id) {
  // Tapping ✎ elsewhere with a note in progress must not destroy it. The sheet
  // has no backdrop and the list stays tappable, so this is an ordinary slip
  // while walking the hall — and a note made at a fair is the only copy there
  // is. Keep it rather than asking; a confirm dialog here is another way to
  // lose it.
  if (!$('capture').classList.contains('hidden') && $('capture-note').value.trim()) {
    const saved = await saveCapture();
    // saveCapture failed to hold the in-progress note: it left the sheet open
    // with the text intact and said so. Don't paper over that by clearing the
    // textarea for a different stand.
    if (!saved) return;
  }
  const s = stands.find(x => x.id === id);
  capturingFor = s || null;
  $('capture-for').textContent = s ? `Note on ${s.gallery}` : 'Note';
  $('capture-note').value = '';
  $('capture').classList.remove('hidden');
  $('capture-note').focus();
}

async function saveCapture() {
  const el = $('capture-note');
  const note = el.value.trim();
  if (!note) { $('capture').classList.add('hidden'); return true; }

  // Clear synchronously, before any await. queueBead crosses a real task
  // boundary, so anything still readable in the textarea during that window
  // can be read a second time by another tap and queued as a second bead —
  // one note typed once becoming two on the network. Emptying the box first
  // removes the window entirely; the text lives in `note` until it is safe.
  el.value = '';

  const id = crypto.randomUUID();
  const now = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
  const body = beadBody({
    note,
    standUri: capturingFor ? `spine://records/${capturingFor.id}` : null,
    fairSlug: settings.fairSlug || 'frieze-london-2026',
  }, now);

  try {
    await store.queueBead(db, {
      dedupeKey: makeDedupeKey(id),
      type: 'com.cultureblocs.bead',
      sourceApp: 'rounds',
      createdAt: now,
      body,
    });
  } catch (err) {
    // Put the note back in the box. It is the only copy, and the user must be
    // able to see it and try again.
    el.value = note;
    $('capture-for').textContent =
      'Could not hold this note on the device — keep this screen open. '
      + (err?.message || '');
    return false;
  }

  $('capture').classList.add('hidden');
  capturingFor = null;
  await updateQueue();
  flushQueue();          // best-effort; it stays queued if the String is away
  return true;
}

async function updateQueue() {
  const q = await store.queuedBeads(db);
  note(q.length ? `${q.length} note(s) held on this phone` : 'ready');
  return q;
}

let flushing = null;

/* Only one flush at a time. Two concurrent flushes each read the whole queue
 * and POST overlapping batches, and a note has been observed cleared locally
 * after a POST the String did not durably accept. A note that misses this
 * flush stays queued and goes out on the next one — held, never dropped —
 * so serialising costs at most a delay. */
function flushQueue() {
  if (flushing) return flushing;
  flushing = doFlush().finally(() => { flushing = null; });
  return flushing;
}

/* Beads are held until a String accepts them. Nothing is dropped on failure:
 * a note made in a hall is the only copy there is. */
async function doFlush() {
  const q = await store.queuedBeads(db);
  if (!q.length) return;
  try {
    const accepted = await flush(settings.stringUrl, settings.token, q);
    if (accepted.length) {
      await store.clearQueued(db, accepted);
    }
    await updateQueue();      // always: a partial flush must show what is still held
  } catch {
    note(`${q.length} note(s) held — the String is not reachable`);
  }
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
  $('capture-cancel').onclick = () => { $('capture').classList.add('hidden'); capturingFor = null; };
  $('capture-save').onclick = saveCapture;
  window.addEventListener('online', flushQueue);

  document.addEventListener('click', async e => {
    const noteBtn = e.target.closest('.note-btn');
    if (noteBtn) { await openCapture(noteBtn.dataset.note); return; }
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
