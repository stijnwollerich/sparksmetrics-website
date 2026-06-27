(function () {
  var STORAGE_KEY = "qualify_quiz_results";
  var CALENDLY_BASE =
    "https://calendly.com/stijn-wollerich/conversion-rate-optimization?hide_gdpr_banner=1";
  var BOOK_STEP = 9;

  var bookStep = document.getElementById("qualify-book-step");
  if (!bookStep) return;

  var calendlyHost = document.getElementById("qualify-calendly-inline");
  var calendlySection = document.getElementById("qualify-calendly");
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

  function auditFocusPhrase(data) {
    var bottleneck = data && data.answers && data.answers.q6 && data.answers.q6.value;
    if (bottleneck === "low-cvr" || bottleneck === "few-sales") {
      return "product pages and checkout flow";
    }
    if (bottleneck === "high-ad-costs") {
      return "landing pages and post-click conversion";
    }
    if (bottleneck === "cant-grow") {
      return "checkout flow and offer positioning";
    }
    return "product pages and checkout flow";
  }

  function buildPersonalizedPhrase(data) {
    var revenue = answerLabel(data, "q2");
    var cvr = answerLabel(data, "q3");
    var focus = auditFocusPhrase(data);

    if (revenue && cvr) {
      return (
        "With " +
        revenue +
        " in revenue and a " +
        cvr +
        " conversion rate, we'd start by auditing your " +
        focus +
        ". In the 4-minute audit below, you'll see exactly how we uncover opportunities like this."
      );
    }
    if (revenue) {
      return (
        "With " +
        revenue +
        " in revenue, we'd start by auditing your " +
        focus +
        ". In the 4-minute audit below, you'll see exactly how we uncover opportunities like this."
      );
    }
    return (
      "Based on your answers, we'd start by auditing your " +
      focus +
      ". In the 4-minute audit below, you'll see exactly how we uncover opportunities like this."
    );
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
        quiz_completed: true,
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

  function scrollToCalendly(source) {
    var target = calendlySection || calendlyHost;
    if (!target) return;
    pushGtm("calendly_scroll", { source: source || "unknown" });
    target.scrollIntoView({ behavior: "smooth", block: "start" });
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
            video_id: "vsl-free-cro-audit",
            video_youtube_id: "wwWZImpQ4cc",
            video_provider: "youtube",
            video_url: "https://www.youtube.com/watch?v=wwWZImpQ4cc",
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
        scrollToCalendly("hero_cta");
      });
    }
    bookStep.querySelectorAll("[data-qualify-book-end-cta]").forEach(function (el) {
      el.addEventListener("click", function () {
        pushGtm("book_cta_click", { source: "video_end_cta" });
        scrollToCalendly("video_end_cta");
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
    mountCalendly(quizData);
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
    if (calendlyHost) {
      calendlyHost.innerHTML = "";
      calendlyHost.removeAttribute("data-processed");
    }
  };
})();
