// Pure bead construction. Deliberately the SAME shape Pocket produces, so the
// two authoring paths stay semantically identical even though their UIs differ.

export function makeDedupeKey(id) {
  return `rounds:${id}`;
}

export function beadBody(f, now) {
  const body = {
    $type: 'com.cultureblocs.bead',
    kind: 'visit',
    createdAt: now,
  };
  const note = String(f.note || '').trim();
  if (note) body.note = note;
  if (f.standUri) body.subject = { uri: f.standUri };
  const tags = [];
  if (f.fairSlug) tags.push(`fair:${f.fairSlug}`);
  if (tags.length) body.tags = tags.slice(0, 8);
  // No geo, no provenance: Rounds is used in a public hall and must not
  // quietly record where someone was standing.
  return body;
}
