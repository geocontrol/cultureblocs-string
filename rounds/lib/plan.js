// Pure operations over seeded stands and the local plan. No DOM, no storage.
//
// The plan is deliberately NOT a record: a local stand has no CID, the
// community RSVP requires one, and inventing it would be a lie in the field
// this project relies on to make references tamper-evident. See design spec §5.

const SECTION_TAG = 'section:';

export function standModel(record) {
  const b = record?.body || {};
  const billing = Array.isArray(b.billing) ? b.billing : [];
  const gallery = billing.find(x => x?.role === 'gallery') || billing[0] || {};
  const tags = Array.isArray(b.tags) ? b.tags : [];
  const section = tags.find(t => typeof t === 'string' && t.startsWith(SECTION_TAG));
  return {
    id: record?.id || '',
    gallery: gallery.name || '',
    artists: billing.filter(x => x?.role === 'artist').map(x => x.name).filter(Boolean),
    section: section ? section.slice(SECTION_TAG.length) : '',
    note: b.note || '',
  };
}

export function bySection(stands) {
  const groups = new Map();
  for (const s of stands) {
    if (!groups.has(s.section)) groups.set(s.section, []);
    groups.get(s.section).push(s);
  }
  return [...groups.entries()]
    .map(([section, list]) => ({ section, stands: list }))
    // Largest first, but unsectioned stands always last: a group with no name
    // is a data gap, not a part of the fair.
    .sort((a, b) => (a.section === '') - (b.section === '')
      || b.stands.length - a.stands.length
      || a.section.localeCompare(b.section));
}

export function search(stands, query) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return stands;
  return stands.filter(s =>
    s.gallery.toLowerCase().includes(q)
    || s.artists.some(a => a.toLowerCase().includes(q)));
}

/* Returns a new plan; never mutates the one it was given. Toggling a stand
 * that is already planned for a DIFFERENT day moves it rather than removing
 * it — the user changed their mind about when, not whether. */
export function togglePlanned(plan, id, day) {
  const next = { ...(plan || {}) };
  const current = next[id];
  if (current && current.day === day) {
    delete next[id];
    return next;
  }
  next[id] = { day: day || null, at: null };
  return next;
}

export function isPlanned(plan, id) {
  return Boolean(plan && plan[id]);
}

/* The days the fair runs, derived from the seeded event's span. Returns []
 * for anything unparseable or reversed rather than throwing or looping — the
 * seed is data from another system and may be absent or wrong. */
export function daysBetween(startsAt, endsAt) {
  if (!startsAt || !endsAt) return [];
  const a = new Date(startsAt), b = new Date(endsAt);
  if (isNaN(a) || isNaN(b) || b < a) return [];
  const out = [];
  for (let d = new Date(Date.UTC(a.getUTCFullYear(), a.getUTCMonth(), a.getUTCDate()));
       d <= b && out.length < 60; d.setUTCDate(d.getUTCDate() + 1)) {
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

export function plannedFor(stands, plan, day) {
  return stands.filter(s => {
    const entry = plan?.[s.id];
    if (!entry) return false;
    return day == null || entry.day === day;
  });
}
