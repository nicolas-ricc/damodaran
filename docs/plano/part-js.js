const ROLES = {datos:"Datos", elimina:"Elimina", selecciona:"Selecciona",
               valua:"Valúa", vigila:"Vigila"};
const GLIFO = {
  datos:'<svg width="15" height="15" viewBox="0 0 18 18" aria-hidden="true"><path d="M3 2h8l4 4v10H3z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M11 2v4h4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
  elimina:'<svg width="15" height="15" viewBox="0 0 18 18" aria-hidden="true"><path d="M4 4l10 10M14 4L4 14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  selecciona:'<svg width="15" height="15" viewBox="0 0 18 18" aria-hidden="true"><path d="M3 9.5l4 4L15 4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  valua:'<svg width="15" height="15" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="6.2" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="9" cy="9" r="2.2" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
  vigila:'<svg width="15" height="15" viewBox="0 0 18 18" aria-hidden="true"><path d="M2 11c2-4 3.5-4 5.5 0s3.5 4 5.5 0 2.5-3 3-1" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>'
};
const PIG = {datos:"--p-datos-t", elimina:"--p-elimina-t", selecciona:"--p-selecciona-t",
             valua:"--p-valua-t", vigila:"--p-vigila-t"};
const NOMBRE_PAT = {"p-registry":"Registry", "p-strategy":"Strategy",
  "p-spec":"Spec declarativo", "p-value":"Value object", "p-adapter":"Adapter",
  "p-tx":"Transacción", "p-protocol":"Protocol", "p-seam":"Costura inyectable",
  "p-source":"Procedencia"};

const ORDEN = [
  "damodaran","sec","fmp","ibkr",
  "adapters","a-download","a-parse","a-upsert","duckdb",
  "zigurat","g-cap","g-hist","g-sect","g-debt","g-cover","g-ocf","g-gw",
  "v-pe","v-ev","v-fcf","v-pbv",
  "t-rev","t-margin","t-sloan","t-roic","t-dilution",
  "story","s-hg","s-ms","s-md","s-cy","s-ds",
  "assumptions","a-growth","a-margin","a-s2c","a-wacc","a-g","a-default",
  "dcf","dcf-formula","sensitivity","sens-tornado","sens-grid",
  "flags","f-story","f-growth","f-beta","f-tv","f-country",
  "monitor","events","reports",
  "mod-cli","mod-ingest","mod-screener","mod-valuator","mod-portfolio","mod-reporting",
  "mod-reference","mod-utils","mod-config","mod-storage",
  "p-registry","p-strategy","p-spec","p-value","p-adapter","p-tx","p-protocol",
  "p-seam","p-source",
  "x-bc","x-utils","x-adapter"
].filter(k => F[k]);

const VISTAS = ["sistema","fuentes","capa-a","capa-b","capa-c","salida","codigo"];
const dlg = document.getElementById('ficha');
const cuerpo = document.getElementById('ficha-body');
const rolEl = document.getElementById('ficha-rol');
const titEl = document.getElementById('ficha-titulo');
let actual = null;
let quienAbrio = null;

