// Run in the head before first paint; no storage access may prevent rendering.
var themePreference = null;
var themeMedia = window.matchMedia('(prefers-color-scheme: dark)');
try { themePreference = localStorage.getItem('theme'); } catch (_) {}
if (!['light', 'dark'].includes(themePreference)) themePreference = null;
function applyTheme() {
  var theme = themePreference || (themeMedia.matches ? 'dark' : 'light');
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.documentElement.style.colorScheme = theme;
  var meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) { meta = document.createElement('meta'); meta.name = 'theme-color'; document.head.appendChild(meta); }
  meta.content = theme === 'dark' ? '#2D1D1A' : '#ECEADF';
  document.querySelectorAll('[data-theme-btn]').forEach(function (btn) {
    btn.classList.toggle('active', btn.dataset.themeBtn === theme);
    btn.setAttribute('aria-pressed', String(btn.dataset.themeBtn === theme));
  });
}
function setTheme(theme) {
  if (!['light', 'dark'].includes(theme)) return;
  themePreference = theme;
  try { localStorage.setItem('theme', theme); } catch (_) {}
  applyTheme();
}
applyTheme();
try {
  document.documentElement.classList.toggle('sidebar-collapsed', localStorage.getItem('trash-talker-sidebar-collapsed') === '1');
} catch (_) {}
themeMedia.addEventListener('change', function () { if (!themePreference) applyTheme(); });
window.addEventListener('storage', function (event) {
  if (event.key !== 'theme' && event.key !== null) return;
  themePreference = ['light', 'dark'].includes(event.newValue) ? event.newValue : null;
  applyTheme();
});
document.addEventListener('DOMContentLoaded', function () {
  applyTheme();
  document.querySelectorAll('[data-theme-btn]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      var next = btn.dataset.themeBtn;
      if (next === (document.documentElement.classList.contains('dark') ? 'dark' : 'light')) return;
      var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (!document.startViewTransition || reduce) { setTheme(next); return; }
      // Revelação circular a partir do ponto do clique.
      var box = btn.getBoundingClientRect();
      var x = e.clientX || box.left + box.width / 2, y = e.clientY || box.top + box.height / 2;
      var r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
      document.documentElement.classList.add('theme-vt');
      var t = document.startViewTransition(function () { setTheme(next); });
      t.finished.finally(function () { document.documentElement.classList.remove('theme-vt'); });
      t.ready.then(function () {
        document.documentElement.animate(
          { clipPath: ['circle(0 at ' + x + 'px ' + y + 'px)', 'circle(' + r + 'px at ' + x + 'px ' + y + 'px)'] },
          { duration: 520, easing: 'cubic-bezier(.2,.8,.2,1)', pseudoElement: '::view-transition-new(root)' }
        );
      }).catch(function () {});
    });
  });
});
