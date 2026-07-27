function escapeHtml(text) {
  return $("<div>").text(text || "").html();
}

/**
 * Collects and prepares form data from the batch evaluation form as a JSON object.
 * @param {HTMLFormElement} formElem - The form element to collect data from.
 * @returns {object} The form data as a plain object suitable for JSON serialization.
 */
function collectBatchEvalFormData(formElem) {
  const formData = new FormData(formElem);
  const data = {};
  formData.forEach((value, key) => {
    if (key.endsWith('[]')) {
      if (!data[key]) data[key] = [];
      data[key].push(value);
    } else {
      data[key] = value;
    }
  });
  return data;
}

/**
 * Renders a single evaluation row into the batch results table.
 * @param {object} ev - Evaluation status object from the API.
 */
function renderEvaluationRow(ev, meta) {
  var now = new Date();
  var datetimeStr = now.toLocaleString();
  var headingLink = '<a href="/exam/' + ev.exam_id + '/" class="details-link" title="View details"><span class="details-icon" aria-label="Details">🔍</span></a>';
  var gradeCell;
  if (ev.status === "failed") {
    gradeCell = 'Failed';
  } else if (ev.status === "completed") {
    gradeCell = ev.grade !== null ? ev.grade : "-";
  } else {
    gradeCell = "Pending";
  }

  var repetitionCell = "-";
  if (meta && meta.repetition && meta.totalReps) {
    repetitionCell = escapeHtml(meta.repetition) + "/" + escapeHtml(meta.totalReps);
  }

  $("#batch-eval-table").show();
  var $row = $("<tr></tr>");
  $row.append($('<td data-label="Date"></td>').append(headingLink, ' ' + escapeHtml(datetimeStr)));
  $row.append($('<td data-label="Model"></td>').text(ev.model_name || ev.model_id || "-"));
  $row.append($('<td data-label="Subject"></td>').text(ev.course_name || "-"));
  $row.append($('<td data-label="Exam"></td>').text(ev.exam_name || ev.exam_id || "-"));
  $row.append($('<td data-label="Repetition"></td>').text(repetitionCell));
  $row.append($('<td data-label="Grade"></td>').text(gradeCell));
  $row.append($('<td data-label="Time"></td>').text(ev.time !== null ? ev.time.toFixed(2) : "-"));
  $("#batch-eval-table tbody").append($row);
}

/**
 * Polls an individual evaluation's question details and renders them.
 * @param {number} evalId - Evaluation ID to poll.
 * @param {object} meta - Metadata for this evaluation (model, exam, repetition).
 */
