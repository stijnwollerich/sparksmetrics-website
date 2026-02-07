(function () {
  var key = "sm_audit_bar_closed";
  var bar = document.getElementById("audit-bar");
  var btn = document.getElementById("audit-bar-close");
  if (!bar || !btn) return;

  function showBar() {
    bar.style.visibility = "visible";
    bar.style.transform = "translateY(0)";
  }

  function hideBar() {
    bar.style.transform = "translateY(100%)";
    sessionStorage.setItem(key, "1");
    bar.addEventListener("transitionend", function onEnd() {
      bar.style.visibility = "hidden";
      bar.removeEventListener("transitionend", onEnd);
    });
  }

  if (sessionStorage.getItem(key) === "1") {
    bar.style.visibility = "hidden";
    bar.style.transform = "translateY(100%)";
  } else {
    setTimeout(showBar, 1500);
  }

  btn.addEventListener("click", hideBar);
})();
