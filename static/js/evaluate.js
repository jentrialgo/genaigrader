$(document).ready(function () {
  const examNameInput = $("#user-exam");
  const examNameError = $("#user-exam-error");

  function escapeHtml(text) {
    return $("<div>").text(text || "").html();
  }

  function showExamNameError(content, isHtml = false) {
    examNameInput.addClass("is-invalid").attr("aria-invalid", "true");
    examNameInput.removeClass("is-invalid-highlight");
    if (isHtml) {
      examNameError.html(content);
    } else {
      examNameError.text(content);
    }
    examNameError.addClass("is-visible");
    const inputElement = examNameInput.get(0);
    if (inputElement) {
      inputElement.scrollIntoView({ behavior: "smooth", block: "center" });
      inputElement.focus();
      examNameInput.addClass("is-invalid-highlight");
    }
  }

  function clearExamNameError() {
    examNameInput.removeClass("is-invalid is-invalid-highlight").removeAttr("aria-invalid");
    examNameError.text("").removeClass("is-visible");
  }

  function toggleCourseInputs() {
    const courseChoice = $('input[name="course_choice"]:checked').val();
    if (courseChoice === "new") {
      $("#course-select").hide();
      $("#new-course-input").show().prop("required", true);
    } else {
      $("#course-select").show();
      $("#new-course-input").hide().prop("required", false);
    }
  }

  toggleCourseInputs();
  $('input[name="course_choice"]').change(toggleCourseInputs);


  examNameInput.on("input", clearExamNameError);

  function buildDuplicateExamMessage(payload) {
    const examName = escapeHtml(payload.exam_name || "Unknown");
    const courseName = escapeHtml(payload.course_name || "Unknown");

    return `
      <p class="field-error-title">${escapeHtml(payload.message || "An exam with this name already exists in this course.")}</p>
      <ul class="field-error-list">
        <li><strong>If it is a different exam:</strong> Rename the uploaded file or change the <strong>Exam name</strong> field.</li>
        <li><strong>If it is the same exam:</strong> Do not re-upload. Open the existing exam or use Batch Evaluation to compare models.</li>
      </ul>
    `;
  }

  function pollSingleExamQuestions(evalId, examId) {
    var rendered = {};
    var totalQuestions = null;
    var retries = 0;
    var MAX_RETRIES = 10;
    var interval = setInterval(function() {
      fetch("/evaluation/" + evalId + "/questions/")
        .then(function(r) {
          var ct = r.headers.get("content-type") || "";
          if (!r.ok || r.redirected || ct.indexOf("application/json") === -1) {
            clearInterval(interval);
            return null;
          }
          return r.json();
        })
        .then(function(data) {
          if (!data || !data.questions) return;
          retries = 0;
          if (totalQuestions === null) {
            totalQuestions = data.total_questions;
          }

          for (var i = 0; i < data.questions.length; i++) {
            var q = data.questions[i];
            if (rendered[q.question_id]) continue;
            rendered[q.question_id] = true;

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
            $("#exam-results").html(
              '<p class="error-message">Evaluation failed.</p>'
            );
            $("#loading-indicator").hide();
            $("#progress-bar").css("width", "100%").text("Failed");
            return;
          }

          if (data.status === "completed" || (data.questions.length >= totalQuestions && totalQuestions > 0)) {
            clearInterval(interval);
            var examLink = '/exam/' + examId + '/?eval_id=' + evalId;
            $("#exam-results").html(
              '<p>Evaluation complete. <a href="' + examLink + '">View exam details</a></p>'
            );
            $("#loading-indicator").hide();
            $("#progress-bar").css("width", "100%").text("Done");
          }
        })
        .catch(function() {
          retries++;
          if (retries >= MAX_RETRIES) {
            clearInterval(interval);
            $("#exam-results").html(
              '<p class="error-message">Lost connection to server. Please reload the page.</p>'
            );
            $("#loading-indicator").hide();
          }
        });
    }, 2000);
    return interval;
  }

  function handleQueuedEvaluation(data) {
    sessionStorage.setItem("eval_task_ids", JSON.stringify(data.task_ids));

    $("#progress-bar")
      .removeAttr("style")
      .addClass("progress-bar-custom")
      .text("Queued");

    pollBatchTasks(data.task_ids, function(finished, total, results, pending) {
      var percent = Math.round((finished / total) * 100);
      $("#progress-bar").css("width", percent + "%").text(finished + "/" + total);
    }, function(results) {
      // All tasks done — final progress set by pollSingleExamQuestions
    }, 2000);

    pollSingleExamQuestions(data.evaluation_id, data.exam_id);

    if (window.addPendingEvaluation && data.evaluation_id && data.exam_id) {
      window.addPendingEvaluation(data.evaluation_id, data.exam_id);
    }
  }

  $("#exam-form").submit(function (event) {
    event.preventDefault();

    const courseChoice = $('input[name="course_choice"]:checked').val();
    if (courseChoice === "new" && !$("#new-course-input").val().trim()) {
      alert("Please enter the name of the new course");
      return;
    }

    clearExamNameError();
    resetUI();
    const formData = new FormData(this);

    let duplicateConflictHandled = false;

    fetch("/upload/", {
      method: "POST",
      body: formData,
      headers: {
        "Cache-Control": "no-cache",
        "X-CSRFToken": getCookie("csrftoken"),
      },
    })
      .then((response) => {
        if (!response.ok) {
          if (response.status === 409) {
            return response.json().then((payload) => {
              $("#loading-indicator").hide();
              if (payload && payload.error === "duplicate_exam") {
                showExamNameError(buildDuplicateExamMessage(payload), true);
                duplicateConflictHandled = true;
                throw new Error(payload.message || "An exam with this name already exists in this course.");
              }
              throw new Error("A conflict was detected while uploading the exam.");
            });
          }
          return handleErrorResponse(response, "There was an error processing the file.");
        }

        return response.json().then((data) => {
            if (data.status === "queued" && data.task_ids) {
              handleQueuedEvaluation(data);
            } else if (data.status === "success") {
              window.location.href = "/exam/" + data.exam_id + "/";
            }
          });
      })
      .catch((error) => {
        if (duplicateConflictHandled) {
          return;
        }
        console.error("Error:", error);
        $("#loading-indicator").hide();
        const errorMessage = error.message ? error.message : "Error processing the file.";
        $("#exam-results").html(`<div class="error-message">${errorMessage}</div>`);
      });
  });

});