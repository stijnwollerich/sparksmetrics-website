(function (global) {
  var VIDEO_PROGRESS_MILESTONES = [10, 25, 50, 75, 90, 100];

  function isElementVisible(el) {
    if (!el) return true;
    var rect = el.getBoundingClientRect();
    return (
      rect.bottom > 0 &&
      rect.top < global.innerHeight &&
      rect.width > 0 &&
      rect.height > 0
    );
  }

  function pushVslVideoEvent(eventName, videoMeta, extra) {
    try {
      var payload = {
        event: eventName,
        video_id: videoMeta.video_id || "",
        video_provider: videoMeta.video_provider || "",
        video_url: videoMeta.video_url || "",
        video_title: videoMeta.video_title || "",
        video_duration: videoMeta.video_duration || 0,
        video_current_time: videoMeta.video_current_time || 0,
        video_percent: videoMeta.video_percent || 0,
        video_visible:
          videoMeta.video_visible !== undefined
            ? videoMeta.video_visible
            : true,
        page_path: global.location.pathname,
        page_location: global.location.href,
        timestamp: new Date().toISOString(),
      };
      if (extra) {
        Object.keys(extra).forEach(function (key) {
          if (extra[key] !== undefined) payload[key] = extra[key];
        });
      }
      global.dataLayer = global.dataLayer || [];
      global.dataLayer.push(payload);
    } catch (err) {}
  }

  function getHtml5VideoMeta(video, wrapper) {
    var duration = 0;
    var current = 0;
    if (video && !isNaN(video.duration) && isFinite(video.duration)) {
      duration = Math.floor(video.duration);
    }
    if (video && !isNaN(video.currentTime) && isFinite(video.currentTime)) {
      current = Math.floor(video.currentTime);
    }
    var percent =
      duration > 0
        ? Math.min(100, Math.max(0, Math.floor((current / duration) * 100)))
        : 0;
    var src = "";
    try {
      src =
        video.currentSrc ||
        (video.querySelector("source") &&
          video.querySelector("source").getAttribute("src")) ||
        "";
    } catch (srcErr) {}
    var videoId =
      wrapper.getAttribute("data-video-id") ||
      video.getAttribute("data-video-id") ||
      "hero";
    return {
      video_id: videoId,
      video_provider: "html5",
      video_url: src,
      video_title: video.getAttribute("aria-label") || "",
      video_duration: duration,
      video_current_time: current,
      video_percent: percent,
      video_visible: isElementVisible(wrapper),
    };
  }

  function buildYoutubeMeta(wrap, player, videoId) {
    var currentTime = 0;
    var duration = 0;
    var title = "";
    if (player && player.getCurrentTime) {
      try {
        currentTime = Math.floor(player.getCurrentTime());
      } catch (timeErr) {}
    }
    if (player && player.getDuration) {
      try {
        duration = Math.floor(player.getDuration());
      } catch (durErr) {}
    }
    if (player && player.getVideoData) {
      try {
        title = (player.getVideoData().title || "").trim();
      } catch (titleErr) {}
    }
    if (!duration && wrap._vslChapterDuration) {
      duration = Math.floor(wrap._vslChapterDuration);
    }
    var percent =
      duration > 0
        ? Math.min(100, Math.max(0, Math.floor((currentTime / duration) * 100)))
        : 0;
    return {
      video_id: videoId,
      video_provider: "youtube",
      video_url: "https://www.youtube.com/watch?v=" + videoId,
      video_title: title,
      video_duration: duration,
      video_current_time: currentTime,
      video_percent: percent,
      video_visible: isElementVisible(wrap),
    };
  }

  function initHtml5VideoAnalytics(wrapper) {
    if (wrapper._vslAnalyticsBound) return;
    wrapper._vslAnalyticsBound = true;

    var video = wrapper.querySelector("video");
    if (!video) return;

    var started = false;
    var completeSent = false;
    var sent = {};
    VIDEO_PROGRESS_MILESTONES.forEach(function (m) {
      sent[m] = false;
    });

    function snapshot() {
      return getHtml5VideoMeta(video, wrapper);
    }

    function checkProgress() {
      var meta = snapshot();
      if (!meta.video_duration) return;
      var pct = meta.video_percent;
      for (var i = 0; i < VIDEO_PROGRESS_MILESTONES.length; i++) {
        var m = VIDEO_PROGRESS_MILESTONES[i];
        var next = VIDEO_PROGRESS_MILESTONES[i + 1];
        var inRange =
          next !== undefined ? pct >= m && pct < next : pct >= m;
        if (inRange && !sent[m]) {
          sent[m] = true;
          pushVslVideoEvent("video_progress", snapshot(), {
            video_percent: m,
          });
          if (m === 100 && !completeSent) {
            completeSent = true;
            pushVslVideoEvent("video_complete", snapshot(), {
              video_percent: 100,
            });
          }
          break;
        }
      }
    }

    video.addEventListener("play", function () {
      if (!started) {
        started = true;
        pushVslVideoEvent("video_start", snapshot());
      }
    });
    video.addEventListener("pause", function () {
      if (!video.ended) {
        pushVslVideoEvent("video_pause", snapshot());
      }
    });
    video.addEventListener("timeupdate", checkProgress);
    video.addEventListener("ended", function () {
      if (!completeSent) {
        completeSent = true;
        pushVslVideoEvent("video_complete", snapshot(), {
          video_percent: 100,
        });
      }
    });
  }

  global.VslVideoAnalytics = {
    push: pushVslVideoEvent,
    buildYoutubeMeta: buildYoutubeMeta,
    milestones: VIDEO_PROGRESS_MILESTONES,
    isVisible: isElementVisible,
    initHtml5: initHtml5VideoAnalytics,
  };
})(window);
