(function (global) {
  var FORM_ID = "qualify-quiz";
  var FORM_NAME = "CRO Agency Qualify Quiz";
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

  function buildFormAnswers(answers) {
    answers = answers || {};
    var snap = {};
    Object.keys(answers).forEach(function (questionId) {
      var entry = answers[questionId];
      if (!entry || !entry.value) return;
      var meta = QUESTION_META[questionId] || {};
      snap[questionId] = {
        question_id: questionId,
        question: meta.question || "",
        answer: entry.value,
        answer_label: entry.label || "",
        score: typeof entry.score === "number" ? entry.score : undefined,
      };
    });
    if (answers.email) {
      snap.email = answers.email;
    }
    return snap;
  }

  function pushQualifyGtm(formAction, step, answer, extra, state) {
    extra = extra || {};
    state = state || {};
    try {
      var meta = STEP_META[step] || {};
      var answers = state.answers || {};
      var formAnswers = buildFormAnswers(answers);
      if (state.email) {
        formAnswers.email = state.email;
      }

      var payload = {
        event: "cro_qualify_quiz",
        form_action: formAction,
        form_id: FORM_ID,
        form_name: FORM_NAME,
        form_step: step,
        form_step_total: TOTAL,
        form_step_name: meta.key || "",
        form_progress_pct: Math.min(
          100,
          Math.max(0, Math.round((step / TOTAL) * 100)),
        ),
        funnel_session_id: getFunnelSessionId(),
        page_type: PAGE_TYPE,
        page_path: global.location.pathname,
        page_location: global.location.href,
        timestamp: new Date().toISOString(),
        question_id: meta.question_id || "",
        question: meta.question || "",
        answer: answer !== undefined && answer !== null ? String(answer) : "",
        answer_label: extra.answer_label || "",
        form_answers: formAnswers,
      };

      if (extra.answer_score !== undefined) {
        payload.answer_score = extra.answer_score;
      }
      if (typeof state.score === "number") {
        payload.qualify_score = state.score;
      }
      if (state.tier) {
        payload.qualify_tier = state.tier;
      }
      if (state.email) {
        payload.email = state.email;
      }

      Object.keys(extra).forEach(function (key) {
        if (
          key === "answer_label" ||
          key === "answer_score" ||
          key === "qualify_question" ||
          key === "qualify_answer" ||
          key === "qualify_answer_label" ||
          key === "qualify_answer_score"
        ) {
          return;
        }
        payload[key] = extra[key];
      });

      global.dataLayer = global.dataLayer || [];
      global.dataLayer.push(payload);
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
