(function (global) {
  var FORM_ID = "qualify-quiz";
  var FORM_NAME = "CRO Agency Qualify Quiz";
  var TOTAL = 9;
  var PAGE_TYPE = "qualify_quiz_funnel";
  var SESSION_KEY = "qualify_quiz_funnel_session_id";

  var STEP_META = {
    2: {
      key: "conversion_rate",
      question: "What is your current conversion rate?",
      field_name: "conversion_rate",
    },
    3: {
      key: "ad_spend",
      question: "How much do you spend on paid ads per month?",
      field_name: "ad_spend",
    },
    4: {
      key: "monthly_revenue",
      question: "What is your store's monthly revenue?",
      field_name: "monthly_revenue",
    },
    5: {
      key: "monthly_traffic",
      question: "How many visitors does your store get per month?",
      field_name: "monthly_traffic",
    },
    6: {
      key: "cro_experience",
      question: "What have you done for CRO so far?",
      field_name: "cro_experience",
    },
    7: {
      key: "biggest_problem",
      question: "What's holding your store back?",
      field_name: "biggest_problem",
    },
    8: {
      key: "results",
      question: "Your personalized results",
      field_name: null,
    },
    9: {
      key: "book",
      question: "Book your free CRO audit",
      field_name: null,
    },
  };

  var FIELD_TO_Q = {
    conversion_rate: "q3",
    ad_spend: "q1",
    monthly_revenue: "q2",
    monthly_traffic: "q4",
    cro_experience: "q5",
    biggest_problem: "q6",
  };

  function getFunnelSessionId() {
    try {
      var id = sessionStorage.getItem(SESSION_KEY);
      if (!id) {
        id =
          "qq_" +
          Date.now().toString(36) +
          "_" +
          Math.random().toString(36).slice(2, 10);
        sessionStorage.setItem(SESSION_KEY, id);
      }
      return id;
    } catch (err) {
      return "qq_anon";
    }
  }

  function normalizeAnswersSnapshot(answers) {
    answers = answers || {};
    var snap = {
      conversion_rate: "",
      ad_spend: "",
      monthly_revenue: "",
      monthly_traffic: "",
      cro_experience: "",
      biggest_problem: "",
      email: "",
    };
    Object.keys(FIELD_TO_Q).forEach(function (field) {
      var q = FIELD_TO_Q[field];
      if (answers[q] && answers[q].value) {
        snap[field] = answers[q].value;
      }
    });
    return snap;
  }

  function pushQualifyGtm(formAction, step, fieldValue, extra, state) {
    extra = extra || {};
    state = state || {};
    try {
      var meta = STEP_META[step] || {};
      var answers = state.answers || {};
      var formAnswers = normalizeAnswersSnapshot(answers);
      if (state.email) formAnswers.email = state.email;

      var payload = {
        event: "cro_qualify_quiz",
        form_action: formAction,
        form_id: FORM_ID,
        form_name: FORM_NAME,
        form_step: step,
        form_step_total: TOTAL,
        form_step_name: meta.key || "",
        form_step_question: meta.question || "",
        form_progress_pct: Math.min(
          100,
          Math.max(0, Math.round((step / TOTAL) * 100)),
        ),
        funnel_session_id: getFunnelSessionId(),
        page_type: PAGE_TYPE,
        page_path: global.location.pathname,
        page_location: global.location.href,
        timestamp: new Date().toISOString(),
        form_answers: formAnswers,
        conversion_rate: formAnswers.conversion_rate,
        ad_spend: formAnswers.ad_spend,
        monthly_revenue: formAnswers.monthly_revenue,
        monthly_traffic: formAnswers.monthly_traffic,
        cro_experience: formAnswers.cro_experience,
        biggest_problem: formAnswers.biggest_problem,
        email: formAnswers.email,
        field_name: meta.field_name || "",
        field_value: "",
        qualify_answers: answers,
        qualify_score:
          typeof state.score === "number" ? state.score : undefined,
      };

      if (state.tier) payload.qualify_tier = state.tier;
      if (fieldValue !== undefined && fieldValue !== null) {
        payload.field_value = String(fieldValue);
      }

      Object.keys(extra).forEach(function (key) {
        payload[key] = extra[key];
      });

      global.dataLayer = global.dataLayer || [];
      global.dataLayer.push(payload);
    } catch (err) {}
  }

  function videoContextExtra(state) {
    state = state || {};
    return {
      form_id: FORM_ID,
      form_name: FORM_NAME,
      form_step: 9,
      form_step_name: "book",
      form_step_total: TOTAL,
      funnel_session_id: getFunnelSessionId(),
      page_type: PAGE_TYPE,
      qualify_score: state.score,
      qualify_tier: state.tier,
      qualify_revenue_left: state.revenueLeft,
    };
  }

  global.QualifyQuizGtm = {
    push: pushQualifyGtm,
    getSessionId: getFunnelSessionId,
    videoContext: videoContextExtra,
    FORM_ID: FORM_ID,
    FORM_NAME: FORM_NAME,
    BOOK_STEP: 9,
    RESULT_STEP: 8,
    TOTAL: TOTAL,
    STEP_META: STEP_META,
  };
})(window);
