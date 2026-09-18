document.addEventListener('submit', function (e) {
  var form = e.target.closest('form[data-confirm]');
  if (form && !window.confirm(form.getAttribute('data-confirm'))) e.preventDefault();
});

function copyText(text) {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).catch(function () {});
    return;
  }
  var ta = document.createElement('textarea');
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); } catch (err) {}
  document.body.removeChild(ta);
}

function lsGet(key, fallback) {
  try { return localStorage.getItem(key); } catch (err) { return fallback; }
}

function lsSet(key, value) {
  try { localStorage.setItem(key, value); } catch (err) {}
}

// -- Assignee picker: toggle list + search + temp-save text block ------------
(function initAssigneePicker() {
  var list = document.getElementById('assignee-list');
  var search = document.getElementById('assignee-search');
  var draft = document.getElementById('assignee-draft');
  var count = document.getElementById('assignee-count');
  if (!list || !draft) return;
  var SEL_KEY = 'rmtask.assignees';
  var DRAFT_KEY = 'rmtask.assignee.draft';

  function refresh(fromDraft) {
    var checked = list.querySelectorAll('input[name=owner_open_id]:checked');
    var ids = [];
    var names = [];
    checked.forEach(function (o) {
      ids.push(o.value);
      names.push(o.getAttribute('data-name') || o.value);
    });
    if (!fromDraft) draft.value = names.join(', ');
    if (count) count.textContent = ids.length + ' selected';
    lsSet(SEL_KEY, JSON.stringify(ids));
    lsSet(DRAFT_KEY, draft.value);
  }

  var savedIds = [];
  try { savedIds = JSON.parse(lsGet(SEL_KEY, '[]') || '[]'); } catch (err) { savedIds = []; }
  var savedDraft = lsGet(DRAFT_KEY, '');
  if (savedIds.length) {
    list.querySelectorAll('input[name=owner_open_id]').forEach(function (o) {
      if (savedIds.indexOf(o.value) !== -1) o.checked = true;
    });
  } else if (savedDraft) {
    draft.value = savedDraft;
  }
  refresh(true);

  list.addEventListener('change', function () { refresh(); });
  draft.addEventListener('input', function () {
    lsSet(DRAFT_KEY, draft.value);
    var n = draft.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean).length;
    if (count) count.textContent = n + ' named';
  });
  if (search) {
    search.addEventListener('input', function () {
      var q = search.value.trim().toLowerCase();
      list.querySelectorAll('.toggle').forEach(function (label) {
        var name = (label.getAttribute('data-name') || label.textContent || '').toLowerCase();
        label.style.display = (!q || name.indexOf(q) !== -1) ? '' : 'none';
      });
    });
  }
  var copy = document.getElementById('assignee-copy');
  if (copy) copy.addEventListener('click', function () { copyText(draft.value); });
  var clear = document.getElementById('assignee-clear');
  if (clear) clear.addEventListener('click', function () {
    list.querySelectorAll('input[name=owner_open_id]:checked').forEach(function (o) { o.checked = false; });
    refresh();
  });
})();

// -- Dashboard team members: toggle + search + temp-save text block ----------
(function initMemberPanel() {
  var toggle = document.getElementById('member-toggle');
  var panel = document.getElementById('member-panel');
  var search = document.getElementById('member-search');
  var grid = document.getElementById('member-grid');
  var draft = document.getElementById('member-draft');
  var count = document.getElementById('member-count');
  if (!toggle || !panel || !grid || !draft) return;
  var HIDE_KEY = 'rmtask.members.hidden';
  var DRAFT_KEY = 'rmtask.members.draft';

  function visibleMembers() {
    var q = search ? search.value.trim().toLowerCase() : '';
    var rows = [];
    grid.querySelectorAll('.member').forEach(function (m) {
      var name = (m.getAttribute('data-member-name') || m.textContent || '').toLowerCase();
      var role = (m.getAttribute('data-member-role') || '').toLowerCase();
      var match = !q || name.indexOf(q) !== -1 || role.indexOf(q) !== -1;
      m.style.display = match ? '' : 'none';
      if (match) rows.push(m.getAttribute('data-member-name') || '');
    });
    return rows;
  }

  function refresh() {
    var rows = visibleMembers();
    draft.value = rows.join('\n');
    if (count) count.textContent = rows.length + ' shown';
    lsSet(DRAFT_KEY, draft.value);
  }

  if (lsGet(HIDE_KEY, '') === '1') {
    toggle.checked = false;
    panel.style.display = 'none';
  }
  var savedDraft = lsGet(DRAFT_KEY, '');
  if (savedDraft && !grid.querySelector('.member')) draft.value = savedDraft;
  toggle.addEventListener('change', function () {
    panel.style.display = toggle.checked ? '' : 'none';
    lsSet(HIDE_KEY, toggle.checked ? '0' : '1');
    refresh();
  });
  if (search) search.addEventListener('input', refresh);
  var copy = document.getElementById('member-copy');
  if (copy) copy.addEventListener('click', function () { copyText(draft.value); });
  refresh();
})();
