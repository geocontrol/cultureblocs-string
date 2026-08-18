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

function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function boot() {
  const params = parseParams(window.location.search, window.location.origin);

  if (params.cssHref) {
    $('template-css').setAttribute('href', params.cssHref);
  } else {
    $('template-css').setAttribute('href', `templates/${params.template}.css`);
  }

  if (!params.actor) {
    status(`<h1>A catalogue needs an actor</h1>
      <p>Add a handle or DID to the address, for example
      <code>?actor=handle.example</code>.</p>`);
    return;
  }

  status(`<p>Loading ${esc(params.actor)}…</p>`);

  let did, pds;
  try {
    ({ did, pds } = await resolveActor(params.actor));
  } catch (e) {
    status(`<h1>Could not find ${esc(params.actor)}</h1>
      <p>${esc(e.message)}</p>
      <p>Check the handle is spelled correctly and has been published.</p>`);
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
    status(`<h1>Could not load the catalogue</h1>
      <p>${esc(e.message)}</p>
      <p><a href="">Try again</a></p>`);
    return;
  }

  if (!works.length) {
    status(`<h1>${esc(profile?.value?.name || params.actor)}</h1>
      <p>No works published yet.</p>`);
    return;
  }

  clearStatus();
  $('catalogue').innerHTML = renderCatalogue(
    profileModel(profile, params.actor),
    works.map(w => workModel(w, pds, did)));
  document.title = `${profile?.value?.name || params.actor} — Catalogue`;
}

boot();
