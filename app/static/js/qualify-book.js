(function () {
  var STORAGE_KEY = "qualify_quiz_results";
  var CALENDLY_BASE =
    "https://calendly.com/stijn-wollerich/conversion-rate-optimization?hide_gdpr_banner=1";
  var BOOK_STEP = 9;

  var bookStep = document.getElementById("qualify-book-step");
  if (!bookStep) return;

  var calendlyHost = document.getElementById("qualify-calendly-inline");
  var calendlyPanel = document.getElementById("qualify-calendly-panel");
  var calendlyReveal = document.getElementById("qualify-calendly-reveal");
  var ctaTop = document.getElementById("qualify-book-cta-top");
  var calendlyMounted = false;
  var bookInitialized = false;
  var quizData = null;
  var eventsBound = false;
  var vslViewSent = false;

  function readQuizData() {
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function answerLabel(data, key) {
    return data && data.answers && data.answers[key] && data.answers[key].label
      ? data.answers[key].label
      : "";
  }

  function buildQuizSummary(data) {
    if (!data) return "";
    return [
      "Tier: " + (data.tier || ""),
      "Score: " + (data.score != null ? String(data.score) : ""),
      "Opportunity: " + (data.revenueLeft || ""),
      "Ad spend: " + answerLabel(data, "q1"),
      "Revenue: " + answerLabel(data, "q2"),
      "CVR: " + answerLabel(data, "q3"),
      "Traffic: " + answerLabel(data, "q4"),
      "CRO exp: " + answerLabel(data, "q5"),
      "Bottleneck: " + answerLabel(data, "q6"),
    ]
      .filter(function (part) {
        return part && !part.endsWith(": ");
      })
      .join(" | ");
  }

  function headlineForTier(tier) {
    if (tier === "strong") return "You're a strong fit for CRO";
    if (tier === "almost") return "You qualify for CRO";
    return "You qualify for CRO";
  }

  function buildPersonalizedPhrase(data) {
    var revenue = answerLabel(data, "q2");
    var ads = answerLabel(data, "q1");
    var traffic = answerLabel(data, "q4");
    var cvr = answerLabel(data, "q3");

    if (revenue && ads && traffic) {
      return (
        "With " +
        revenue +
        " in monthly revenue and " +
        ads +
        " in ad spend, your biggest opportunity isn't traffic—it's converting more of the " +
        traffic +
        " visitors you're already paying for."
      );
    }
    if (revenue && traffic && cvr) {
      return (
        "With " +
        revenue +
        " in monthly revenue, " +
        traffic +
        " monthly visitors, and a " +
        cvr +
        " conversion rate, you're leaving revenue on the table before you need more traffic."
      );
    }
    if (data.subtitle) return data.subtitle;
    return "Based on your answers, your store appears to be a strong candidate for CRO.";
  }

  function renderHeader(data) {
    var headline = document.getElementById("qualify-book-headline");
    var amount = document.getElementById("qualify-book-amount");
    var personal = document.getElementById("qualify-book-personal");
    var revenue = (data.revenueLeft || "").replace("/year", "");

    if (headline) headline.textContent = headlineForTier(data.tier);
    if (amount && revenue) amount.textContent = revenue + "/year";
    if (personal) personal.textContent = buildPersonalizedPhrase(data);
  }

  function pushGtm(formAction, extra) {
    if (!window.QualifyQuizGtm) return;
    window.QualifyQuizGtm.push(formAction, BOOK_STEP, "", extra, {
      answers: (quizData && quizData.answers) || {},
      score: quizData && quizData.score,
      tier: quizData && quizData.tier,
      email: quizData && quizData.email,
    });
  }

  function syncQuizLead(data) {
    fetch("/qualify-quiz-lead", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      keepalive: true,
      body: JSON.stringify({
        email: data.email || "",
        fname: data.fname || "",
        score: data.score,
        tier: data.tier,
        qualified: data.qualified,
        revenue_left: data.revenueLeft,
        answers: data.answers,
        quiz_summary: buildQuizSummary(data),
        form_page_url: window.location.href,
        funnel_session_id:
          data.funnelSessionId ||
          (window.QualifyQuizGtm ? window.QualifyQuizGtm.getSessionId() : ""),
      }),
    }).catch(function () {});
  }

  function buildCalendlyUrl(data) {
    var url = CALENDLY_BASE + "&utm_source=qualify_quiz";
    if (data.email) url += "&email=" + encodeURIComponent(data.email);
    if (data.fname) url += "&name=" + encodeURIComponent(data.fname);
    return url;
  }

  function mountCalendly(data) {
    if (calendlyMounted || !calendlyHost) return;
    calendlyMounted = true;
    var widgetUrl = buildCalendlyUrl(data);
    calendlyHost.setAttribute("data-url", widgetUrl);

    function initWidget() {
      if (window.Calendly && window.Calendly.initInlineWidget) {
        window.Calendly.initInlineWidget({
          url: widgetUrl,
          parentElement: calendlyHost,
          prefill: {
            email: data.email || "",
            name: data.fname || "",
          },
          resize: true,
        });
        pushGtm("calendly_open", { calendly_url: widgetUrl });
        return;
      }
      window.setTimeout(initWidget, 50);
    }

    initWidget();
  }

  function revealCalendly(source) {
    if (!calendlyPanel) return;
    calendlyPanel.classList.remove("is-hidden");
    calendlyPanel.setAttribute("aria-hidden", "false");
    if (calendlyReveal) calendlyReveal.style.display = "none";
    mountCalendly(quizData);
    pushGtm("calendly_reveal", { source: source || "unknown" });
    window.setTimeout(function () {
      calendlyPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
  }

  function observeVslSection() {
    if (vslViewSent || !window.IntersectionObserver) return;
    var vslSection = document.getElementById("qualify-book-vsl");
    if (!vslSection) return;

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting || vslViewSent) return;
          vslViewSent = true;
          pushGtm("vsl_section_view", {
            video_id: "qualify-book-vsl",
            video_provider: "youtube",
            video_youtube_id: "wwWZImpQ4cc",
          });
          observer.disconnect();
        });
      },
      { threshold: 0.35 },
    );
    observer.observe(vslSection);
  }

  function bindEvents() {
    if (eventsBound) return;
    eventsBound = true;

    if (ctaTop) {
      ctaTop.addEventListener("click", function () {
        pushGtm("book_cta_click", { source: "hero_cta" });
        revealCalendly("hero_cta");
      });
    }
    if (calendlyReveal) {
      calendlyReveal.addEventListener("click", function () {
        pushGtm("book_cta_click", { source: "bottom_cta" });
        revealCalendly("bottom_cta");
      });
    }
    bookStep.querySelectorAll("[data-qualify-book-scroll-vsl]").forEach(function (el) {
      el.addEventListener("click", function (e) {
        var target = document.getElementById("qualify-book-vsl");
        if (!target) return;
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        pushGtm("vsl_scroll", { source: "teaser_link" });
      });
    });
  }

  window.initQualifyBookStep = function () {
    if (bookInitialized) return false;

    quizData = readQuizData();
    if (!quizData || !quizData.qualified) return false;

    if (!quizData.funnelSessionId && window.QualifyQuizGtm) {
      quizData.funnelSessionId = window.QualifyQuizGtm.getSessionId();
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(quizData));
      } catch (e) {}
    }

    renderHeader(quizData);
    syncQuizLead(quizData);
    bindEvents();
    observeVslSection();
    bookInitialized = true;
    return true;
  };

  window.resetQualifyBookStep = function () {
    bookInitialized = false;
    calendlyMounted = false;
    vslViewSent = false;
    quizData = null;
    if (calendlyPanel) {
      calendlyPanel.classList.add("is-hidden");
      calendlyPanel.setAttribute("aria-hidden", "true");
    }
    if (calendlyReveal) calendlyReveal.style.display = "";
    if (calendlyHost) {
      calendlyHost.innerHTML = "";
      calendlyHost.removeAttribute("data-processed");
    }
  };
})();
