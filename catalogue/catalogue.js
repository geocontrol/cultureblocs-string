import { parseParams } from './lib/params.js';
import { resolveActor, fetchAllWorks, fetchProfile } from './lib/atproto.js';
import { profileModel, workModel, renderCatalogue } from './lib/render.js';

const $ = id => document.getElementById(id);

/* Unlike the embeds, this surface never fails silently. An embed sits on
 * someone else's page, where a stranger should not see our plumbing. A
 * catalogue IS the destination, so a blank page reads as a broken site. */
function status(html) {
  $('status').innerHTML = html;
  $('status').classList.remove('hidden');
}

function clearStatus() {
  $('status').innerHTML = '';
  $('status').classList.add('hidden');
}

/* #status is an aria-live region: fine for a transient "Loading…" line, wrong
 * for real page content. A screen-reader user landing on the needs-an-actor
 * message, an error, or the empty state must get it as page content in the
 * <main> landmark, not as a passing status announcement. Every terminal state
 * (nothing left to wait for) goes through here instead of status(). */
function terminal(html) {
  clearStatus();
  $('catalogue').innerHTML = `<div class="notice">${html}</div>`;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function loadFailure(e) {
  terminal(`<h1>Could not load the catalogue</h1>
    <p>${esc(e.message)}</p>
    <p><a href="">Try again</a></p>`);
}

async function boot() {
  const params = parseParams(window.location.search, window.location.href);

  if (params.cssHref) {
    $('template-css').setAttribute('href', params.cssHref);
  } else {
    $('template-css').setAttribute('href', `templates/${params.template}.css`);
  }

  if (!params.actor) {
    terminal(`<h1>A catalogue needs an actor</h1>
      <p>Add a handle or DID to the address, for example
      <code>?actor=handle.example</code>.</p>`);
    return;
  }

  status(`<p>Loading ${esc(params.actor)}…</p>`);

  let did, pds;
  try {
    ({ did, pds } = await resolveActor(params.actor));
  } catch (e) {
    // A genuine 4xx (getJson's err.status) means the handle really doesn't
    // resolve — the friendly, check-your-spelling message is correct. A
    // transport failure or a 5xx (no status, or a status outside 4xx) is not
    // evidence the handle is wrong and must fall through to the generic
    // load-failure message, which offers a retry link. Spec §7.
    if (e.status >= 400 && e.status < 500) {
      terminal(`<h1>Could not find ${esc(params.actor)}</h1>
        <p>${esc(e.message)}</p>
        <p>Check the handle is spelled correctly and has been published.</p>`);
    } else {
      loadFailure(e);
    }
    return;
  }

  let works = [], profile = null;
  try {
    // The works are the catalogue; the profile is a header. atproto.js rightly
    // rethrows a real profile fault rather than disguising it as "no profile",
    // but that fault must not cost the visitor the works — spec §5: "a catalogue
    // is about the works". So the policy that the profile is optional lives here.
    [works, profile] = await Promise.all([
      fetchAllWorks(pds, did),
      fetchProfile(pds, did).catch(e => {
        console.warn('profile unavailable, falling back to the handle:', e.message);
        return null;
      }),
    ]);
  } catch (e) {
    loadFailure(e);
    return;
  }

  if (!works.length) {
    terminal(`<h1>${esc(profile?.value?.name || params.actor)}</h1>
      <p>No works published yet.</p>`);
    return;
  }

  clearStatus();
  $('catalogue').innerHTML = renderCatalogue(
    profileModel(profile, params.actor),
    works.map(w => workModel(w, pds, did)));

  // A dead blob must cost its own card its image, nothing more. Spec §7.
  for (const img of $('catalogue').querySelectorAll('img')) {
    img.addEventListener('error', () => img.remove(), { once: true });
  }

  document.title = `${profile?.value?.name || params.actor} — Catalogue`;
}

boot().catch(loadFailure);
