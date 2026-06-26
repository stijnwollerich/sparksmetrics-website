(function () {
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

  function getFunnelExtra(wrap) {
    if (!wrap || wrap.getAttribute("data-vsl-funnel") !== "qualify_quiz") {
      return null;
    }
    var state = null;
    try {
      var raw = sessionStorage.getItem("qualify_quiz_results");
      if (raw) state = JSON.parse(raw);
    } catch (err) {}
    if (window.QualifyQuizGtm) {
      return window.QualifyQuizGtm.videoContext(state || {});
    }
    return {
      form_id: "qualify-quiz",
      form_step: 9,
      page_type: "qualify_quiz_funnel",
    };
  }

  function pushVslEvent(eventName, wrap, player, videoId, extra) {
    if (!window.VslVideoAnalytics) return;
    var merged = extra || {};
    var funnelExtra = getFunnelExtra(wrap);
    if (funnelExtra) {
      Object.keys(funnelExtra).forEach(function (key) {
        if (merged[key] === undefined) merged[key] = funnelExtra[key];
      });
    }
    window.VslVideoAnalytics.push(
      eventName,
      window.VslVideoAnalytics.buildYoutubeMeta(wrap, player, videoId),
      merged,
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
        var duration = player.getDuration() || 0;
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
          pushVslEvent("video_progress", wrap, player, videoId, {
            video_percent: toSend,
          });
          if (toSend === 100) {
            if (!wrap._vslVideoCompleteSent) {
              wrap._vslVideoCompleteSent = true;
              pushVslEvent("video_complete", wrap, player, videoId, {
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

  document.querySelectorAll(".vsl-youtube-wrap[data-youtube-id]").forEach(function (wrap) {
    var videoId = wrap.getAttribute("data-youtube-id");
    var poster = wrap.querySelector(".vsl-youtube-poster");
    var playBtn = wrap.querySelector(".vsl-youtube-play");
    var iframeHost = wrap.querySelector(".vsl-youtube-iframe");
    if (!videoId || !playBtn || !iframeHost) return;

    var origin =
      window.location.origin ||
      window.location.protocol + "//" + window.location.host;

    playBtn.addEventListener("click", function () {
      if (wrap._vslStarted) return;
      wrap._vslStarted = true;
      if (poster) poster.classList.add("hidden");
      playBtn.classList.add("hidden");

      pushVslEvent("video_click", wrap, null, videoId, {
        video_id: wrap.getAttribute("data-video-id") || videoId,
      });

      var iframeId = "vsl-yt-" + videoId + "-" + Math.random().toString(36).slice(2, 8);
      iframeHost.innerHTML = '<div id="' + iframeId + '" class="w-full h-full"></div>';
      iframeHost.classList.remove("hidden");

      loadYouTubeAPI(function () {
        var player = new window.YT.Player(iframeId, {
          videoId: videoId,
          playerVars: {
            autoplay: 1,
            controls: 1,
            modestbranding: 1,
            rel: 0,
            playsinline: 1,
            enablejsapi: 1,
            origin: origin,
          },
          events: {
            onStateChange: function (e) {
              var player = e.target;
              if (e.data === window.YT.PlayerState.PLAYING) {
                if (!wrap._vslVideoStarted) {
                  wrap._vslVideoStarted = true;
                  pushVslEvent("video_start", wrap, player, videoId, {
                    video_id: wrap.getAttribute("data-video-id") || videoId,
                  });
                }
                pushVslEvent("video_play", wrap, player, videoId);
                bindProgressTracking(wrap, player, videoId);
              }
              if (e.data === window.YT.PlayerState.PAUSED) {
                pushVslEvent("video_pause", wrap, player, videoId);
                if (wrap._progressIntervalId) {
                  clearInterval(wrap._progressIntervalId);
                  wrap._progressIntervalId = null;
                }
              }
              if (e.data === window.YT.PlayerState.ENDED) {
                if (!wrap._vslVideoCompleteSent) {
                  wrap._vslVideoCompleteSent = true;
                  pushVslEvent("video_complete", wrap, player, videoId, {
                    video_percent: 100,
                  });
                }
                if (wrap._progressIntervalId) {
                  clearInterval(wrap._progressIntervalId);
                  wrap._progressIntervalId = null;
                }
              }
            },
          },
        });
        wrap._vslPlayer = player;
      });
    });
  });
})();
