// Auto-insert a subtle CTA bar below the first video/iframe with class .page-video or the first <video> / iframe[data-video]
(function () {
  function createCTAHtml(id) {
    return '\
      <div class="video-cta-bar mt-4 rounded-lg border border-gray-100 bg-white/90 shadow-sm p-4 flex items-center gap-4" data-video-cta>\
        <div class="flex items-center gap-3">\
          <div class="w-12 h-12 rounded-md bg-primary/10 flex items-center justify-center">\
            <span class="material-symbols-outlined text-primary text-2xl">play_arrow</span>\
          </div>\
        </div>\
        <div class="flex-1">\
          <p class="text-sm text-deep-charcoal font-bold mb-1">Watch the demo video</p>\
          <p class="text-xs text-gray-600">See these strategies in action — quick walkthrough and examples.</p>\
        </div>\
        <div class="flex-shrink-0">\
          <button type="button" class="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-md font-black text-sm hover:brightness-110 transition" data-video-target="'+ (id || '#') +'">Play video</button>\
        </div>\
      </div>';
  }

  function smoothScrollTo(el) {
    if (!el) return;
    var rect = el.getBoundingClientRect();
    var top = window.scrollY + rect.top - 24;
    window.scrollTo({ top: top, behavior: 'smooth' });
    // subtle highlight
    el.classList.add('ring-2', 'ring-primary', 'ring-opacity-30');
    setTimeout(function () {
      el.classList.remove('ring-2', 'ring-primary', 'ring-opacity-30');
    }, 1800);
  }

  function bindCTA(cta) {
    cta.addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-video-target]');
      if (!btn) return;
      var target = btn.getAttribute('data-video-target');
      try {
        var el = document.querySelector(target) || document.querySelector('video, iframe[data-video], .page-video');
        if (el) smoothScrollTo(el);
        // If it's an iframe with a src about:blank (lazy), try opening src from data-src attribute
        if (el && el.tagName === 'IFRAME' && (el.src === '' || el.src === 'about:blank')) {
          var ds = el.getAttribute('data-src');
          if (ds) el.src = ds;
        }
      } catch (err) {}
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    try {
      var videoEl = document.querySelector('.page-video') || document.querySelector('video') || document.querySelector('iframe[data-video]');
      if (!videoEl) return;
      // avoid duplicating if already inserted
      if (videoEl.nextElementSibling && videoEl.nextElementSibling.getAttribute && videoEl.nextElementSibling.getAttribute('data-video-cta')) return;
      var id = videoEl.id ? ('#' + videoEl.id) : '';
      var wrapper = document.createElement('div');
      wrapper.innerHTML = createCTAHtml(id);
      var cta = wrapper.firstElementChild;
      videoEl.parentNode.insertBefore(cta, videoEl.nextSibling);
      bindCTA(cta);
    } catch (err) {
      // fail silently
    }
  });
})();

