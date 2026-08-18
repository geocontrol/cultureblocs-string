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

/* Posts records to the String in chunks of 100. The endpoint caps a batch at
 * 500, but one malformed record 422s the *entire* request it's part of — a
 * single 500-record POST would let one bad record take 499 good ones down
 * with it. 100 keeps that blast radius small, matching scripts/seed_frieze.py.
 *
 * Returns every result the String reported (status + problems, per record),
 * not just the accepted ones — callers need to see `invalid` results to
 * surface them rather than silently holding a note that will never go
 * through. */
export async function flush(url, token, records) {
  if (!records.length) return [];
  const results = [];
  for (let i = 0; i < records.length; i += 100) {
    const chunk = records.slice(i, i + 100);
    const r = await fetch(`${url.replace(/\/$/, '')}/records`, {
      method: 'POST',
      headers: headers(token, true),
      body: JSON.stringify({ records: chunk }),
    });
    if (!r.ok) throw new Error(`the String answered ${r.status}`);
    const body = await r.json();
    results.push(...(body.results || []));
  }
  return results;
}
