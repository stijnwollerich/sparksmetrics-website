(function () {
  var UNLOCK_KEY = "vsl-free-cro-video-unlocked";

  function isFreeCroVideoLandingPage() {
    var path = (window.location && window.location.pathname) || "";
    return path.indexOf("/free-cro-video") !== -1;
  }

  function vslRedirectUrl() {
    return "/free-cro-audit";
  }

  function isUnlocked() {
    try {
      return sessionStorage.getItem(UNLOCK_KEY) === "1";
    } catch (err) {
      return false;
    }
  }

  function loadYouTubeAPI(callback) {
    if (window.YT && window.YT.Player) {
      callback();
      return;
    }
    if (window.vslYoutubeAPILoading) {
      var check = setInterval(function () {
        if (window.YT && window.YT.Player) {
          clearInterval(check);
          callback();
        }
      }, 100);
      return;
    }
    window.vslYoutubeAPILoading = true;
    var tag = document.createElement("script");
    tag.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(tag);
    var prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = function () {
      if (typeof prev === "function") prev();
      callback();
    };
  }

  function pushVslVideoEvent(eventName, wrap, player, videoId, extra) {
    if (!window.VslVideoAnalytics) return;
    window.VslVideoAnalytics.push(
      eventName,
      window.VslVideoAnalytics.buildYoutubeMeta(wrap, player, videoId),
      extra,
    );
  }

  function bindProgressTracking(wrap, player, videoId) {
    if (wrap._progressIntervalId) {
      clearInterval(wrap._progressIntervalId);
      wrap._progressIntervalId = null;
    }
    var sent = {};
    var milestones = window.VslVideoAnalytics
      ? window.VslVideoAnalytics.milestones
      : [10, 25, 50, 75, 90, 100];
    milestones.forEach(function (m) {
      sent[m] = false;
    });

    wrap._progressIntervalId = setInterval(function () {
      try {
        if (!player.getCurrentTime) return;
        var current = player.getCurrentTime();
        var duration =
          wrap._vslChapterDuration || player.getDuration() || 0;
        if (duration <= 0) return;
        var pct = Math.floor((current / duration) * 100);
        var toSend = null;
        for (var i = 0; i < milestones.length; i++) {
          var m = milestones[i];
          var next = milestones[i + 1];
          var inRange =
            next !== undefined ? pct >= m && pct < next : pct >= m;
          if (inRange && !sent[m]) {
            toSend = m;
            break;
          }
        }
        if (toSend !== null) {
          sent[toSend] = true;
          pushVslVideoEvent("video_progress", wrap, player, videoId, {
            video_percent: toSend,
          });
          if (toSend === 100) {
            if (!wrap._vslVideoCompleteSent) {
              wrap._vslVideoCompleteSent = true;
              pushVslVideoEvent("video_complete", wrap, player, videoId, {
                video_percent: 100,
              });
            }
            clearInterval(wrap._progressIntervalId);
            wrap._progressIntervalId = null;
          }
        }
      } catch (err) {
        clearInterval(wrap._progressIntervalId);
        wrap._progressIntervalId = null;
      }
    }, 500);
  }

  function startPlayback(wrap) {
    if (!wrap || wrap._vslStarted) return;
    var videoId = wrap.getAttribute("data-youtube-id");
    var poster = wrap.querySelector(".vsl-youtube-poster");
    var posterWrap = wrap.querySelector(".vsl-youtube-poster-wrap");
    var playBtn = wrap.querySelector(".vsl-youtube-play");
    var iframeHost = wrap.querySelector(".vsl-youtube-iframe");
    if (!videoId || !iframeHost) return;

    wrap._vslStarted = true;
    if (poster) poster.classList.add("hidden");
    if (posterWrap) posterWrap.classList.add("hidden");
    if (playBtn) playBtn.classList.add("hidden");
    wrap.classList.add("is-playing");

    var origin =
      window.location.origin ||
      window.location.protocol + "//" + window.location.host;
    var iframeId = "vsl-gated-iframe-" + videoId;
    iframeHost.innerHTML =
      '<div id="' + iframeId + '" class="w-full h-full"></div>';
    iframeHost.classList.remove("hidden");

    loadYouTubeAPI(function () {
      new window.YT.Player(iframeId, {
        videoId: videoId,
        playerVars: {
          autoplay: 1,
          controls: 1,
          modestbranding: 1,
          rel: 0,
          iv_load_policy: 3,
          cc_load_policy: 0,
          playsinline: 1,
          enablejsapi: 1,
          origin: origin,
        },
        events: {
          onReady: function (event) {
            wrap._ytPlayer = event.target;
            wrap._ytPlayerReady = true;
            try {
              var playerDuration =
                event.target.getDuration && event.target.getDuration();
              if (playerDuration > 0) {
                wrap._vslChapterDuration = playerDuration;
              }
            } catch (readyErr) {}
          },
          onStateChange: function (event) {
            var player = event.target;
            if (event.data === window.YT.PlayerState.PLAYING) {
              if (!wrap._vslVideoStarted) {
                wrap._vslVideoStarted = true;
                pushVslVideoEvent("video_start", wrap, player, videoId);
              }
              bindProgressTracking(wrap, player, videoId);
            }
            if (event.data === window.YT.PlayerState.PAUSED) {
              pushVslVideoEvent("video_pause", wrap, player, videoId);
              if (wrap._progressIntervalId) {
                clearInterval(wrap._progressIntervalId);
                wrap._progressIntervalId = null;
              }
            }
            if (event.data === window.YT.PlayerState.ENDED) {
              if (!wrap._vslVideoCompleteSent) {
                wrap._vslVideoCompleteSent = true;
                pushVslVideoEvent("video_complete", wrap, player, videoId, {
                  video_percent: 100,
                });
              }
              if (wrap._progressIntervalId) {
                clearInterval(wrap._progressIntervalId);
                wrap._progressIntervalId = null;
              }
              try {
                var duration = player.getDuration && player.getDuration();
                if (duration > 0 && player.seekTo) {
                  player.seekTo(Math.max(0, duration - 0.3), true);
                }
                if (player.pauseVideo) player.pauseVideo();
              } catch (freezeErr) {}
            }
          },
        },
      });
    });
  }

  function primaryGatedWrap() {
    return document.querySelector(".vsl-gated-wrap[data-youtube-id]");
  }

  window.VslGated = {
    unlockAndPlay: function () {
      if (isFreeCroVideoLandingPage()) {
        window.location.href = vslRedirectUrl();
        return;
      }
      try {
        sessionStorage.setItem(UNLOCK_KEY, "1");
      } catch (err) {}
      var wrap = primaryGatedWrap();
      if (!wrap) return;
      wrap.scrollIntoView({ behavior: "smooth", block: "center" });
      startPlayback(wrap);
    },
    isUnlocked: isUnlocked,
  };

  document
    .querySelectorAll(".vsl-gated-wrap[data-youtube-id]")
    .forEach(function (wrap) {
      var playBtn = wrap.querySelector("[data-vsl-gated-play]");
      if (!playBtn) return;

      playBtn.addEventListener("click", function (e) {
        e.preventDefault();
        if (isFreeCroVideoLandingPage()) {
          if (window.LeadModal && window.LeadModal.openFrom) {
            window.LeadModal.openFrom(playBtn);
          }
          return;
        }
        if (isUnlocked()) {
          startPlayback(wrap);
          return;
        }
        if (window.LeadModal && window.LeadModal.openFrom) {
          window.LeadModal.openFrom(playBtn);
        }
      });
    });
})();
