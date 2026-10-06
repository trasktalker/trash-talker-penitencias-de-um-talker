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
    btn.addEventListener('click', function () { setTheme(btn.dataset.themeBtn); });
  });
});