function pollEvaluationQuestions(evalId, meta) {
  var MAX_RETRIES = 10;
  var state = {
    headingShown: false,
    renderedQuestions: {},
    totalQuestions: null,
    retries: 0,
  };
  var interval = setInterval(function() {
    fetch("/evaluation/" + evalId + "/questions/")
      .then(function(r) {
        var ct = r.headers.get("content-type") || "";
        if (!r.ok || r.redirected || ct.indexOf("application/json") === -1) {
          state.retries++;
          if (state.retries >= MAX_RETRIES) {
            clearInterval(interval);
          }
          return null;
        }
        return r.json();
      })
      .then(function(data) {
        if (!data || !data.questions) return;
        state.retries = 0;
        if (state.totalQuestions === null) {
          state.totalQuestions = data.total_questions;
        }

        if (!state.headingShown && data.questions.length > 0) {
          var evalIdSafe = "eval-" + evalId;
          var headingHtml = '<div id="' + evalIdSafe + '" class="exam-detail-heading exam-detail-heading-margin eval-details-section">' +
            '<span class="exam-detail-label">Model:</span> <span class="exam-detail-value">' + escapeHtml(data.model_name || "-") + ' - </span>' +
            '<span class="exam-detail-label">Subject:</span> <span class="exam-detail-value">' + escapeHtml(data.course_name || "-") + ' - </span>' +
            '<span class="exam-detail-label">Exam:</span> <span class="exam-detail-value">' + escapeHtml(data.exam_name || "-") + ' - </span>' +
            '<span class="exam-detail-label">Repetition:</span> <span class="exam-detail-value">' + escapeHtml(meta.repetition || "-") + "/" + escapeHtml(meta.totalReps || "-") + '</span>' +
          '</div>';
          $("#exam-details").append(headingHtml);
          state.headingShown = true;
        }

        for (var i = 0; i < data.questions.length; i++) {
          var q = data.questions[i];
          if (state.renderedQuestions[q.question_id]) continue;
          state.renderedQuestions[q.question_id] = true;

          var detailsHtml = '<div class="exam-detail-box">' +
            '<b>Question ' + q.question_number + ':</b>' +
            '<pre>' + escapeHtml(q.question_prompt) + '</pre>' +
            '<b>Model response:</b> <span class="model-response-text ' + (q.is_correct ? 'correct-response' : 'incorrect-response') + '">' + escapeHtml(q.response) + '</span><br>' +
            '<b>Correct option:</b> ' + escapeHtml(q.correct_option) +
            '<span class="correctness-icon">' + (q.is_correct ? "✅" : "❌") + '</span>' +
            '<div class="question-time">Time: ' + (q.question_time !== null ? q.question_time : "-") + 's</div>' +
          '</div>';
          $("#exam-details").append(detailsHtml);
        }

        if (data.status === "failed") {
          clearInterval(interval);
          $("#exam-details").append(
            '<div class="exam-error-message">Evaluation failed for ' + escapeHtml(data.model_name || "Model") + '.</div>' +
            '<div class="back-to-top-link-container"><a href="#top" class="back-to-top-link no-underline">⬆ Back to Top</a></div>'
          );
          return;
        }

        if (data.status === "completed" || (data.questions.length >= state.totalQuestions && state.totalQuestions > 0)) {
          clearInterval(interval);
          $("#exam-details").append('<div class="back-to-top-link-container"><a href="#top" class="back-to-top-link no-underline">⬆ Back to Top</a></div>');
        }
      })
      .catch(function() {
        state.retries++;
        if (state.retries >= MAX_RETRIES) {
          clearInterval(interval);
        }
      });
  }, 2000);
  return interval;
}

/**
 * Polls the batch-evaluation-status endpoint and renders rows for completed evaluations.
 * Progress is based on real QuestionEvaluation rows (completed_tasks/total_tasks),
 * not on django-q2 task records, so it cannot be affected by task pruning.
 * @param {number[]} evaluationIds - Array of evaluation IDs to monitor.
 * @param {Object} metaById - Map of evaluation ID to { repetition, totalReps }.
 * @param {Function} onProgress - Callback with (finishedQuestions, totalQuestions).
 * @param {Function} onAllComplete - Callback when all evaluations are done.
 */
