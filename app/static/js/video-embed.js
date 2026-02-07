(function () {
  var container = document.getElementById("video-container");
  var poster = document.getElementById("video-poster");
  var embed = document.getElementById("video-embed");
  var iframe = document.getElementById("video-iframe");
  var videoId = container && container.getAttribute("data-video-id");
  if (container && poster && embed && iframe && videoId) {
    container.addEventListener(
      "click",
      function () {
        iframe.src =
          "https://www.youtube.com/embed/" + videoId + "?autoplay=1&rel=0";
        poster.classList.add("hidden");
        embed.classList.remove("hidden");
      },
      { once: true }
    );
  }
})();
