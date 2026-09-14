/* Refs helpers that need more than the lexicon can say — a port of
 * string/app/refs.py. The validator checks a ref's shape; it cannot check
 * that an `index` lands inside the record's own text, on character
 * boundaries. Both implementations run tests/fixtures/refs-cases.json.
 *
 * CANONICAL COPY. Apps carry copies; copy outward from here.
 */

const ANNOTATION = 'com.cultureblocs.annotation';

// The text a record's ref anchors index into.
export const TEXT_FIELD = {
  'com.cultureblocs.strand': 'narrative',
  'com.cultureblocs.bead': 'note',
  [ANNOTATION]: 'note',
};

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const nonEmpty = (v) => typeof v === 'string' && v !== '';
const encoder = new TextEncoder();

// True unless `pos` falls inside a multi-byte UTF-8 sequence.
const onBoundary = (data, pos) => pos === data.length || (data[pos] & 0xc0) !== 0x80;

/** Problems with ref anchors that the lexicon cannot express. */
export function anchorProblems(nsid, body) {
  const field = TEXT_FIELD[nsid];
  if (field === undefined) return [];
  const problems = [];
  const text = body[field];
  const data = typeof text === 'string' ? encoder.encode(text) : new Uint8Array();
  const refs = Array.isArray(body.refs) ? body.refs : [];
  refs.forEach((ref, i) => {
    const idx = isObject(ref) ? ref.index : undefined;
    if (!isObject(idx)) return;
    const { byteStart: start, byteEnd: end } = idx;
    if (!Number.isInteger(start) || !Number.isInteger(end)) return; // the validator's to report
    const path = `$.refs[${i}].index`;
    if (!(start >= 0 && start <= end && end <= data.length)) {
      problems.push(`${path}: ${start}..${end} is outside ${field} (${data.length} bytes)`);
    } else if (!(onBoundary(data, start) && onBoundary(data, end))) {
      problems.push(`${path}: ${start}..${end} splits a character in ${field}`);
    }
  });
  if (isObject(body.presentation)) {
    for (const key of ['venueRef', 'eventRef']) {
      const ref = body.presentation[key];
      if (isObject(ref) && 'index' in ref) {
        problems.push(`$.presentation.${key}.index: presentation refs cannot anchor`);
      }
    }
  }
  return problems;
}

/** Map a deprecated #workRef onto a #ref with role subject. */
export function refFromWorkRef(work) {
  const descriptor = { label: work.title || work.wikidata || 'Untitled work' };
  for (const key of ['creator', 'creatorDid', 'date']) {
    if (nonEmpty(work[key])) descriptor[key] = work[key];
  }
  const ids = [];
  if (nonEmpty(work.wikidata)) ids.push({ scheme: 'wikidata', id: work.wikidata });
  if (nonEmpty(work.linkedArt)) ids.push({ scheme: 'linkedArt', id: work.linkedArt, uri: work.linkedArt });
  const acc = work.accession;
  if (isObject(acc) && typeof acc.institution === 'string' && typeof acc.id === 'string') {
    ids.push({ scheme: 'accession', id: `${acc.institution}/${acc.id}` });
  }
  const ref = { type: 'work', role: 'subject', descriptor };
  if (ids.length) ref.externalIds = ids;
  return ref;
}

/** Give an annotation's required `work` a matching subject ref (transitional). */
export function mirrorAnnotationWork(nsid, body) {
  if (nsid !== ANNOTATION || !isObject(body.work)) return body;
  const refs = Array.isArray(body.refs) ? body.refs : [];
  if (refs.some((r) => isObject(r) && r.type === 'work' && r.role === 'subject')) return body;
  return { ...body, refs: [...refs, refFromWorkRef(body.work)] };
}