function pollEvaluations(evaluationIds, metaById, onProgress, onAllComplete) {
  var MAX_RETRIES = 10;
  var csrf = getCookie("csrftoken");
  var rendered = {};
  var retries = 0;
  var lastFinished = 0;
  var lastTotal = 0;
  var interval = setInterval(function() {
    fetch("/batch-evaluation-status/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf
      },
      body: JSON.stringify({ ids: evaluationIds })
    })
      .then(function(r) {
        var ct = r.headers.get("content-type") || "";
        if (!r.ok || r.redirected || ct.indexOf("application/json") === -1) {
          retries++;
          $("#batch-eval-status-msg").html(
            '<div class="batch-eval-status-warning">Connection problem (retry ' + retries + '/' + MAX_RETRIES + '). Waiting for server...</div>'
          );
          if (retries >= MAX_RETRIES) {
            clearInterval(interval);
            $("#batch-eval-status-msg").html(
              '<div class="batch-eval-status-error">Stopped updating progress after ' + MAX_RETRIES + ' failed attempts. Reload the page to resume. Last progress: ' + lastFinished + '/' + lastTotal + '</div>'
            );
          }
          return null;
        }
        return r.json();
      })
      .then(function(data) {
        if (!data || !data.results) return;
        if (data.status === "error") {
          clearInterval(interval);
          return;
        }
        retries = 0;
        $("#batch-eval-status-msg").html("");
        var allDone = true;
        var finishedQuestions = 0;
        var totalQuestions = 0;
        for (var i = 0; i < data.results.length; i++) {
          var ev = data.results[i];
          if (typeof ev.completed_tasks === "number") {
            finishedQuestions += ev.completed_tasks;
          }
          if (typeof ev.total_tasks === "number") {
            totalQuestions += ev.total_tasks;
          }
          if (ev.status === "completed" || ev.status === "failed") {
            if (!rendered[ev.evaluation_id]) {
              rendered[ev.evaluation_id] = true;
              renderEvaluationRow(ev, metaById["" + ev.evaluation_id]);
              if (ev.status === "failed" && ev.failed_reason) {
                $("#batch-eval-errors").append(
                  '<div class="batch-eval-error">Evaluation ' + ev.evaluation_id +
                  ' failed on question ' + (ev.failed_question_id || "?") +
                  ': ' + escapeHtml(ev.failed_reason) + '</div>'
                );
              }
            }
          } else {
            allDone = false;
          }
        }
        lastFinished = finishedQuestions;
        lastTotal = totalQuestions;
        if (onProgress) {
          onProgress(finishedQuestions, totalQuestions);
        }
        if (allDone) {
          clearInterval(interval);
          if (onAllComplete) onAllComplete();
        }
      })
      .catch(function() {
        retries++;
        $("#batch-eval-status-msg").html(
          '<div class="batch-eval-status-warning">Connection problem (retry ' + retries + '/' + MAX_RETRIES + '). Waiting for server...</div>'
        );
        if (retries >= MAX_RETRIES) {
          clearInterval(interval);
          $("#batch-eval-status-msg").html(
            '<div class="batch-eval-status-error">Stopped updating progress after ' + MAX_RETRIES + ' failed attempts. Reload the page to resume. Last progress: ' + lastFinished + '/' + lastTotal + '</div>'
          );
        }
      });
  }, 3000);
  return interval;
}

/**
 * Handles the batch evaluation task response and polls for results.
 * @param {Response} response - The fetch response object.
 * @returns {Promise<void>} Resolves when results are rendered.
 */
function handleBatchEvalTask(response) {
  return response.json().then(function (data) {
    if (data.status === "queued") {
      window._batchEvalStartTime = Date.now();
      $("#batch-eval-results").html(
        '<div class="batch-eval-progress-detail">' + escapeHtml(data.message) + '</div>'
      );
      $("#progress-bar")
        .removeAttr("style")
        .addClass("progress-bar-custom")
        .text("Queued");

      // Poll evaluation IDs for the progress bar and table rows. Progress is
      // based on real QuestionEvaluation rows (not django-q2 task records,
      // whose retention is limited), so the bar cannot stall on large batches.
      var metaById = {};
      if (data.evaluations && data.evaluations.length) {
        for (var j = 0; j < data.evaluations.length; j++) {
          var evMeta = data.evaluations[j];
          metaById["" + evMeta.id] = {
            repetition: evMeta.repetition,
            totalReps: evMeta.total_repetitions,
          };
        }
      }
      if (data.evaluation_ids && data.evaluation_ids.length) {
        pollEvaluations(data.evaluation_ids, metaById, function(finished, total) {
          if (total > 0) {
            var percent = Math.round((finished / total) * 100);
            $("#progress-bar").css("width", percent + "%").text(finished + "/" + total);
          }
        }, function() {
          // All evaluations reported as completed or failed
          window._batchEvalFinished = true;
          var elapsedMs = Date.now() - window._batchEvalStartTime;
          var elapsedStr = formatDuration(elapsedMs);
          $("#batch-eval-results").prepend(
            '<div>Batch evaluation finished. <span class="batch-eval-time">(Total time: ' + elapsedStr + ')</span></div>'
          );
          $("#loading-indicator").hide();
          $("#progress-bar").css("width", "100%").text("Done");
        });
      } else {
        $("#loading-indicator").hide();
        $("#progress-bar").css("width", "100%").text("Done");
      }

      // Poll per-question details for each evaluation
      if (data.evaluations && data.evaluations.length) {
        for (var j = 0; j < data.evaluations.length; j++) {
          var evMeta = data.evaluations[j];
          pollEvaluationQuestions(evMeta.id, {
            repetition: evMeta.repetition,
            totalReps: evMeta.total_repetitions,
          });
          if (window.addPendingEvaluation && evMeta.id && evMeta.exam_id) {
            window.addPendingEvaluation(evMeta.id, evMeta.exam_id);
          }
        }
      }
    } else {
      $("#loading-indicator").hide();
      $("#batch-eval-errors").html("Unexpected response from server.");
    }
  });
}

