// AI Tag Remover UI. Talks to Python through window.pywebview.api; Python pushes
// updates back by calling App.on(event, payload).
(function () {
  const ICONS = {
    upload: '<path d="M12 15V4"/><path d="m7 9 5-5 5 5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9L9.6 3.6A2 2 0 0 0 8.2 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    sparkle: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 17v4M17 19h4"/>',
    layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
    film: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    reveal: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    download: '<path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M4 20h16"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    bolt: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    eraser: '<path d="m7 21-4.3-4.3a1 1 0 0 1 0-1.4l10-10a1 1 0 0 1 1.4 0l5.6 5.6a1 1 0 0 1 0 1.4L11 21"/><path d="M22 21H7M5 11l9 9"/>',
  };
  const icon = (n) => `<svg class="i" viewBox="0 0 24 24">${ICONS[n] || ''}</svg>`;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  document.querySelectorAll('[data-icon]').forEach((el) => {
    const svg = icon(el.dataset.icon);
    if (el.tagName === 'I') el.outerHTML = svg; else el.insertAdjacentHTML('afterbegin', svg);
  });

  const items = new Map(); // id -> item
  let mode = 'beside', customDir = null, busy = false, lastDir = null;
  let api = null;
  let settings = {}, upd = null, modal = null, home = '';
  const tilde = (p) => (home && p && p.startsWith(home) ? '~' + p.slice(home.length) : p);

  // ---------- rendering ----------
  const STATUS = {
    scanning: ['', 'Scanning', true], ready: ['', 'Ready'], cleaning: ['', 'Cleaning', true],
    done: ['done', 'Clean', false, 'check'], warning: ['failed', 'Check output', false, 'alert'],
    failed: ['failed', 'Failed', false, 'alert'], unsupported: ['', 'Not supported'],
  };

  function statusPill(it) {
    let [cls, text, spin, ic] = STATUS[it.status] || ['', it.status];
    if (it.status === 'ready' && it.markers.length) { cls = 'ai'; text = 'AI tagged'; ic = 'alert'; }
    return `<span class="status ${cls} ${spin ? 'busy' : ''}">${ic ? icon(ic) : ''}${text}</span>`;
  }

  function tagChips(it) {
    if (it.status === 'scanning') return '<span class="sub">Reading metadata</span>';
    if (it.status === 'unsupported' || (it.error && it.status !== 'done')) return `<span class="err">${esc(it.error)}</span>`;
    const removed = it.status === 'done' || it.status === 'warning';
    if (!it.markers.length) {
      const n = it.blocks.length;
      return `<span class="sub">${removed ? 'Metadata removed' : `No AI tags · ${n} other metadata block${n === 1 ? '' : 's'}`}</span>`;
    }
    const shown = it.markers.slice(0, 4).map((m) => `<span class="tag ${removed && !(it.left || []).includes(m) ? 'removed' : ''}">${esc(m)}</span>`);
    if (it.markers.length > 4) shown.push(`<span class="tag more">+${it.markers.length - 4}</span>`);
    return shown.join('');
  }

  function thumbHTML(it) {
    const inner = it.thumb ? `<img src="${it.thumb}">` : icon(it.kind === 'video' ? 'film' : 'image');
    return `<div class="thumb">${inner}<span class="ext">${esc(it.ext)}</span></div>`;
  }

  function rowHTML(it) {
    return `${thumbHTML(it)}
      <div class="meta">
        <div class="title">${esc(it.name)}</div>
        <div class="tags">${tagChips(it)}</div>
      </div>
      <div class="sub" style="flex:none">${esc(it.size)}</div>
      ${statusPill(it)}
      <div class="acts">
        <button class="btn-icon" data-act="details" title="Details">${icon('eye')}</button>
        <button class="btn-icon" data-act="reveal" title="Show in folder">${icon('reveal')}</button>
        <button class="btn-icon" data-act="remove" title="Remove from list">${icon('x')}</button>
      </div>`;
  }

  function upsert(it) {
    items.set(it.id, it);
    let el = document.getElementById('row-' + it.id);
    if (!el) {
      el = document.createElement('div');
      el.className = 'row';
      el.id = 'row-' + it.id;
      el.dataset.id = it.id;
      $('#list').appendChild(el);
    }
    el.innerHTML = rowHTML(it);
    refresh();
  }

  function refresh() {
    const all = [...items.values()];
    const tagged = all.filter((i) => i.markers.length && i.status !== 'done').length;
    const done = all.filter((i) => i.status === 'done').length;
    const todo = all.filter((i) => ['ready', 'failed', 'warning'].includes(i.status)).length;
    $('#empty').classList.toggle('hidden', all.length > 0);
    $('#clear').classList.toggle('hidden', !all.length || busy);
    $('#open-out').classList.toggle('hidden', !lastDir);
    $('#stats').innerHTML = all.length ? `
      <span class="stat"><b>${all.length}</b>file${all.length === 1 ? '' : 's'}</span>
      ${tagged ? `<span class="stat warn"><b>${tagged}</b>with AI tags</span>` : ''}
      ${done ? `<span class="stat lime"><b>${done}</b>cleaned</span>` : ''}` : '';
    const btn = $('#clean-btn');
    btn.disabled = busy || !todo || (mode === 'custom' && !customDir);
    btn.querySelector('span').textContent = busy ? 'Cleaning…' : todo ? `Clean ${todo} file${todo === 1 ? '' : 's'}` : (done ? 'All clean' : 'Clean');
  }

  function toast(text, err, action) {
    const t = document.createElement('div');
    t.className = 'toast' + (err ? ' err' : '');
    t.innerHTML = icon(err ? 'alert' : 'check') + `<span>${esc(text)}</span>`;
    if (action) {
      const b = document.createElement('button');
      b.textContent = action.label;
      b.onclick = action.run;
      t.appendChild(b);
    }
    $('#toasts').appendChild(t);
    setTimeout(() => { t.style.transition = 'opacity .3s'; t.style.opacity = 0; setTimeout(() => t.remove(), 300); }, 4200);
  }

  function details(it) {
    const blocks = it.blocks.length ? it.blocks.map((b) => `<div><span class="k">${esc(b)}</span></div>`).join('') : '<div class="empty-row">None found</div>';
    const markers = it.markers.length ? it.markers.map((m) => `<div><span class="k">${esc(m)}</span><span class="v">${['done', 'warning'].includes(it.status) && !(it.left || []).includes(m) ? 'Removed' : 'Found'}</span></div>`).join('') : '<div class="empty-row">None found</div>';
    const root = $('#modal-root');
    root.innerHTML = `<div class="modal-back"><div class="modal">
      <div class="modal-head">${thumbHTML(it)}<div class="t"><h2>${esc(it.name)}</h2><div class="sub"><span class="path">${esc(it.folder)}</span></div></div>${statusPill(it)}</div>
      <div class="label">AI and provenance markers</div><div class="group">${markers}</div>
      <div class="label">Metadata blocks ${['done', 'warning'].includes(it.status) ? 'removed' : 'that will be removed'}</div><div class="group">${blocks}</div>
      ${it.out ? `<div class="label">Cleaned copy</div><div class="group"><div><span class="k" style="word-break:break-all">${esc(it.out)}</span></div></div>` : ''}
      <div class="foot">${it.out ? `<button class="btn-quiet" data-m="reveal">${icon('reveal')}Show cleaned file</button>` : ''}<button class="btn-quiet" data-m="close">Done</button></div>
    </div></div>`;
    root.querySelector('.modal-back').onclick = (e) => {
      const m = e.target.closest('[data-m]');
      if (e.target.classList.contains('modal-back') || (m && m.dataset.m === 'close')) root.innerHTML = '';
      else if (m && m.dataset.m === 'reveal') api.reveal(it.out);
    };
  }


  // ---------- modals ----------
  function closeModal() { $('#modal-root').innerHTML = ''; modal = null; }
  function showModal(name, html, onClick, cls) {
    const box = modal === name && $('#modal-root .modal');
    modal = name;
    if (box) {
      // Same dialog again: swap what's inside so the dark backdrop doesn't fade in again (that read as the window blinking).
      box.className = `modal ${cls || ''}`;
      box.innerHTML = html;
    } else {
      $('#modal-root').innerHTML = `<div class="modal-back"><div class="modal ${cls || ''}">${html}</div></div>`;
    }
    $('#modal-root .modal-back').onclick = (e) => {
      if (e.target.classList.contains('modal-back')) return closeModal();
      const el = e.target.closest('[data-m]');
      if (el) onClick(el.dataset.m, el);
    };
  }
  const sw = (on) => `<span class="switch ${on ? 'on' : ''}"></span>`;
  const opt = (key, title, detail) => `<button class="opt" data-m="toggle" data-key="${key}"><div class="t"><b>${title}</b><span>${detail}</span></div>${sw(settings[key])}</button>`;
  const ago = (iso) => {
    if (!iso) return 'Never checked';
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return 'Checked just now';
    if (s < 3600) return `Checked ${Math.round(s / 60)} min ago`;
    if (s < 86400) return `Checked ${Math.round(s / 3600)} h ago`;
    return 'Checked ' + new Date(iso).toLocaleDateString();
  };
  function updateLine() {
    if (!upd) return ['', ''];
    switch (upd.phase) {
      case 'checking': return ['Checking for updates…', ''];
      case 'uptodate': return ["You're up to date", 'ok'];
      case 'available': return [`Version ${upd.latest} is available`, 'ok'];
      case 'downloading': return [`Downloading ${upd.latest}… ${Math.round(upd.progress * 100)}%`, ''];
      case 'ready': return [`Version ${upd.latest} is ready to install`, 'ok'];
      case 'installing': return ['Installing…', ''];
      case 'failed': return [upd.error || 'Update failed', 'bad'];
      default: return [ago(upd.last_checked), ''];
    }
  }
  function renderUpdateRow() {
    const el = $('#upd-row');
    if (!el) return;
    const [line, cls] = updateLine();
    const has = upd && ['available', 'downloading', 'ready'].includes(upd.phase);
    el.innerHTML = `<div class="t"><b>Tag ${esc(upd ? upd.current : '')}</b><span class="${cls}">${esc(line)}</span></div>
      ${has ? `<button class="btn-quiet" data-m="see-update">${icon('download')}See update</button>` : `<button class="btn-quiet" data-m="check" ${upd && upd.phase === 'checking' ? 'disabled' : ''}>${icon('refresh')}Check now</button>`}`;
  }
  function openSettings() {
    showModal('settings', `
      <div class="modal-title"><h2>Settings</h2><button class="btn-icon" data-m="close">${icon('x')}</button></div>
      <div class="label">Cleaning</div>
      <div class="group">${opt('open_after', 'Open the folder when cleaning finishes', 'Shows the cleaned copies in Finder or Explorer')}</div>
      <div class="label">Updates</div>
      <div class="group">
        <div class="ver-row" id="upd-row"></div>
        ${opt('auto_check', 'Check for updates automatically', 'Looks for a new version at launch and every few hours')}
        ${opt('auto_install', 'Download and install updates automatically', 'Downloads in the background and installs when you quit')}
      </div>
      <div class="label">About</div>
      <div class="about">Tag removes metadata only: C2PA Content Credentials, IPTC AI labels, XMP/EXIF history and video container tags. Invisible watermarks inside the pixels, such as SynthID, aren't metadata and stay.</div>
      <div class="foot"><button class="link" data-m="page">Release notes on GitHub</button><button class="link" data-m="welcome" style="margin-right:0">Show welcome screen</button></div>`,
      async (m, el) => {
        if (m === 'close') closeModal();
        else if (m === 'toggle') {
          const k = el.dataset.key;
          settings = await api.set_setting(k, !settings[k]);
          el.querySelector('.switch').classList.toggle('on', !!settings[k]);
        } else if (m === 'check') { upd = await api.check_updates(); renderUpdateRow(); renderPill(); }
        else if (m === 'see-update') openUpdate();
        else if (m === 'page') api.open_url(upd ? upd.page : '');
        else if (m === 'welcome') { closeModal(); showWelcome(); }
      }, 'settings');
    renderUpdateRow();
  }

  function renderPill() {
    const p = $('#update-pill');
    if (!upd || !['available', 'downloading', 'ready', 'installing'].includes(upd.phase)) { p.classList.add('hidden'); return; }
    p.classList.remove('hidden');
    p.innerHTML = upd.phase === 'ready' ? `${icon('refresh')}Restart to update` :
      upd.phase === 'downloading' ? `${icon('download')}Updating ${Math.round(upd.progress * 100)}%` :
      upd.phase === 'installing' ? `${icon('refresh')}Installing…` : `${icon('download')}Update to ${esc(upd.latest)}`;
  }

  // Progress ticks arrive several times a second: only the bar and its line change.
  function patchUpdateProgress() {
    const bar = $('#modal-root .progress > div');
    const line = $('#modal-root .update-hero p');
    if (!bar || !line) return false;
    const pct = Math.round((upd.progress || 0) * 100);
    bar.style.width = pct + '%';
    line.textContent = `Downloading… ${pct}%`;
    return true;
  }

  function openUpdate() {
    if (!upd) return;
    const ph = upd.phase;
    const pct = Math.round((upd.progress || 0) * 100);
    const sub = ph === 'ready' ? 'Downloaded and ready. Restart now, or it installs the next time you quit.' :
      ph === 'downloading' ? `Downloading… ${pct}%` : ph === 'installing' ? 'Installing and restarting…' :
      ph === 'failed' ? (upd.error || 'Something went wrong.') : ph === 'uptodate' ? "You're on the newest version." :
      `You have ${esc(upd.current)}.` + (upd.can_install ? '' : ' This copy runs from source, so the download page opens instead.');
    const primary = ph === 'ready' ? `<button class="btn-primary inline" data-m="install">${icon('refresh')}Restart to update</button>` :
      ph === 'available' || ph === 'failed' ? `<button class="btn-primary inline" data-m="${upd.can_install ? 'download' : 'page'}">${icon('download')}${upd.can_install ? 'Download update' : 'Open download page'}</button>` : '';
    showModal('update', `
      <div class="update-hero">
        <div class="logomark lg"><span class="mark" style="--size:30px">tag<i class="strike"></i></span></div>
        <div><h2>${upd.latest ? 'Tag ' + esc(upd.latest) : 'Updates'}</h2><p class="${ph === 'failed' ? 'err' : ''}">${sub}</p></div>
      </div>
      ${ph === 'downloading' ? `<div class="progress"><div style="width:${pct}%"></div></div>` : ''}
      ${upd.notes ? `<div class="label">What's new</div><div class="notes">${esc(upd.notes)}</div>` : ''}
      <div class="foot"><button class="link" data-m="page">View on GitHub</button><button class="btn-quiet" data-m="close">Later</button>${primary}</div>`,
      (m) => {
        if (m === 'close') closeModal();
        else if (m === 'install') api.install_update();
        else if (m === 'download') api.download_update();
        else if (m === 'page') api.open_url(upd.page);
      });
  }

  // ---------- welcome (first launch) ----------
  function showWelcome() {
    const w = $('#welcome');
    let page = 0;
    const pages = [
      () => `<div class="logomark lg" style="width:96px;height:96px;border-radius:26px"><span class="mark" style="--size:38px">tag<i class="strike"></i></span></div>
        <h1>Welcome to Tag</h1>
        <p class="lead">Takes AI-generation and Content Credential tags off your photos and videos<br>before you post them to YouTube or Instagram.</p>
        <div class="facts">
          <div class="card fact">${icon('bolt')}<b>Lossless</b><span>Nothing is re-encoded. Pixels, audio and video stay identical.</span></div>
          <div class="card fact">${icon('lock')}<b>Originals untouched</b><span>Clean copies are saved separately. Your files never change.</span></div>
          <div class="card fact">${icon('shield')}<b>Private</b><span>Cleaning happens on this computer. Your files are never uploaded.</span></div>
        </div>`,
      () => `<h1>Stay up to date</h1>
        <p class="lead">New versions arrive from GitHub with support for more apps and formats.</p>
        <div class="group">
          ${opt('auto_check', 'Check for updates automatically', 'Looks for a new version at launch and every few hours')}
          ${opt('auto_install', 'Download and install updates automatically', 'Downloads in the background and installs when you quit')}
        </div>`,
    ];
    const render = () => {
      w.innerHTML = `<div class="glow"></div><div class="dots">${pages.map((_, i) => `<i class="${i <= page ? 'on' : ''} ${i === page ? 'cur' : ''}"></i>`).join('')}</div>
        <div class="page">${pages[page]()}</div>
        <div class="foot">${page ? '<button class="btn-quiet" data-w="back">Back</button>' : ''}
          <button class="btn-primary" data-w="next">${page === pages.length - 1 ? 'Get started' : 'Continue'}</button></div>`;
    };
    w.onclick = async (e) => {
      const t = e.target.closest('[data-w],[data-m]');
      if (!t) return;
      if (t.dataset.m === 'toggle') {
        const k = t.dataset.key;
        settings = await api.set_setting(k, !settings[k]);
        t.querySelector('.switch').classList.toggle('on', !!settings[k]);
      } else if (t.dataset.w === 'back') { page--; render(); }
      else if (t.dataset.w === 'next') {
        if (page < pages.length - 1) { page++; render(); }
        else { w.classList.add('hidden'); settings = await api.set_setting('welcomed', true); }
      }
    };
    render();
    w.classList.remove('hidden');
  }

  // ---------- events from Python ----------
  window.App = {
    on(event, p) {
      if (event === 'upsert') upsert(p);
      else if (event === 'busy') {
        busy = p.busy;
        $('#progress').classList.toggle('hidden', !busy);
        if (busy) $('#progress > div').style.width = '0%';
        refresh();
      } else if (event === 'progress') $('#progress > div').style.width = (100 * p.done / p.total) + '%';
      else if (event === 'finished') {
        if (p.dir) { lastDir = p.dir; if (mode !== 'custom') $('#save-path').textContent = tilde(p.dir); }
        refresh();
        const failed = p.total - p.ok;
        toast(failed ? `Cleaned ${p.ok} of ${p.total} files` : `Cleaned ${p.ok} file${p.ok === 1 ? '' : 's'}`, !!failed,
          p.dir ? { label: 'Show', run: () => api.reveal(p.dir) } : null);
      } else if (event === 'toast') toast(p.text, p.err);
      else if (event === 'update') {
        const prev = upd && upd.phase;
        upd = p;
        renderPill();
        if (modal === 'update' && !(prev === 'downloading' && p.phase === 'downloading' && patchUpdateProgress())) openUpdate();
        else if (modal === 'settings') renderUpdateRow();
        if (prev !== 'ready' && p.phase === 'ready' && modal !== 'update')
          toast(`Version ${p.latest} is ready`, false, { label: 'Restart', run: () => api.install_update() });
      }
    },
  };

  // ---------- user actions ----------
  $('#add-files').onclick = () => api.pick_files();
  $('#dropzone').onclick = () => api.pick_files();
  $('#add-folder').onclick = () => api.pick_folder();
  $('#clean-btn').onclick = () => api.clean(mode, customDir);
  $('#open-out').onclick = () => lastDir && api.reveal(lastDir);
  $('#clear').onclick = () => { api.clear(); items.clear(); $('#list').innerHTML = ''; lastDir = null; refresh(); };
  async function pickCustom() {
    const d = await api.choose_output();
    if (d) { customDir = d; api.set_setting('custom_dir', d); }
    return !!customDir;
  }
  function setMode(m) {
    mode = m;
    document.querySelectorAll('#out-mode button').forEach((x) => x.classList.toggle('on', x.dataset.mode === m));
    $('#custom-row').classList.toggle('hidden', m !== 'custom');
    $('#custom-path').textContent = tilde(customDir) || '';
    $('#save-path').textContent = m === 'custom' && customDir ? tilde(customDir) : 'a “cleaned” folder beside each file';
    refresh();
  }
  $('#out-mode').onclick = async (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.mode === 'custom' && !customDir && !(await pickCustom())) return;
    setMode(b.dataset.mode);
    api.set_setting('out_mode', mode);
  };
  $('#custom-row').onclick = async () => { if (await pickCustom()) setMode('custom'); };
  $('#save-row').onclick = () => {
    const target = mode === 'custom' && customDir ? customDir : lastDir;
    if (target) api.reveal(target);
  };
  $('#list').onclick = (e) => {
    const row = e.target.closest('.row');
    if (!row) return;
    const it = items.get(+row.dataset.id);
    const act = e.target.closest('[data-act]');
    const a = act ? act.dataset.act : 'details';
    if (a === 'details') details(it);
    else if (a === 'reveal') api.reveal(it.out || it.path);
    else if (a === 'remove' && !busy) { api.remove(it.id); items.delete(it.id); row.remove(); refresh(); }
  };
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
  $('#open-settings').onclick = () => openSettings();
  $('#update-pill').onclick = () => openUpdate();

  // Drag overlay (Python receives the actual drop with full file paths).
  let depth = 0;
  const showDrop = (on) => { $('#drop').classList.toggle('hidden', !on); document.body.classList.toggle('dragging', on); };
  document.addEventListener('dragenter', (e) => { e.preventDefault(); depth++; showDrop(true); });
  document.addEventListener('dragover', (e) => e.preventDefault());
  document.addEventListener('dragleave', () => { if (--depth <= 0) { depth = 0; showDrop(false); } });
  document.addEventListener('drop', (e) => { e.preventDefault(); depth = 0; showDrop(false); });

  // ---------- start ----------
  async function start(a) {
    api = a;
    const info = await api.info();
    document.body.classList.add(info.platform === 'darwin' ? 'mac' : info.platform.startsWith('win') ? 'win' : 'other');
    $('#version').textContent = 'v' + info.version;
    settings = info.settings || {};
    home = info.home || '';
    upd = info.update;
    if (settings.custom_dir) customDir = settings.custom_dir;
    setMode(settings.out_mode === 'custom' && customDir ? 'custom' : 'beside');
    renderPill();
    if (!settings.welcomed) setTimeout(showWelcome, 1150);
    $('#ffmpeg-note').innerHTML = info.ffmpeg ? '<i class="dot"></i>Photos and videos supported' : '<i class="dot bad"></i>Videos need ffmpeg (see README)';
    refresh();
    setTimeout(() => { $('#splash').classList.add('out'); $('#app').classList.add('in'); }, 1150);
    setTimeout(() => $('#splash').remove(), 1800);
  }

  // Demo data for previewing the UI in a plain browser (open index.html?demo).
  function demoApi() {
    const sample = [
      { name: 'higgsfield_soul_portrait.jpg', ext: 'JPG', kind: 'jpeg', size: '3.4 MB', markers: ['Higgsfield', 'C2PA Content Credentials', 'IPTC: made with generative AI', 'JUMBF manifest container', 'Content Authenticity Initiative'], blocks: ['EXIF', 'XMP', 'C2PA/JUMBF (APP11)'] },
      { name: 'vfx_pass_final_v3.mp4', ext: 'MP4', kind: 'video', size: '412.8 MB', markers: ["'Made with AI' label", 'Adobe Firefly'], blocks: ['uuid (d8fec3d6…)', 'moov/udta/meta'] },
      { name: 'thumbnail_genfill.png', ext: 'PNG', kind: 'png', size: '1.9 MB', markers: ['Adobe Generative Fill/Expand', 'IPTC: made with generative AI'], blocks: ['C2PA manifest (caBX)', 'Text/XMP (iTXt)'] },
      { name: 'IMG_4821.jpg', ext: 'JPG', kind: 'jpeg', size: '2.2 MB', markers: [], blocks: ['EXIF', 'XMP'] },
      { name: 'reel_cut_01.mov', ext: 'MOV', kind: 'video', size: '1.2 GB', markers: ['C2PA Content Credentials'], blocks: ['uuid', 'moov/udta'] },
    ];
    const grads = ['#3a2f5c,#c06c84', '#1f3b4d,#5fb3b3', '#4a3b1f,#e0a458', '#2b3a2b,#8fbf6a', '#3d1f2b,#e05a6b'];
    let n = 0;
    const thumb = (i) => 'data:image/svg+xml;utf8,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="160" height="110"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${grads[i].split(',')[0]}"/><stop offset="1" stop-color="${grads[i].split(',')[1]}"/></linearGradient></defs><rect width="160" height="110" fill="url(#g)"/><circle cx="${40 + i * 18}" cy="45" r="22" fill="rgba(255,255,255,.25)"/></svg>`);
    const add = () => sample.forEach((s, i) => {
      const it = Object.assign({ id: ++n, path: '/Users/demo/Desktop/' + s.name, folder: '/Users/demo/Desktop', status: 'scanning', left: [] }, s, { markers: [], blocks: [] });
      upsert(it);
      setTimeout(() => upsert(Object.assign({}, it, s, { status: 'ready', thumb: thumb(i) })), 300 + i * 120);
    });
    return {
      info: async () => ({ version: '1.1.0', ffmpeg: true, platform: 'darwin',
        settings: { out_mode: 'beside', open_after: false, auto_check: true, auto_install: true, welcomed: !location.search.includes('welcome') },
        update: { phase: location.search.includes('update') ? 'ready' : 'uptodate', current: '1.1.0', latest: '1.2.0', progress: 0, can_install: true,
          notes: "- Detects Kling, Runway and Veo tags\n- HEIC support\n- Faster video cleaning", page: 'https://github.com', last_checked: new Date().toISOString() } }),
      set_setting: async (k, v) => { settings[k] = v; return Object.assign({}, settings); },
      check_updates: async () => upd, download_update() {}, install_update() {}, open_url() {},
      pick_files: add, pick_folder: add, choose_output: async () => '/Users/demo/Desktop/Ready to post',
      clean: (m, d) => {
        App.on('busy', { busy: true });
        const todo = [...items.values()].filter((i) => i.status === 'ready');
        todo.forEach((it, k) => {
          setTimeout(() => upsert(Object.assign({}, it, { status: 'cleaning' })), k * 450);
          setTimeout(() => { upsert(Object.assign({}, it, { status: 'done', out: '/Users/demo/Desktop/cleaned/' + it.name })); App.on('progress', { done: k + 1, total: todo.length }); }, k * 450 + 420);
        });
        setTimeout(() => { App.on('busy', { busy: false }); App.on('finished', { ok: todo.length, total: todo.length, dir: '/Users/demo/Desktop/cleaned' }); }, todo.length * 450 + 500);
      },
      remove() {}, clear() {}, reveal() {},
      _add: add,
    };
  }

  if (window.pywebview && window.pywebview.api) start(window.pywebview.api);
  else window.addEventListener('pywebviewready', () => start(window.pywebview.api));
  if (location.search.includes('demo')) {
    const d = demoApi();
    start(d).then(() => { if (location.search.includes('filled')) d._add(); });
  }
})();