/* ---------- vistas ---------- */
function mostrar(v){
  if(!VISTAS.includes(v)) return;
  VISTAS.forEach(k => {
    const s = document.getElementById('v-' + k);
    if(s) s.hidden = (k !== v);
  });
  document.querySelectorAll('.crumb').forEach(b =>
    b.setAttribute('aria-current', String(b.dataset.goto === v)));
  const nav = document.querySelector('.nav');
  if(nav) nav.scrollIntoView({block:'start',
    behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}
document.querySelectorAll('.crumb').forEach(b =>
  b.addEventListener('click', () => mostrar(b.dataset.goto)));

/* ---------- ficha ---------- */
function pintar(id, foco){
  const d = F[id];
  if(!d) return;
  actual = id;
  rolEl.innerHTML = GLIFO[d.role] + ROLES[d.role];
  rolEl.style.color = 'var(' + PIG[d.role] + ')';
  titEl.textContent = d.titulo;

  const izq = ['<p class="col-h">La idea</p>'];
  if(d.lead) izq.push('<p><strong>' + d.lead + '</strong></p>');
  (d.idea || []).forEach(p => izq.push('<p>' + p + '</p>'));
  if(d.num) izq.push('<div class="num">' + d.num + '</div>');

  const der = ['<p class="col-h">En el programa</p>'];
  const m = (typeof META !== 'undefined' && META[id]) || null;
  const s = (m && typeof SIMB !== 'undefined' && SIMB[m.sym]) || null;
  if(s){
    der.push('<div class="firma">' + s.firma.replace(/</g,'&lt;') + '</div>');
    der.push('<p class="donde">' + s.donde + '</p>');
  }
  if(d.code && d.code.where && d.code.where.length){
    der.push('<div class="where">' + d.code.where.map(
      ([k, v]) => '<div><span>' + k + '</span>' + v + '</div>').join('') + '</div>');
  }
  if(s){
    der.push('<h4>Lugar en la arquitectura</h4>');
    der.push('<div class="where"><div><span>paquete</span>' + s.paquete + '/</div>' +
      '<div><span>depende de</span>' + (s.depende.length ? s.depende.join(', ') : 'nada') + '</div>' +
      '<div><span>lo usan</span>' + (s.usan.length ? s.usan.join(', ') : 'nadie') + '</div></div>');
  }
  if(m && m.pat && m.pat.length){
    der.push('<h4>Patrones que usa</h4><ul class="pats">' + m.pat.map(k =>
      '<li><button type="button" class="pat" data-ir="' + k + '">' +
      (NOMBRE_PAT[k] || k) + '</button></li>').join('') + '</ul>');
  }
  (d.code && d.code.notes || []).forEach(p => der.push('<p>' + p + '</p>'));

  let html = '<div class="ficha-cols"><div>' + izq.join('') + '</div><div>' +
             der.join('') + '</div></div>';
  if(d.caveat) html += '<p class="caveat">' + d.caveat + '</p>';

  const i = ORDEN.indexOf(id);
  html += '<div class="ficha-nav">' +
    '<button type="button" data-ir="' + (i > 0 ? ORDEN[i-1] : '') + '"' +
      (i <= 0 ? ' disabled' : '') + '>&larr; anterior</button>' +
    '<button type="button" data-ir="' + (i < ORDEN.length-1 ? ORDEN[i+1] : '') + '"' +
      (i >= ORDEN.length-1 ? ' disabled' : '') + '>siguiente &rarr;</button>' +
    '</div>';
  cuerpo.innerHTML = html;
  const inner = dlg.querySelector('.ficha-inner');
  if(inner) inner.scrollTop = 0;
  // una firma que scrollea tiene que ser alcanzable por teclado
  cuerpo.querySelectorAll('.firma').forEach(f => {
    if(f.scrollWidth > f.clientWidth + 1){
      f.tabIndex = 0;
      f.setAttribute('role', 'region');
      f.setAttribute('aria-label', 'Firma, se desplaza en horizontal');
    }
  });
  if(foco) titEl.focus();
}

function abrir(id, origen){
  if(!F[id]) return;
  if(!dlg.open){
    quienAbrio = origen || document.activeElement;
    dlg.showModal();
    pintar(id, false);
  } else {
    pintar(id, true);
  }
}

cuerpo.addEventListener('click', e => {
  const b = e.target.closest('[data-ir]');
  if(!b || !b.dataset.ir) return;
  pintar(b.dataset.ir, true);
});
document.getElementById('ficha-close').addEventListener('click', () => dlg.close());
dlg.addEventListener('click', e => { if(e.target === dlg) dlg.close(); });
dlg.addEventListener('close', () => {
  if(quienAbrio && document.contains(quienAbrio)) quienAbrio.focus();
  quienAbrio = null;
});

/* ---------- piezas activables ---------- */
function activar(el){
  const fid = el.dataset.ficha || el.dataset.node;
  if(fid && F[fid]){ abrir(fid, el); return; }
  const capa = el.dataset.layer;
  if(capa) mostrar(capa);
}

function cablear(el){
  el.classList.add('hot');
  if(!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
  if(!el.hasAttribute('role')) el.setAttribute('role', 'button');
  el.addEventListener('click', () => activar(el));
  el.addEventListener('keydown', e => {
    if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); activar(el); }
  });
}

document.querySelectorAll('[data-ficha]').forEach(cablear);
document.querySelectorAll('#v-sistema .slab, #v-sistema .lyr-lbl, #v-sistema .blk')
  .forEach(cablear);

/* ---------- resaltado del camino en el nivel 1 ---------- */
const iso = document.getElementById('svg-sistema');
if(iso){
  const marcar = capa => {
    iso.querySelectorAll('.is-lit').forEach(x => x.classList.remove('is-lit'));
    if(!capa){ iso.classList.remove('is-dimmed'); return; }
    iso.classList.add('is-dimmed');
    iso.querySelectorAll('.layer[data-layer="' + capa + '"]')
       .forEach(x => x.classList.add('is-lit'));
  };
  iso.querySelectorAll('.slab, .lyr-lbl').forEach(el => {
    const capa = el.dataset.layer;
    el.addEventListener('mouseenter', () => marcar(capa));
    el.addEventListener('focus', () => marcar(capa));
    el.addEventListener('mouseleave', () => marcar(null));
    el.addEventListener('blur', () => marcar(null));
  });
}

/* ---------- teclado ---------- */
document.addEventListener('keydown', e => {
  if(!dlg.open) return;
  if(e.key === 'ArrowRight' || e.key === 'ArrowLeft'){
    const i = ORDEN.indexOf(actual);
    if(i < 0) return;
    const j = e.key === 'ArrowRight' ? i + 1 : i - 1;
    if(j >= 0 && j < ORDEN.length){ e.preventDefault(); pintar(ORDEN[j], true); }
  }
});
