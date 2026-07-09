(function (global) {
  var FORM_ID = "qualify-quiz";
  var FORM_NAME = "CRO Qualify Quiz";
  var TOTAL = 9;
  var PAGE_TYPE = "qualify_quiz_funnel";
  var SESSION_KEY = "qualify_quiz_funnel_session_id";

  var STEP_META = {
    2: {
      key: "conversion_rate",
      question_id: "q3",
      question: "What is your current conversion rate?",
    },
    3: {
      key: "ad_spend",
      question_id: "q1",
      question: "How much do you spend on paid ads per month?",
    },
    4: {
      key: "monthly_revenue",
      question_id: "q2",
      question: "What is your store's monthly revenue?",
    },
    5: {
      key: "monthly_traffic",
      question_id: "q4",
      question: "How many visitors does your store get per month?",
    },
    6: {
      key: "cro_experience",
      question_id: "q5",
      question: "What have you done for CRO so far?",
    },
    7: {
      key: "biggest_problem",
      question_id: "q6",
      question: "What's holding your store back?",
    },
    8: {
      key: "results",
      question_id: "",
      question: "Your personalized results",
    },
    9: {
      key: "book",
      question_id: "",
      question: "Book your free CRO audit",
    },
  };

  var QUESTION_META = {
    q1: { question: "How much do you spend on paid ads per month?" },
    q2: { question: "What is your store's monthly revenue?" },
    q3: { question: "What is your current conversion rate?" },
    q4: { question: "How many visitors does your store get per month?" },
    q5: { question: "What have you done for CRO so far?" },
    q6: { question: "What's holding your store back?" },
  };

  function getFunnelSessionId() {
    if (global.SmAnalytics) return global.SmAnalytics.getFunnelSessionId();
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

  function buildUserDataFromAnswers(answers, state) {
    answers = answers || {};
    state = state || {};
    var ud = global.SmAnalytics ? global.SmAnalytics.emptyUserData() : {};
    if (state.email) ud.email = state.email;
    if (state.fname) ud.fname = state.fname;
    if (typeof state.score === "number") ud.qualify_score = state.score;
    if (state.tier) ud.qualify_tier = state.tier;
    return ud;
  }

  function pushQualifyGtm(formAction, step, answer, extra, state) {
    if (!global.SmAnalytics) return;
    extra = extra || {};
    state = state || {};
    try {
      var meta = STEP_META[step] || {};
      var eventName = "form_step";
      if (formAction === "form_submit") eventName = "form_submit";
      if (formAction === "form_success") eventName = "form_success";

      global.SmAnalytics.push(eventName, {
        form_id: FORM_ID,
        form_name: FORM_NAME,
        lead_type: "qualify_quiz",
        page_type: PAGE_TYPE,
        form_step: step,
        form_step_total: TOTAL,
        form_step_name: meta.key || "",
        funnel_session_id: getFunnelSessionId(),
        user_data: buildUserDataFromAnswers(state.answers, state),
        question_id: meta.question_id || "",
        question: meta.question || "",
        answer: answer !== undefined && answer !== null ? String(answer) : "",
        answer_label: extra.answer_label || "",
      });
    } catch (err) {}
  }

  global.QualifyQuizGtm = {
    push: pushQualifyGtm,
    getSessionId: getFunnelSessionId,
    FORM_ID: FORM_ID,
    FORM_NAME: FORM_NAME,
    BOOK_STEP: 9,
    RESULT_STEP: 8,
    TOTAL: TOTAL,
    STEP_META: STEP_META,
    QUESTION_META: QUESTION_META,
  };
})(window);
