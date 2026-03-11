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
      headers: { "Cache-Control": "no-cache" },
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
        return handleStreamingResponse(response, updateUI);
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