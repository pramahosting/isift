/* iSift task pane for Outlook (message and appointment compose). Plain JavaScript, no build step.
   The iSift address and API address come from the page address, so the same files work wherever iSift is installed. */
(function () {
  var params = new URLSearchParams(location.search);
  var API = params.get('api') || (location.origin + '/api/v1');
  var HOME = location.origin + '/';
  var $ = function (id) { return document.getElementById(id); };
  var item = null;

  function say(text, bad) { var m = $('msg'); m.hidden = !text; m.textContent = text || ''; m.className = 'msg' + (bad ? ' err' : ''); }
  function getKey() { try { return Office.context.roamingSettings.get('isiftKey') || localStorage.getItem('isiftKey') || ''; } catch (e) { return ''; } }
  function setKey(v) {
    try { localStorage.setItem('isiftKey', v); } catch (e) {}
    try { if (v) Office.context.roamingSettings.set('isiftKey', v); else Office.context.roamingSettings.remove('isiftKey'); Office.context.roamingSettings.saveAsync(); } catch (e) {}
  }
  function call(path, opts) {
    opts = opts || {};
    return fetch(API + path, { method: opts.method || 'GET', headers: { 'Authorization': 'Bearer ' + getKey(), 'Content-Type': 'application/json' }, body: opts.body ? JSON.stringify(opts.body) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Request failed (' + r.status + ')'); return d; }); });
  }
  function insertHtml(html) {
    return new Promise(function (res, rej) { item.body.setSelectedDataAsync(html, { coercionType: Office.CoercionType.Html }, function (r) { r.status === Office.AsyncResultStatus.Succeeded ? res() : rej(new Error(r.error.message)); }); });
  }
  function getSubject() {
    return new Promise(function (res) { try { item.subject.getAsync(function (r) { res(r.status === Office.AsyncResultStatus.Succeeded ? (r.value || '') : ''); }); } catch (e) { res(''); } });
  }
  function setLocation(text) {
    return new Promise(function (res) { try { if (item.location && item.location.setAsync) item.location.setAsync(text, function () { res(); }); else res(); } catch (e) { res(); } });
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  function show() {
    var has = !!getKey(); $('setup').hidden = has; $('app').hidden = !has;
    if (has) loadPages();
  }
  function loadPages() {
    call('/booking-types').then(function (list) {
      var box = $('pages'); box.innerHTML = '';
      var live = list.filter(function (p) { return p.active; });
      if (!live.length) { box.textContent = 'You have no booking pages yet. Create one in iSift under Meetings > Scheduling.'; return; }
      live.forEach(function (p) {
        var link = HOME + '#/book/' + p.slug;
        var row = document.createElement('div'); row.className = 'row';
        row.innerHTML = '<div><b>' + esc(p.title) + '</b><small>' + p.duration_minutes + ' minutes</small></div>';
        var b = document.createElement('button'); b.textContent = 'Insert link';
        b.onclick = function () { insertHtml('<p>Book a time with me: <a href="' + esc(link) + '">' + esc(p.title) + '</a></p>').then(function () { say('Link inserted.'); }).catch(function (e) { say(e.message, true); }); };
        row.appendChild(b); box.appendChild(row);
      });
    }).catch(function (e) {
      if (/key|valid|revoked|owner/i.test(e.message)) { setKey(''); show(); say(e.message, true); } else say(e.message, true);
    });
  }
  function addMeeting() {
    var b = $('meet'); b.disabled = true; say('Creating the meeting…');
    getSubject().then(function (subject) {
      return call('/rooms', { method: 'POST', body: { title: subject || 'iSift meeting', base_url: HOME } }).then(function (r) {
        var html = '<p><b>Join the iSift video meeting</b><br><a href="' + esc(r.url) + '">' + esc(r.url) + '</a>' + (r.passcode ? '<br>Passcode: ' + esc(r.passcode) : '') + '</p>';
        return setLocation(r.url).then(function () { return insertHtml(html); }).then(function () { say('The iSift meeting was added.'); });
      });
    }).catch(function (e) { say(e.message, true); }).then(function () { b.disabled = false; });
  }

  Office.onReady(function () {
    item = Office.context.mailbox && Office.context.mailbox.item;
    $('save').onclick = function () { var v = $('key').value.trim(); if (!/^isift_pat_/.test(v)) { say('That does not look like an iSift access key.', true); return; } setKey(v); say(''); show(); };
    $('meet').onclick = addMeeting;
    $('disc').onclick = function (e) { e.preventDefault(); setKey(''); show(); say('Disconnected.'); };
    show();
  });
})();
