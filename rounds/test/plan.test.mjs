import { test } from 'node:test';
import assert from 'node:assert/strict';
import { standModel, bySection, search, togglePlanned, isPlanned, plannedFor, daysBetween } from '../lib/plan.js';

const rec = (id, gallery, section, artists = [], note = '') => ({
  id, body: {
    $type: 'com.cultureblocs.venue.lineup',
    billing: [{ name: gallery, role: 'gallery' },
              ...artists.map(a => ({ name: a, role: 'artist' }))],
    tags: section ? [`section:${section}`, 'seed:artworld'] : ['seed:artworld'],
    ...(note ? { note } : {}),
  },
});

test('standModel reads the gallery from the first billing entry', () => {
  const m = standModel(rec('a1', 'Alison Jacques', 'Galleries', ['Sheila Hicks']));
  assert.equal(m.id, 'a1');
  assert.equal(m.gallery, 'Alison Jacques');
  assert.deepEqual(m.artists, ['Sheila Hicks']);
  assert.equal(m.section, 'Galleries');
});

test('standModel tolerates a stand with no section and no artists', () => {
  const m = standModel(rec('a2', 'Some Gallery', null));
  assert.equal(m.section, '');
  assert.deepEqual(m.artists, []);
});

test('standModel tolerates a malformed record without throwing', () => {
  const m = standModel({ id: 'x', body: {} });
  assert.equal(m.gallery, '');
  assert.deepEqual(m.artists, []);
});

test('bySection groups and sorts sections by size, largest first', () => {
  const stands = [
    rec('1', 'A', 'Galleries'), rec('2', 'B', 'Focus'),
    rec('3', 'C', 'Galleries'), rec('4', 'D', 'Galleries'),
  ].map(standModel);
  const groups = bySection(stands);
  assert.deepEqual(groups.map(g => [g.section, g.stands.length]),
    [['Galleries', 3], ['Focus', 1]]);
});

test('bySection puts unsectioned stands last under an empty label', () => {
  const stands = [rec('1', 'A', null), rec('2', 'B', 'Focus'), rec('3', 'C', 'Focus')]
    .map(standModel);
  assert.equal(bySection(stands).at(-1).section, '');
});

test('search matches gallery name, case-insensitively', () => {
  const stands = [rec('1', 'Alison Jacques', 'Galleries'), rec('2', 'Carlos/Ishikawa', 'Focus')]
    .map(standModel);
  assert.deepEqual(search(stands, 'alison').map(s => s.id), ['1']);
  assert.deepEqual(search(stands, 'ISHIKAWA').map(s => s.id), ['2']);
});

test('search matches an artist name too', () => {
  const stands = [rec('1', 'Alison Jacques', 'Galleries', ['Sheila Hicks'])].map(standModel);
  assert.deepEqual(search(stands, 'hicks').map(s => s.id), ['1']);
});

test('search with an empty query returns everything', () => {
  const stands = [rec('1', 'A', 'Galleries'), rec('2', 'B', 'Focus')].map(standModel);
  assert.equal(search(stands, '').length, 2);
  assert.equal(search(stands, '   ').length, 2);
});

test('togglePlanned adds, then removes, and never mutates its input', () => {
  const empty = {};
  const one = togglePlanned(empty, 'a1', '2026-10-16');
  assert.deepEqual(empty, {}, 'input must not be mutated');
  assert.equal(isPlanned(one, 'a1'), true);
  assert.equal(one['a1'].day, '2026-10-16');
  const none = togglePlanned(one, 'a1', '2026-10-16');
  assert.equal(isPlanned(none, 'a1'), false);
});

test('togglePlanned on an already-planned stand with a different day moves it', () => {
  const one = togglePlanned({}, 'a1', '2026-10-16');
  const moved = togglePlanned(one, 'a1', '2026-10-17');
  assert.equal(isPlanned(moved, 'a1'), true, 'a different day re-plans, not un-plans');
  assert.equal(moved['a1'].day, '2026-10-17');
});

test('daysBetween derives the fair run from the seeded event', () => {
  assert.deepEqual(
    daysBetween('2026-10-15T00:00:00Z', '2026-10-17T23:59:59Z'),
    ['2026-10-15', '2026-10-16', '2026-10-17']);
});

test('daysBetween handles a single-day fair and rejects nonsense', () => {
  assert.deepEqual(daysBetween('2026-10-15T00:00:00Z', '2026-10-15T23:59:59Z'), ['2026-10-15']);
  assert.deepEqual(daysBetween(null, null), []);
  assert.deepEqual(daysBetween('not-a-date', '2026-10-17T00:00:00Z'), []);
  assert.deepEqual(daysBetween('2026-10-17T00:00:00Z', '2026-10-15T00:00:00Z'), [],
    'an end before the start yields nothing rather than looping');
});

test('plannedFor returns only the stands planned for that day', () => {
  const stands = [rec('1', 'A', 'Galleries'), rec('2', 'B', 'Focus'), rec('3', 'C', 'Focus')]
    .map(standModel);
  let plan = togglePlanned({}, '1', '2026-10-16');
  plan = togglePlanned(plan, '2', '2026-10-17');
  assert.deepEqual(plannedFor(stands, plan, '2026-10-16').map(s => s.id), ['1']);
  assert.deepEqual(plannedFor(stands, plan, null).map(s => s.id), ['1', '2']);
});

test('togglePlanned with no day un-plans a stand planned for a specific day', () => {
  // Reachable from the "All days" view, where the UI passes day = null.
  // A mark button that will not unmark is a bug.
  const one = togglePlanned({}, 'a1', '2026-10-16');
  const off = togglePlanned(one, 'a1', null);
  assert.equal(isPlanned(off, 'a1'), false);
});

test('togglePlanned day matrix', () => {
  const planned16 = togglePlanned({}, 'a1', '2026-10-16');
  // same day -> un-plans
  assert.equal(isPlanned(togglePlanned(planned16, 'a1', '2026-10-16'), 'a1'), false);
  // different day -> moves, still planned
  const moved = togglePlanned(planned16, 'a1', '2026-10-17');
  assert.equal(isPlanned(moved, 'a1'), true);
  assert.equal(moved['a1'].day, '2026-10-17');
  // no day -> un-plans
  assert.equal(isPlanned(togglePlanned(planned16, 'a1', null), 'a1'), false);
  // undefined behaves as null
  assert.equal(isPlanned(togglePlanned(planned16, 'a1', undefined), 'a1'), false);
  // planned with no day, toggled with no day -> un-plans
  const plannedNull = togglePlanned({}, 'a1', null);
  assert.equal(isPlanned(togglePlanned(plannedNull, 'a1', null), 'a1'), false);
});

test('standModel coerces non-string names so downstream search cannot throw', () => {
  const m = standModel({ id: 'x', body: { billing: [
    { name: 42, role: 'gallery' },
    { name: { nope: 1 }, role: 'artist' },
    { name: 'Real Artist', role: 'artist' },
  ], tags: ['section:Focus'], note: 99 } });
  assert.equal(m.gallery, '');
  assert.deepEqual(m.artists, ['Real Artist']);
  assert.equal(m.note, '');
  assert.doesNotThrow(() => search([m], 'real'));
  assert.deepEqual(search([m], 'real').map(s => s.id), ['x']);
});