$(document).ready(function () {
  // Prevent Enter in user prompt textarea from submitting the form
  $('#user-prompt').on('keydown', function(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
    }
  });

  $("#batch-eval-form").submit(function (event) {
    event.preventDefault(); // Prevent default form submission

    // UI: Reset state
    $("#loading-indicator").show();
    $("#progress-bar").css("width", "0%").text("0%");
    $("#batch-eval-results").html("");
    $("#batch-eval-status-msg").html("");
    $("#batch-eval-errors").html("");
    $("#exam-details").html("");
    $("#batch-eval-table tbody").html("");

    // Collect and prepare data
    const data = collectBatchEvalFormData(this);

    // Fetch and handle response
    fetch(window.location.pathname, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": $("input[name='csrfmiddlewaretoken']").val(),
      },
      body: JSON.stringify(data),
    })
      .then(handleBatchEvalTask)
      .catch((error) => {
        $("#loading-indicator").hide();
        $("#batch-eval-errors").html("Error: " + error.message);
      });
  });
});

/**
 * Formats a duration in milliseconds into a human-readable string.
 * Examples: "5s", "2m 10s", "1h 3m 5s", "1d 2h 3m 5s"
 * @param {number} ms - Duration in milliseconds
 * @returns {string} Human-readable duration
 */
function formatDuration(ms) {
  const sec = Math.floor(ms / 1000) % 60;
  const min = Math.floor(ms / (1000 * 60)) % 60;
  const hr = Math.floor(ms / (1000 * 60 * 60)) % 24;
  const day = Math.floor(ms / (1000 * 60 * 60 * 24));
  let parts = [];
  if (day > 0) parts.push(`${day}d`);
  if (hr > 0) parts.push(`${hr}h`);
  if (min > 0) parts.push(`${min}m`);
  if (sec > 0 || parts.length === 0) parts.push(`${sec}s`);
  return parts.join(' ');
}

/**
 * Updates the evaluation count indicator based on selected exams, models, and repetitions.
 */
function updateEvalCountIndicator() {
  const exams = document.getElementById('exams');
  const models = document.getElementById('models');
  const reps = document.getElementById('repetitions');
  const nExams = exams ? Array.from(exams.selectedOptions).length : 0;
  const nModels = models ? Array.from(models.selectedOptions).length : 0;
  const nReps = reps ? parseInt(reps.value) : 0;
  let total = nExams * nModels * nReps;
  let msg = '';
  if (nExams && nModels && nReps) {
    msg = `Total evaluations to run: <b>${total}</b> (${nExams} exam${nExams>1?'s':''} × ${nModels} model${nModels>1?'s':''} × ${nReps} repetition${nReps>1?'s':''})`;
  } else {
    msg = 'Select at least one exam, one model, and set repetitions.';
  }
  document.getElementById('eval-count-indicator').innerHTML = msg;
}

document.addEventListener('DOMContentLoaded', function() {
  updateEvalCountIndicator();
  document.getElementById('exams').addEventListener('change', updateEvalCountIndicator);
  document.getElementById('models').addEventListener('change', updateEvalCountIndicator);
  document.getElementById('repetitions').addEventListener('input', updateEvalCountIndicator);
});
