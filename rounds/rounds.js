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
  $('going-day').innerHTML = days.map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
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
let captureGen = 0;

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
  captureGen++;              // this sheet is now the current one; any save
                              // still in flight for a previous sheet must not
                              // touch what we're about to open
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
  const gen = captureGen;      // the sheet this save belongs to
  const owner = capturingFor;  // the stand this save belongs to — read now,
                                // not from the live capturingFor, which may
                                // point at a different stand by the time this
                                // await resolves
  el.value = '';

  const id = crypto.randomUUID();
  const now = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
  const body = beadBody({
    note,
    standUri: owner ? `spine://records/${owner.id}` : null,
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
    // The note is the only copy. If the user has moved to another sheet we
    // must not overwrite what they are typing now — but we must not drop this
    // either, so it goes back in front of them.
    const cur = el.value;
    el.value = cur ? `${note}\n\n---\n${cur}` : note;
    $('capture').classList.remove('hidden');
    $('capture-for').textContent =
      'Could not hold this note on the device — it is back in the box. '
      + (err?.message || '');
    return false;
  }

  // Only close the sheet if it's still the one this save started from — a
  // later ✎ tap may already have opened a different sheet while this save
  // was in flight, and this save has no business closing that one or
  // clearing its stand association.
  if (gen === captureGen) {
    $('capture').classList.add('hidden');
    capturingFor = null;
  }
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
let flushAgain = false;

/* Only one flush at a time. Two concurrent flushes each read the whole queue
 * and POST overlapping batches, and a note has been observed cleared locally
 * after a POST the String did not durably accept. A note that misses this
 * flush stays queued and goes out on the next one — held, never dropped —
 * so serialising costs at most a delay. A call that arrives while a flush is
 * already running sets flushAgain instead of being silently dropped: without
 * it, a note queued mid-flush has nothing left to trigger it, and it would
 * sit until the next unrelated trigger (a later save, 'online', or the next
 * boot) instead of going out right after the current flush settles. */
function flushQueue() {
  if (flushing) { flushAgain = true; return flushing; }
  flushing = doFlush().finally(() => {
    flushing = null;
    if (flushAgain) { flushAgain = false; flushQueue(); }
  });
  return flushing;
}

/* Beads are held until a String accepts them. Nothing is dropped on failure:
 * a note made in a hall is the only copy there is. */
async function doFlush() {
  const q = await store.queuedBeads(db);
  if (!q.length) return;
  try {
    const results = await flush(settings.stringUrl, settings.token, q);
    // A `duplicate` counts as accepted: the bead is already there, so
    // holding it locally would mean flushing it forever.
    const accepted = results
      .filter(x => x.status === 'created' || x.status === 'duplicate')
      .map(x => x.dedupeKey);
    const invalid = results.filter(x => x.status === 'invalid');
    if (accepted.length) {
      await store.clearQueued(db, accepted);
    }
    const remaining = await updateQueue();      // always: a partial flush must show what is still held
    if (invalid.length) {
      // An invalid bead — e.g. a note that somehow exceeds the 3000-grapheme
      // cap — would otherwise sit in the queue forever, rejected on every
      // retry with nothing on screen to say why. Surface it instead.
      note(`${remaining.length} note(s) held; ${invalid.length} rejected — `
        + invalid.map(x => (x.problems || []).join('; ')).join(' | '));
    }
  } catch {
    note(`${q.length} note(s) held — the String is not reachable`);
  }
}

/* Your own event record for the fair. You are not claiming to be Frieze —
 * you are recording that a public occasion exists and that you are attending
 * it, both of which are yours to say. The RSVP that points at this event can
 * only be written after the event is PUBLISHED, because a strongRef needs the
 * published record's at:// uri and its cid, and fabricating a cid would be a
 * lie in the field this project relies on for tamper-evidence. */
async function saveGoing() {
  const chosen = $('going-day').value;
  if (!chosen) { $('going-status').textContent = 'Choose a day first.'; return; }
  const now = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
  const rec = {
    dedupeKey: `rounds:going:${settings.fairSlug || 'frieze-london-2026'}:${chosen}`,
    type: 'community.lexicon.calendar.event',
    sourceApp: 'rounds',
    createdAt: now,
    body: {
      $type: 'community.lexicon.calendar.event',
      name: settings.fairName || 'Frieze London 2026',
      createdAt: now,
      startsAt: `${chosen}T11:00:00Z`,
      endsAt: `${chosen}T19:00:00Z`,
    },
  };
  try {
    const results = await flush(settings.stringUrl, settings.token, [rec]);
    const result = results[0];
    if (result && result.status === 'invalid') {
      $('going-status').textContent =
        'Not saved — the String rejected it: '
        + (result.problems || []).join('; ');
      return;
    }
    $('going-status').textContent =
      'Saved locally. To share it, publish the record with '
      + 'scripts/promote.py publish <record-id> --identity <name>.';
  } catch {
    // Unlike a note, this write bypasses the offline queue, so nothing is
    // held when this fails — there is nothing queued to retry automatically.
    $('going-status').textContent =
      'Not saved — the String is not reachable. Press "I\'m going" again '
      + 'once it is.';
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
  $('going-save').onclick = saveGoing;
  window.addEventListener('online', flushQueue);

  document.addEventListener('click', async e => {
    const noteBtn = e.target.closest('.note-btn');
    if (noteBtn) { await openCapture(noteBtn.dataset.note); return; }
    const btn = e.target.closest('.mark');
    // #capture-save and #capture-cancel also carry class="mark" (for shared
    // button styling) but have no data-id — without this guard they'd match
    // here too and togglePlanned(plan, undefined, day) would write a bogus
    // "undefined" key into the stored plan.
    if (!btn || !btn.dataset.id) return;
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
