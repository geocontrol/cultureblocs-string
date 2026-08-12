// ATProto record-key helpers. rkey syntax: 1–512 chars from [A-Za-z0-9._~-],
// excluding the relative-path keys "." and "..".
const RKEY_RE = /^[A-Za-z0-9._~-]{1,512}$/;

export function isValidRkey(s) {
  return typeof s === 'string' && RKEY_RE.test(s) && s !== '.' && s !== '..';
}

export function makeRkey() {
  // 16 random chars from a 32-symbol alphabet (~80 bits). 256 is an exact
  // multiple of 32, so the modulo below is unbiased. Not time-sortable — a
  // work's rkey is a stable identity, and ordering comes from createdAt.
  const alphabet = '234567abcdefghijklmnopqrstuvwxyz';
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  let out = '';
  for (const b of bytes) out += alphabet[b % alphabet.length];
  return out;
}
