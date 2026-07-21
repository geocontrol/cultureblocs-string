/* <cultureblocs-strands> — embed published bead strands on any page.
 *
 * Usage on a static site (e.g. geekyoto.com):
 *   <script type="module" src="/cultureblocs/cultureblocs-strands.js"></script>
 *   <cultureblocs-strands src="/cultureblocs/strands.json" limit="1"></cultureblocs-strands>
 *
 * Attributes:
 *   src    — path/URL of the exported strands.json (required)
 *   limit  — show only the newest N strands (default: all)
 *
 * Theming (CSS custom properties on the element or an ancestor):
 *   --cb-ink, --cb-faint, --cb-thread, --cb-accent, --cb-card, --cb-edge, --cb-font
 *
 * The component consumes records in com.cultureblocs.* lexicon shape.
 * Today the src is a static export; when a PDS exists, a loader that
 * fetches the same shapes from public XRPC can feed the identical markup.
 */
class CultureblocsStrands extends HTMLElement {
  static get observedAttributes(){ return ['src','limit'] }
  attributeChangedCallback(){ this.#load() }
  connectedCallback(){ this.#load() }

  async #load(){
    const src = this.getAttribute('src');
    if(!src) return;
    try{
      const res = await fetch(src);
      if(!res.ok) throw new Error(res.status);
      const doc = await res.json();
      let strands = doc.strands || [];
      const limit = parseInt(this.getAttribute('limit') || '0');
      if(limit > 0) strands = strands.slice(0, limit);
      this.#render(strands, src);
    }catch(e){
      this.#shadow().innerHTML = '';   // fail silent on a public page
    }
  }

  #shadow(){ return this.shadowRoot || this.attachShadow({mode:'open'}) }

  #render(strands, src){
    const base = src.slice(0, src.lastIndexOf('/')+1);
    const esc = s => (s||'').replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
    const hhmm = iso => (iso||'').slice(11,16);
    const kindColor = {visit:'var(--cb-accent,#2B4BC7)', dwell:'#C7860F',
      encounter:'#B0326E', screening:'#0F6E6B', performance:'#5B2BC7',
      bloc:'#4A4741', read:'#2E7A4F', listen:'#C74E2B', watch:'#0F6E6B'};

    const noteHtml = note => {
      if(!note) return '';
      return note.split('\n\n').map(bk=>{
        const lines = bk.split('\n').filter(Boolean);
        const timed = lines.filter(l=>/^\d{2}:\d{2}\s/.test(l)).length;
        if(lines.length>1 && timed >= lines.length*0.7){
          return `<ul class="tracks">${lines.map(l=>{
            const m=l.match(/^(\d{2}:\d{2})\s+(.*)$/);
            return `<li>${m?`<span class="tt">${esc(m[1])}</span>${esc(m[2])}`:esc(l)}</li>`;
          }).join('')}</ul>`;
        }
        return `<p>${esc(bk)}</p>`;
      }).join('');
    };
    const item = it => {
      const isWork = it.$type==='com.cultureblocs.annotation' || it.work;
      const dot = isWork
        ? `<span class="dot sq"></span>`
        : `<span class="dot" style="background:${kindColor[it.kind]||'#6E6C66'}"></span>`;
      const head = isWork
        ? `<span class="work">${esc(it.work?.title||'Untitled work')}</span>`+
          (it.work?.creator?`<span class="artist"> — ${esc(it.work.creator)}</span>`:'')
        : (it.subject?.name?`<span class="work">${esc(it.subject.name)}</span>`:'');
      const media = (it.media||[]).map(m=>
        `<img loading="lazy" src="${esc(base+m.uri)}" alt="${esc(m.alt||'')}">`).join('');
      const links = (it.links||[]).map(l=>
        `<a href="${esc(l.uri)}" target="_blank" rel="noopener">${esc(l.title||'link')}</a>`).join(' ');
      return `<li>
        <time>${hhmm(it.createdAt)}</time>${dot}
        <div class="body">${head}
          ${noteHtml(it.note)}
          ${media?`<div class="media">${media}</div>`:''}
          ${links?`<div class="links">${links}</div>`:''}
        </div></li>`;
    };

    const strand = b => `<article>
      <header>
        <h3>${esc(b.strand.title||'A day out')}</h3>
        <div class="meta">${esc((b.strand.day||b.strand.createdAt||'').slice(0,10))}${
          b.strand.place?.name?` · ${esc(b.strand.place.name)}`:''}${
          (b.strand.links||[]).map(l=>` · <a href="${esc(l.uri)}" target="_blank" rel="noopener">${esc(l.title||'event')}</a>`).join('')}</div>
        ${b.strand.narrative?`<p class="narrative">${esc(b.strand.narrative)}</p>`:''}
      </header>
      <ul class="stops">${b.items.map(item).join('')}</ul>
    </article>`;

    this.#shadow().innerHTML = `<style>
      :host{display:block;font-family:var(--cb-font,inherit);color:var(--cb-ink,#1B1D22)}
      article{background:var(--cb-card,transparent);border-left:3px solid var(--cb-ink,#1B1D22);
        padding:0 0 .4rem 1.1rem;margin:0 0 1.8rem}
      h3{margin:0;font-size:1.05em;letter-spacing:.02em}
      .meta{font-size:.78em;color:var(--cb-faint,#8A8880);margin:.15rem 0 .6rem}
      .meta a{color:var(--cb-accent,#2B4BC7)}
      .narrative{margin:.2rem 0 .8rem;font-style:italic}
      ul{list-style:none;margin:0;padding:0}
      .stops{position:relative}
      .stops::before{content:"";position:absolute;left:3.05rem;top:.3rem;bottom:.3rem;
        width:2px;background:var(--cb-thread,#C9C7C0)}
      .stops>li{position:relative;display:grid;grid-template-columns:2.4rem 1.4rem 1fr;
        gap:.15rem;padding:0 0 1.05rem;align-items:start}
      time{font-size:.72em;color:var(--cb-faint,#8A8880);text-align:right;
        padding-top:.2em;font-variant-numeric:tabular-nums}
      .dot{width:11px;height:11px;border-radius:50%;margin:.28em auto 0;display:block;
        box-shadow:0 0 0 3px var(--cb-card,#fff0)}
      .dot.sq{border-radius:2px;background:transparent;border:2px solid var(--cb-ink,#1B1D22);
        width:9px;height:9px}
      .body p{margin:.1rem 0 0;font-size:.92em;line-height:1.45;white-space:pre-line}
      .tracks{margin:.4rem 0 0;font-size:.8em;line-height:1.6}
      .tracks li{display:block;padding:0}
      .tt{font-variant-numeric:tabular-nums;color:var(--cb-faint,#8A8880);
        margin-right:.55em;font-size:.92em}
      .work{font-weight:600;font-size:.92em}
      .artist{font-style:italic;font-size:.88em}
      .media{display:flex;gap:.4rem;flex-wrap:wrap;margin-top:.4rem}
      .media img{height:88px;border-radius:4px;border:1px solid var(--cb-edge,#E4E2DB)}
      .links{margin-top:.25rem;font-size:.8em}
      .links a{color:var(--cb-accent,#2B4BC7)}
    </style>
    ${strands.map(strand).join('') || ''}`;
  }
}
customElements.define('cultureblocs-strands', CultureblocsStrands);
