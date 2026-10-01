// Keeps in-page (JavaScript) table filters across reloads -- a refresh, or the page
// reloading after an Edit/Delete/Relieve round-trip. Opt in by adding
// data-persist-filter="<name>" to an <input>, <select> or checkbox; the name must be
// unique on the page (checkboxes sharing a name are told apart by their value).
// Values live in sessionStorage per page path (same tab, like the planner's own state)
// and are replayed on load by firing input/keyup/change so the page's existing filter
// handler re-runs.
(function () {
    var PREFIX = 'persist-filter:' + window.location.pathname + ':';

    function fields() { return document.querySelectorAll('[data-persist-filter]'); }
    function isCheck(el) { return el.type === 'checkbox' || el.type === 'radio'; }
    function key(el) { return PREFIX + el.dataset.persistFilter + (isCheck(el) ? ':' + el.value : ''); }
    function read(el) { return isCheck(el) ? (el.checked ? '1' : '') : el.value; }

    function save(el) {
        try { sessionStorage.setItem(key(el), read(el)); } catch (e) {}
    }

    function restore() {
        fields().forEach(function (el) {
            var saved;
            try { saved = sessionStorage.getItem(key(el)); } catch (e) { return; }
            if (saved === null || saved === read(el)) return;
            if (isCheck(el)) el.checked = saved === '1'; else el.value = saved;
            ['input', 'keyup', 'change'].forEach(function (type) {
                el.dispatchEvent(new Event(type, { bubbles: true }));
            });
        });
    }

    function onEdit(e) {
        var el = e.target;
        if (el && el.dataset && el.dataset.persistFilter !== undefined) save(el);
    }
    document.addEventListener('input', onEdit, true);
    document.addEventListener('change', onEdit, true);
    // Catches filters a page resets in code without firing events (e.g. "Clear" buttons).
    window.addEventListener('pagehide', function () { fields().forEach(save); });

    // Run after the page's own DOMContentLoaded handlers have wired up their filters.
    function start() { setTimeout(restore, 0); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
