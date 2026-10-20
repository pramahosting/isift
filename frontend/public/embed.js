/*! iSift booking embed. Add one script tag to any page:
 *   <script src="https://YOUR-ISIFT/embed.js" async></script>
 * Inline:   <div data-isift-book="my-page-slug" data-name="Pat" data-email="pat@example.com"></div>
 * Button:   <button data-isift-popup="my-page-slug">Book a meeting</button>
 * Script:   iSift.open({slug:'my-page-slug', name:'Pat', email:'pat@example.com'})
 * Events:   window.addEventListener('isift:booked', e => console.log(e.detail))   // {slug, start_at, join_url, token}
 */
(function () {
  var script = document.currentScript || document.querySelector('script[src*="embed.js"]');
  var ORIGIN = script ? new URL(script.src).origin : location.origin;
  function url(o) {
    var q = new URLSearchParams({ embed: '1' }); if (o.name) q.set('name', o.name); if (o.email) q.set('email', o.email);
    return ORIGIN + '/embed/#/book/' + encodeURIComponent(o.slug) + '?' + q.toString();
  }
  function frame(o, height) {
    var f = document.createElement('iframe'); f.src = url(o); f.title = 'Book a meeting'; f.loading = 'lazy'; f.allow = 'clipboard-write';
    f.style.cssText = 'border:0;width:100%;height:' + (height || 680) + 'px;max-width:100%;background:transparent'; return f;
  }
  window.addEventListener('message', function (e) {
    if (e.origin !== ORIGIN || !e.data || typeof e.data !== 'object') return;
    if (e.data.type === 'isift:resize') document.querySelectorAll('iframe[src^="' + ORIGIN + '/embed/"]').forEach(function (f) { if (f.contentWindow === e.source && !f.dataset.fixed) f.style.height = Math.max(420, e.data.height) + 'px'; });
    if (e.data.type === 'isift:booked') window.dispatchEvent(new CustomEvent('isift:booked', { detail: e.data.booking }));
  });
  function open(o) {
    var back = document.createElement('div'); back.style.cssText = 'position:fixed;inset:0;background:#0008;z-index:2147483000;display:grid;place-items:center;padding:16px';
    var box = document.createElement('div'); box.style.cssText = 'background:#fff;border-radius:14px;width:min(960px,100%);max-height:94vh;overflow:auto;position:relative';
    var x = document.createElement('button'); x.textContent = '×'; x.setAttribute('aria-label', 'Close'); x.style.cssText = 'position:absolute;right:10px;top:6px;border:0;background:none;font-size:26px;cursor:pointer;z-index:2';
    function close() { back.remove(); document.removeEventListener('keydown', esc); }
    function esc(ev) { if (ev.key === 'Escape') close(); }
    x.onclick = close; back.onclick = function (ev) { if (ev.target === back) close(); }; document.addEventListener('keydown', esc);
    box.appendChild(x); box.appendChild(frame(o, 640)); back.appendChild(box); document.body.appendChild(back);
  }
  function init() {
    document.querySelectorAll('[data-isift-book]').forEach(function (el) { if (el.dataset.ready) return; el.dataset.ready = '1'; el.appendChild(frame({ slug: el.dataset.isiftBook, name: el.dataset.name, email: el.dataset.email }, +el.dataset.height || 0)); if (el.dataset.height) el.firstChild.dataset.fixed = '1'; });
    document.querySelectorAll('[data-isift-popup]').forEach(function (el) { if (el.dataset.ready) return; el.dataset.ready = '1'; el.addEventListener('click', function (ev) { ev.preventDefault(); open({ slug: el.dataset.isiftPopup, name: el.dataset.name, email: el.dataset.email }); }); });
  }
  window.iSift = { open: open, init: init };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
