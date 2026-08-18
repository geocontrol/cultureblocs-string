// Reads seeded stands and flushes queued beads. The String is usually
// unreachable while the app is in use — a fair hall has no usable
// connectivity and the String is at home — so every call here is expected
// to fail routinely and must fail quietly.

function headers(token, json) {
  const h = json ? { 'content-type': 'application/json' } : {};
  if (token) h.authorization = `Bearer ${token}`;
  return h;
}

export async function fetchStands(url, token) {
  const r = await fetch(
    `${url.replace(/\/$/, '')}/records?type=com.cultureblocs.venue.lineup&limit=500`,
    { headers: headers(token, false) });
  if (!r.ok) throw new Error(`the String answered ${r.status}`);
  const body = await r.json();
  return Array.isArray(body) ? body : (body.records || []);
}

/* The seeded fair event, which carries the run's span and its name. Returns
 * null when the String has nothing seeded yet, so the caller can say so. */
export async function fetchFair(url, token) {
  const r = await fetch(
    `${url.replace(/\/$/, '')}/records?type=community.lexicon.calendar.event&limit=100`,
    { headers: headers(token, false) });
  if (!r.ok) throw new Error(`the String answered ${r.status}`);
  const body = await r.json();
  const rows = Array.isArray(body) ? body : (body.records || []);
  return rows.find(x => x.sourceApp === 'seed-frieze') || null;
}

/* Returns the dedupeKeys the String accepted. A `duplicate` counts as
 * accepted: the bead is already there, so holding it locally would mean
 * flushing it forever. */
export async function flush(url, token, records) {
  if (!records.length) return [];
  const r = await fetch(`${url.replace(/\/$/, '')}/records`, {
    method: 'POST',
    headers: headers(token, true),
    body: JSON.stringify({ records }),
  });
  if (!r.ok) throw new Error(`the String answered ${r.status}`);
  const body = await r.json();
  return (body.results || [])
    .filter(x => x.status === 'created' || x.status === 'duplicate')
    .map(x => x.dedupeKey);
}
