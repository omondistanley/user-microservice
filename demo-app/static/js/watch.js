/**
 * Watch demo: route-based autoplay scenes, pause, skip, prefers-reduced-motion.
 *
 * Scenes must be objects with: { id, path, title, body, durationMs }.
 * Autoplay is controlled by including this script on every watch page and
 * navigating to `scenes[next].path` with a `tourStep` query param.
 */
(function () {
  'use strict';

  var scenes = window.DEMO_SCENES || [];
  var timer = null;

  var elProgress = document.getElementById('watch-progress');
  var elTitle = document.getElementById('watch-narration-title');
  var elBody = document.getElementById('watch-narration-body');
  var elCaption = document.getElementById('watch-caption');
  var btnPause = document.getElementById('watch-pause');
  var btnNext = document.getElementById('watch-next');
  var btnSkip = document.getElementById('watch-skip-interactive');

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var paused = sessionStorage.getItem('demo_watch_paused') === '1';

  function getStepFromUrl() {
    try {
      var params = new URLSearchParams(window.location.search);
      var t = params.get('tourStep');
      if (t !== null) {
        var n = parseInt(t, 10);
        if (!isNaN(n)) return n;
      }
    } catch (e) {
      // ignore
    }

    var path = window.location.pathname;
    var idx = scenes.findIndex(function (s) { return s && s.path === path; });
    return idx >= 0 ? idx : 0;
  }

  var idx = getStepFromUrl();

  function renderScene() {
    var s = scenes[idx];
    if (!s) return;

    if (elTitle) elTitle.textContent = s.title || '';
    if (elBody) elBody.textContent = s.body || '';
    if (elCaption) elCaption.textContent = (s.title || '') + ' — ' + (s.body || '');
    if (elProgress) elProgress.textContent = 'Scene ' + (idx + 1) + ' / ' + scenes.length;

    if (timer) clearTimeout(timer);
    if (paused) return;

    var ms = reducedMotion ? Math.min(s.durationMs || 10000, 8000) : (s.durationMs || 10000);
    timer = setTimeout(function () {
      if (idx + 1 < scenes.length) goTo(idx + 1);
      else endWatch();
    }, ms);
  }

  function goTo(i) {
    var next = scenes[i];
    if (!next) return;
    if (timer) clearTimeout(timer);
    idx = i;
    var url = next.path;
    var join = (url.indexOf('?') >= 0) ? '&' : '?';
    url = url + join + 'tourStep=' + encodeURIComponent(String(i));
    window.location.href = url;
  }

  function endWatch() {
    if (timer) clearTimeout(timer);
    timer = null;
    if (elProgress) elProgress.textContent = 'Finished';
    if (btnPause) btnPause.style.display = 'none';
    if (btnNext) btnNext.style.display = 'none';
  }

  if (btnPause) {
    btnPause.addEventListener('click', function () {
      paused = !paused;
      sessionStorage.setItem('demo_watch_paused', paused ? '1' : '0');
      btnPause.textContent = paused ? 'Resume' : 'Pause';
      btnPause.setAttribute('aria-pressed', paused ? 'true' : 'false');
      if (paused) {
        if (timer) clearTimeout(timer);
      } else {
        renderScene();
      }
    });
    btnPause.textContent = paused ? 'Resume' : 'Pause';
    btnPause.setAttribute('aria-pressed', paused ? 'true' : 'false');
  }

  if (btnNext) {
    btnNext.addEventListener('click', function () {
      if (idx + 1 < scenes.length) goTo(idx + 1);
      else endWatch();
    });
  }

  if (btnSkip && btnSkip.getAttribute('href')) {
    // link navigation handles skip-to-interactive
  }

  if (scenes.length) renderScene();
})();
