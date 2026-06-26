(function () {
  var root = document.getElementById("qualify-quiz");
  if (!root) return;

  var FIRST_QUESTION_STEP = 2;
  var LAST_QUESTION_STEP = 7;
  var RESULT_STEP = 8;
  var BOOK_STEP = 9;
  var QUESTION_COUNT = 6;

  var strategySessionUrl = root.getAttribute("data-strategy-session-url") || "/30-minute-strategy-session/";
  var resourceSlug = root.getAttribute("data-resource-slug") || "7-questions-cro-agency";
  var QUIZ_STORAGE_KEY = "qualify_quiz_results";

  var current = FIRST_QUESTION_STEP;
  var answers = {};
  var totalScore = 0;
  var lastResultGtmExtra = null;

  var chrome = document.getElementById("qualify-chrome");
  var qualifyIntro = document.getElementById("qualify-intro");
  var progressTrack = document.getElementById("qualify-progress-track");
  var progressFill = document.getElementById("qualify-progress-fill");
  var progressLabel = document.getElementById("qualify-progress-label");
  var resultBadge = document.getElementById("qualify-result-badge");
  var resultTitle = document.getElementById("qualify-result-title");
  var resultSubtitle = document.getElementById("qualify-result-subtitle");
  var resultFindings = document.getElementById("qualify-result-findings");
  var resultUrgency = document.getElementById("qualify-result-urgency");
  var resultBody = document.getElementById("qualify-result-body");
  var resultPersonal = document.getElementById("qualify-result-personal");
  var emailOffer = document.getElementById("qualify-email-offer");
  var guideEmail = document.getElementById("qualify-guide-email");
  var guideSubmit = document.getElementById("qualify-guide-submit");
  var guideMsg = document.getElementById("qualify-guide-msg");
  var callPrimary = document.getElementById("qualify-call-primary");
  var callPromise = document.getElementById("qualify-call-promise");
  var emailDivider = document.getElementById("qualify-result-divider-email");
  var emailOfferTitle = emailOffer ? emailOffer.querySelector("h3") : null;
  var emailOfferDesc = emailOffer ? emailOffer.querySelector("p") : null;
  var emailOfferPerks = emailOffer ? emailOffer.querySelector(".qualify-email-perks") : null;

  var CALL_PROMISE_COPY =
    "We'll review your store live and show you the first 3 tests we'd run to recover the revenue opportunity above.";

  var EMAIL_OFFER_COPY = {
    qualified: {
      perks: [
        "The 3 highest-impact tests we'd run",
        "Your personalized CRO scorecard",
        "Priority fixes ranked by ROI",
      ],
      button: "Send my action plan",
    },
    not_qualified: {
      title: "Get the readiness guide (PDF)",
      desc: "Enter your email and we'll send:",
      perks: [
        "Traffic and revenue benchmarks for CRO",
        "What to fix before you hire an agency",
        "7 questions to ask when you are ready",
      ],
      button: "Send me the PDF",
    },
  };

  var RESULT_TIERS = {
    strong: {
      badgeClass: "is-strong",
      badgeLabel: "You're a strong fit for CRO",
      min: 11,
      max: 15,
    },
    almost: {
      badgeClass: "is-almost",
      badgeLabel: "You qualify for CRO",
      min: 6,
      max: 10,
    },
    not_yet: {
      badgeClass: "is-not-yet",
      badgeLabel: "Not ready for CRO yet",
      min: 0,
      max: 5,
    },
  };

  var PAIN_PROFILES = {
    "low-cvr": {
      badge: "Your results are ready",
      issue: "Low conversion rate",
    },
    "high-ad-costs": {
      badge: "Your results are ready",
      issue: "Ad costs are too high",
    },
    "few-sales": {
      badge: "Your results are ready",
      issue: "Traffic comes in, few people buy",
    },
    "cant-grow": {
      badge: "Your results are ready",
      issue: "Can't grow profitably",
    },
  };

  var REVENUE_MID_MONTHLY = {
    "under-100k": 50000,
    "100k-500k": 300000,
    "500k-2m": 1000000,
    "2m-plus": 3000000,
  };

  var AD_SPEND_MID_MONTHLY = {
    "under-10k": 5000,
    "10k-100k": 40000,
    "100k-500k": 200000,
    "500k-plus": 750000,
  };

  var CVR_BASE = {
    unknown: null,
    "under-1": 1.0,
    "1-3": 2.0,
    "over-3": 3.5,
  };

  function painProfile() {
    return PAIN_PROFILES[answerValue("q6")] || {
      badge: "Your results are ready",
      issue: "Your store is leaking potential revenue",
    };
  }

  function formatMoney(n) {
    if (n >= 1000000) {
      return "$" + (Math.round((n / 1000000) * 10) / 10) + "M";
    }
    if (n >= 1000) {
      return "$" + Math.round(n / 1000) + "k";
    }
    return "$" + Math.round(n);
  }

  function formatMoneyRange(low, high, suffix) {
    return formatMoney(low) + "–" + formatMoney(high) + (suffix || "");
  }

  function estimateMetrics(tierKey) {
    var revenueMonthly = REVENUE_MID_MONTHLY[answerValue("q2")] || 100000;
    var adMonthly = AD_SPEND_MID_MONTHLY[answerValue("q1")] || 20000;
    var cvr = answerValue("q3");
    var upliftLow;
    var upliftHigh;
    var oppLow;
    var oppHigh;

    if (cvr === "under-1" || cvr === "unknown") {
      upliftLow = tierKey === "strong" ? 12 : tierKey === "almost" ? 8 : 5;
      upliftHigh = tierKey === "strong" ? 22 : tierKey === "almost" ? 15 : 10;
      oppLow = tierKey === "strong" ? 0.04 : tierKey === "almost" ? 0.03 : 0.02;
      oppHigh = tierKey === "strong" ? 0.08 : tierKey === "almost" ? 0.05 : 0.035;
    } else if (cvr === "1-3") {
      upliftLow = tierKey === "strong" ? 8 : tierKey === "almost" ? 5 : 4;
      upliftHigh = tierKey === "strong" ? 15 : tierKey === "almost" ? 10 : 7;
      oppLow = tierKey === "strong" ? 0.03 : tierKey === "almost" ? 0.02 : 0.015;
      oppHigh = tierKey === "strong" ? 0.06 : tierKey === "almost" ? 0.04 : 0.03;
    } else {
      upliftLow = 5;
      upliftHigh = 10;
      oppLow = 0.02;
      oppHigh = 0.04;
    }

    var annualLow = revenueMonthly * oppLow * 12;
    var annualHigh = revenueMonthly * oppHigh * 12;
    var adCap = adMonthly * 12 * 2.5;
    annualLow = Math.min(annualLow, adCap);
    annualHigh = Math.min(annualHigh, adCap);
    if (annualHigh < annualLow) annualHigh = annualLow;
    if (annualHigh - annualLow < annualHigh * 0.08) {
      annualLow = annualHigh * 0.65;
    }

    var cvrBase = CVR_BASE[cvr];
    var cvrTarget = "a clearer baseline";
    if (cvrBase) {
      cvrTarget =
        (cvrBase * (1 + upliftLow / 100)).toFixed(1) +
        "%–" +
        (cvrBase * (1 + upliftHigh / 100)).toFixed(1) +
        "%";
    }

    return {
      leakPct: Math.round(oppLow * 100) + "–" + Math.round(oppHigh * 100) + "%",
      revenueLeft: formatMoneyRange(annualLow, annualHigh, "/year"),
      uplift: "+" + upliftLow + "–" + upliftHigh + "%",
      cvrNow: cvr === "unknown" ? "unknown" : answerLabel("q3"),
      cvrTarget: cvrTarget,
    };
  }

  function opportunitySubtitle(tierKey) {
    if (tierKey === "not_yet") {
      return (
        "At " +
        answerLabel("q4") +
        " visitors and " +
        answerLabel("q2") +
        " in revenue, build traffic first. The guide below shows when CRO is worth it."
      );
    }
    return (
      "You already have " +
      answerLabel("q4") +
      " visitors and " +
      answerLabel("q1") +
      " in ad spend. The gap is conversion — structured CRO is how you close it."
    );
  }

  function notQualifiedPhrase() {
    return (
      "At " +
      answerLabel("q4") +
      " monthly visitors and " +
      answerLabel("q2") +
      " in revenue, you do not have enough volume yet for a CRO agency to run tests with confidence. Grow traffic first, then fix conversion."
    );
  }

  function updateEmailOffer(qualified, revenueDisplay) {
    var copy = qualified ? EMAIL_OFFER_COPY.qualified : EMAIL_OFFER_COPY.not_qualified;
    if (emailOfferTitle) {
      emailOfferTitle.textContent = qualified
        ? "Where is the " + revenueDisplay + " coming from?"
        : copy.title;
    }
    if (emailOfferDesc) {
      emailOfferDesc.textContent = qualified ? "Enter your email and we'll send:" : copy.desc;
    }
    if (emailOfferPerks) {
      emailOfferPerks.innerHTML = copy.perks
        .map(function (item) {
          return "<li>" + item + "</li>";
        })
        .join("");
    }
    if (guideSubmit) guideSubmit.textContent = copy.button;
  }

  function urgencyPhrase(metrics) {
    var cvr = answerValue("q3");
    if (cvr === "unknown") {
      return (
        "You spend " +
        answerLabel("q1") +
        " on ads each month without a clear conversion number. That makes it hard to know what you are leaving behind."
      );
    }
    if (cvr === "under-1" || cvr === "1-3") {
      return (
        "At " +
        metrics.cvrNow +
        ", moving toward " +
        metrics.cvrTarget +
        " on your current traffic would close most of that gap."
      );
    }
    return "";
  }

  function renderFinding(label, value, accent) {
    var item = document.createElement("div");
    item.className = "qualify-finding" + (accent ? " is-accent" : "");
    item.innerHTML =
      '<div class="qualify-finding-label">' +
      label +
      '</div><div class="qualify-finding-value">' +
      value +
      "</div>";
    return item;
  }

  function renderFindings(metrics, pain, qualified) {
    if (!resultFindings) return;
    resultFindings.innerHTML = "";
    resultFindings.classList.toggle("is-compact", !qualified);
    resultFindings.appendChild(renderFinding("Biggest issue", pain.issue, false));
    if (qualified) {
      resultFindings.appendChild(renderFinding("Revenue opportunity", metrics.revenueLeft, true));
      resultFindings.appendChild(renderFinding("Conversion uplift", metrics.uplift, true));
    } else {
      resultFindings.appendChild(renderFinding("Recommended next step", "Build traffic first", true));
    }
  }

  function answerLabel(key) {
    return answers[key] && answers[key].label ? answers[key].label : "";
  }

  function answerValue(key) {
    return answers[key] && answers[key].value ? answers[key].value : "";
  }

  function snapshotPhrase() {
    return (
      "You spend " +
      answerLabel("q1") +
      " on ads each month, pull in " +
      answerLabel("q4") +
      " visitors, do about " +
      answerLabel("q2") +
      " in revenue, and put conversion at " +
      answerLabel("q3") +
      "."
    );
  }

  function conversionPainPhrase() {
    var cvr = answerValue("q3");
    var traffic = answerLabel("q4");
    var ads = answerLabel("q1");

    if (cvr === "unknown") {
      return (
        "You are spending " +
        ads +
        " without a clear read on how much of that traffic actually buys. That blind spot is expensive."
      );
    }
    if (cvr === "under-1") {
      return (
        "At " +
        answerLabel("q3") +
        ", almost all of those " +
        traffic +
        " monthly visits leave without an order. The traffic is there. The sales are not."
      );
    }
    if (cvr === "1-3") {
      return (
        "At " +
        answerLabel("q3") +
        ", you are still losing most of the " +
        traffic +
        " people who hit your store every month. Small leaks at this volume cost real money."
      );
    }
    return (
      "Your conversion rate is " +
      answerLabel("q3") +
      ", but with " +
      ads +
      " in ad spend you are still paying for clicks that need to work harder to earn back."
    );
  }

  function croPainPhrase() {
    var v = answerValue("q5");
    if (v === "nothing") {
      return "Nothing has been done on the funnel yet, so the leak keeps running month after month.";
    }
    if (v === "diy") {
      return "DIY changes on the site have not moved revenue, so whatever is broken is still broken.";
    }
    if (v === "ab-tests") {
      return "You have run tests, but revenue still has not followed. That means the wrong things got optimized.";
    }
    if (v === "agency") {
      return "You have worked with a CRO agency before and still have this problem. Something in the funnel was missed.";
    }
    return "";
  }

  function tierPainPhrase(tierKey) {
    var traffic = answerLabel("q4");
    var ads = answerLabel("q1");
    var problem = answerLabel("q6");

    if (tierKey === "strong") {
      return (
        "This is not a traffic problem. You already have " +
        traffic +
        " visitors and " +
        ads +
        " in ad spend. You are paying to fill a store that does not convert enough of them."
      );
    }
    if (tierKey === "almost") {
      return (
        "\"" +
        problem +
        "\" is real, but with " +
        traffic +
        " visitors and " +
        ads +
        " in spend you still cannot test fixes with confidence. So the leak stays, and you keep guessing."
      );
    }
    return (
      "\"" +
      problem +
      "\" is real, but at " +
      traffic +
      " visitors a month you do not have enough data to know what to fix. More traffic has to come before CRO can do its job."
    );
  }

  function diagnosisPhrase() {
    var v = answerValue("q6");
    var ads = answerLabel("q1");
    var traffic = answerLabel("q4");
    var revenue = answerLabel("q2");

    if (v === "low-cvr") {
      return (
        "At " +
        answerLabel("q3") +
        " with " +
        traffic +
        " monthly visitors and " +
        revenue +
        " in revenue, the store is getting traffic but not turning enough of it into orders."
      );
    }
    if (v === "high-ad-costs") {
      return (
        "With " +
        ads +
        " in ad spend and " +
        revenue +
        " in revenue, your cost to acquire a customer is likely eating your margin."
      );
    }
    if (v === "few-sales") {
      return (
        "On " +
        traffic +
        " monthly visitors, people are showing up but not buying enough. That usually points to product pages, offer, or checkout, not more traffic."
      );
    }
    if (v === "cant-grow") {
      return (
        "At " +
        revenue +
        " in monthly revenue with " +
        ads +
        " in ad spend, pushing harder on ads without fixing conversion will keep squeezing your margins."
      );
    }
    return "";
  }

  function buildPersonalizedCopy(tierKey) {
    var metrics = estimateMetrics(tierKey);
    var revenueDisplay = metrics.revenueLeft.replace("/year", "");
    var qualified = tierKey !== "not_yet";
    var tierMeta = RESULT_TIERS[tierKey];

    if (!qualified) {
      return {
        badge: tierMeta.badgeLabel,
        title: "You are not ready for a CRO agency yet.",
        titleLead: "",
        titleAmount: "",
        titleTail: "",
        subtitle: opportunitySubtitle(tierKey),
        metrics: metrics,
        urgency: "",
        paragraphs: [],
        personal: notQualifiedPhrase(),
        callPromise: "",
        qualified: false,
      };
    }

    return {
      badge: tierMeta.badgeLabel,
      title: "",
      titleLead: "You could be leaving",
      titleAmount: revenueDisplay,
      titleTail: "on the table each year.",
      subtitle: opportunitySubtitle(tierKey),
      metrics: metrics,
      urgency: urgencyPhrase(metrics),
      paragraphs: [],
      personal: diagnosisPhrase(),
      callPromise: CALL_PROMISE_COPY,
      qualified: true,
    };
  }

  function steps() {
    return root.querySelectorAll(".qualify-step");
  }

  function questionNumberForStep(step) {
    return step - FIRST_QUESTION_STEP + 1;
  }

  var QUESTION_ORDER = ["q3", "q1", "q2", "q4", "q5", "q6"];

  function countAnsweredQuestions() {
    var count = 0;
    QUESTION_ORDER.forEach(function (key) {
      if (answers[key]) count++;
    });
    return count;
  }

  function progressPercentForStep(step) {
    if (step < FIRST_QUESTION_STEP || step > LAST_QUESTION_STEP) return 0;
    var answered = countAnsweredQuestions();
    var viewing = questionNumberForStep(step) - 1;
    var completed = Math.max(answered, viewing);
    return Math.min(100, Math.round((completed / QUESTION_COUNT) * 100));
  }

  function updateProgressBar(step) {
    var pct = progressPercentForStep(typeof step === "number" ? step : current);
    var fill = document.getElementById("qualify-progress-fill");
    var track = document.getElementById("qualify-progress-track");
    if (fill) fill.style.width = pct + "%";
    if (track) track.setAttribute("aria-valuenow", String(pct));
  }

  function updateChrome(step) {
    if (!chrome) return;
    var showChrome = step >= FIRST_QUESTION_STEP && step <= LAST_QUESTION_STEP;
    chrome.classList.toggle("is-hidden", !showChrome);
    if (qualifyIntro) {
      qualifyIntro.classList.toggle("is-hidden", step !== FIRST_QUESTION_STEP);
    }
    if (progressLabel && showChrome) {
      progressLabel.textContent =
        "Question " + questionNumberForStep(step) + " of " + QUESTION_COUNT;
    }
    if (showChrome) updateProgressBar(step);
  }

  function getGtmState() {
    return {
      answers: answers,
      score: totalScore,
      tier: resultTier(totalScore).key,
      email: guideEmail ? guideEmail.value.trim() : "",
    };
  }

  function pushGtm(formAction, step, fieldValue, extra) {
    if (!window.QualifyQuizGtm) return;
    window.QualifyQuizGtm.push(
      formAction,
      step,
      fieldValue,
      extra,
      getGtmState(),
    );
  }

  function pushStepView(step, extra) {
    pushGtm("step_view", step, "", extra);
  }

  function pushStepCompleted(step, fieldValue, extra) {
    pushGtm("step_complete", step, fieldValue, extra);
  }

  function showThankYouStep() {
    renderResult();
    var copy = buildPersonalizedCopy(resultTier(totalScore).key);
    if (copy.qualified) {
      setStep(BOOK_STEP);
    } else {
      setStep(RESULT_STEP);
    }
  }

  function scrollToQuizTop() {
    root.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function setStep(step) {
    current = step;
    steps().forEach(function (el) {
      var s = parseInt(el.getAttribute("data-step"), 10);
      el.classList.toggle("is-active", s === step);
    });
    updateChrome(step);
    if (step === BOOK_STEP && window.initQualifyBookStep) {
      window.initQualifyBookStep();
    }
    var stepExtra = step === RESULT_STEP ? lastResultGtmExtra : null;
    pushStepView(step, stepExtra);
    scrollToQuizTop();
  }

  function computeScore() {
    totalScore = 0;
    ["q1", "q2", "q3", "q4", "q5"].forEach(function (key) {
      var entry = answers[key];
      if (entry && typeof entry.score === "number") {
        totalScore += entry.score;
      }
    });
    return totalScore;
  }

  function resultTier(score) {
    if (score >= RESULT_TIERS.strong.min) return { key: "strong", meta: RESULT_TIERS.strong };
    if (score >= RESULT_TIERS.almost.min) return { key: "almost", meta: RESULT_TIERS.almost };
    return { key: "not_yet", meta: RESULT_TIERS.not_yet };
  }

  function persistQuizResults(score, tier, copy) {
    var email = guideEmail ? guideEmail.value.trim() : "";
    var payload = {
      score: score,
      tier: tier.key,
      qualified: copy.qualified,
      badge: copy.badge,
      revenueLeft: copy.metrics.revenueLeft,
      subtitle: copy.subtitle,
      answers: answers,
      email: email,
      fname: email ? fnameFromEmail(email) : "",
      funnelSessionId: window.QualifyQuizGtm
        ? window.QualifyQuizGtm.getSessionId()
        : "qq-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10),
      savedAt: new Date().toISOString(),
    };
    try {
      var existing = sessionStorage.getItem(QUIZ_STORAGE_KEY);
      if (existing) {
        var prev = JSON.parse(existing);
        if (prev && prev.funnelSessionId) payload.funnelSessionId = prev.funnelSessionId;
        if (prev && prev.email && !payload.email) {
          payload.email = prev.email;
          payload.fname = prev.fname || "";
        }
      }
      sessionStorage.setItem(QUIZ_STORAGE_KEY, JSON.stringify(payload));
    } catch (e) {}
    return payload;
  }

  function renderResult() {
    var score = computeScore();
    var tier = resultTier(score);
    var copy = buildPersonalizedCopy(tier.key);

    if (resultBadge) {
      resultBadge.textContent = copy.badge;
      resultBadge.className = "qualify-result-badge " + tier.meta.badgeClass;
    }
    if (resultTitle) {
      if (copy.titleAmount) {
        resultTitle.innerHTML =
          copy.titleLead +
          ' <span class="qualify-result-amount">' +
          copy.titleAmount +
          "</span> " +
          copy.titleTail;
      } else {
        resultTitle.textContent = copy.title;
      }
    }
    if (resultSubtitle) {
      resultSubtitle.textContent = copy.subtitle || "";
      resultSubtitle.style.display = copy.subtitle ? "" : "none";
    }
    renderFindings(copy.metrics, painProfile(), copy.qualified);
    if (resultUrgency) {
      resultUrgency.textContent = copy.urgency || "";
      resultUrgency.style.display = copy.urgency ? "" : "none";
    }
    if (resultBody) {
      if (copy.paragraphs.length) {
        resultBody.innerHTML = copy.paragraphs
          .map(function (p) {
            return "<p>" + p + "</p>";
          })
          .join("");
        resultBody.style.display = "";
      } else {
        resultBody.innerHTML = "";
        resultBody.style.display = "none";
      }
    }
    if (resultPersonal) {
      resultPersonal.textContent = copy.personal || "";
      resultPersonal.style.display = copy.personal ? "" : "none";
    }
    if (callPrimary) {
      callPrimary.style.display = copy.qualified ? "" : "none";
    }
    if (emailDivider) {
      emailDivider.style.display = copy.qualified ? "" : "none";
    }
    if (callPromise) {
      callPromise.textContent = copy.callPromise || "";
    }
    updateEmailOffer(copy.qualified, copy.metrics.revenueLeft.replace("/year", ""));
    persistQuizResults(score, tier, copy);

    var callCta = document.getElementById("qualify-cta-call");
    if (callCta && copy.qualified) {
      callCta.style.display = "";
    } else if (callCta) {
      callCta.style.display = "none";
    }

    lastResultGtmExtra = {
      qualify_score: score,
      qualify_tier: tier.key,
      qualify_qualified: copy.qualified,
      qualify_q6: answerValue("q6"),
      qualify_revenue_leak: copy.metrics.leakPct,
      qualify_revenue_left: copy.metrics.revenueLeft,
      qualify_uplift: copy.metrics.uplift,
    };
  }

  function selectAnswer(btn) {
    var q = btn.getAttribute("data-q");
    var value = btn.getAttribute("data-value");
    var score = parseInt(btn.getAttribute("data-score") || "0", 10);
    if (!q || !value) return;

    answers[q] = { value: value, score: score, label: btn.textContent.trim() };

    var step = root.querySelector('.qualify-step[data-step="' + current + '"]');
    if (step) {
      step.querySelectorAll("[data-qualify-answer]").forEach(function (tile) {
        tile.classList.toggle("is-selected", tile === btn);
      });
    }

    pushStepCompleted(current, value, {
      qualify_question: q,
      qualify_answer: value,
      qualify_answer_label: btn.textContent.trim(),
      qualify_answer_score: score,
    });

    updateProgressBar(current);

    window.setTimeout(function () {
      if (current < LAST_QUESTION_STEP) {
        setStep(current + 1);
      } else {
        showThankYouStep();
      }
    }, 220);
  }

  function resetQuiz() {
    answers = {};
    totalScore = 0;
    root.querySelectorAll(".mss-tile.is-selected").forEach(function (tile) {
      tile.classList.remove("is-selected");
    });
    if (guideEmail) guideEmail.value = "";
    if (guideMsg) {
      guideMsg.textContent = "";
      guideMsg.className = "qualify-email-msg";
    }
    if (emailOffer) emailOffer.classList.remove("is-sent");
    lastResultGtmExtra = null;
    try {
      sessionStorage.removeItem(QUIZ_STORAGE_KEY);
    } catch (e) {}
    if (window.resetQualifyBookStep) window.resetQualifyBookStep();
    pushGtm("quiz_restart", FIRST_QUESTION_STEP);
    setStep(FIRST_QUESTION_STEP);
  }

  function fnameFromEmail(email) {
    var local = (email.split("@")[0] || "").trim();
    if (!local) return "Friend";
    return local.charAt(0).toUpperCase() + local.slice(1);
  }

  function submitGuideEmail() {
    if (!guideEmail || !guideSubmit) return;
    var email = guideEmail.value.trim();
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      if (guideMsg) {
        guideMsg.textContent = "Enter a valid email address.";
        guideMsg.className = "qualify-email-msg is-error";
      }
      guideEmail.focus();
      return;
    }

    guideSubmit.disabled = true;
    if (guideMsg) {
      guideMsg.textContent = "Sending…";
      guideMsg.className = "qualify-email-msg";
    }

    fetch("/download-resource", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({
        fname: fnameFromEmail(email),
        email: email,
        resource: resourceSlug,
        form_page_url: window.location.href,
        business_stage: answers.q2 ? answers.q2.label : undefined,
      }),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok || !res.data.success) {
          throw new Error((res.data && res.data.error) || "Request failed");
        }
        if (guideMsg) {
          guideMsg.textContent = "Check your inbox. Your action plan is on the way.";
          guideMsg.className = "qualify-email-msg is-success";
        }
        if (emailOffer) emailOffer.classList.add("is-sent");
        var tier = resultTier(totalScore);
        var copy = buildPersonalizedCopy(tier.key);
        persistQuizResults(totalScore, tier, copy);
        pushGtm("email_submit", RESULT_STEP, email, {
          resource_slug: resourceSlug,
          qualify_score: totalScore,
        });
        if (res.data.download_url) {
          window.open(res.data.download_url, "_blank", "noopener");
        }
      })
      .catch(function () {
        if (guideMsg) {
          guideMsg.textContent = "Something went wrong. Try again in a moment.";
          guideMsg.className = "qualify-email-msg is-error";
        }
      })
      .finally(function () {
        guideSubmit.disabled = false;
      });
  }

  pushGtm("page_load", FIRST_QUESTION_STEP);
  setStep(FIRST_QUESTION_STEP);

  root.querySelectorAll("[data-qualify-restart]").forEach(function (btn) {
    btn.addEventListener("click", resetQuiz);
  });

  root.querySelectorAll("[data-qualify-answer]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      selectAnswer(btn);
    });
  });

  if (guideSubmit) {
    guideSubmit.addEventListener("click", submitGuideEmail);
  }
  if (guideEmail) {
    guideEmail.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        submitGuideEmail();
      }
    });
  }

  var callCta = document.getElementById("qualify-cta-call");
  if (callCta) {
    callCta.addEventListener("click", function () {
      pushGtm("book_call_click", RESULT_STEP, "", {
        qualify_score: totalScore,
        qualify_tier: resultTier(totalScore).key,
      });
      showThankYouStep();
    });
  }
})();
