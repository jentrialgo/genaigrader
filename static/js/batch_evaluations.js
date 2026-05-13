/**
 * Parses a progress string from the batch evaluation stream.
 * @param {string} progressStr - The progress string to parse.
 * @returns {object|null} An object with parsed progress fields, or null if parsing fails.
 */
function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function parseProgress(progressData) {
  if (typeof progressData === 'object' && progressData.eval_count !== undefined) {
    return {
      currentEval: progressData.eval_count,
      totalEval: progressData.total_tasks,
      model: progressData.model,
      subject: progressData.subject,
      exam: progressData.exam,
      repetition: String(progressData.rep),
      totalReps: String(progressData.repetitions),
      evalMsg: `Eval ${progressData.eval_count}/${progressData.total_tasks}`,
      detailMsg: `Evaluating <b>${escapeHtml(progressData.model)}</b> on <b>${escapeHtml(progressData.subject)}</b> with <b>${escapeHtml(progressData.exam)}</b> (Repetition ${escapeHtml(String(progressData.rep))}/${escapeHtml(String(progressData.repetitions))})`
    };
  }
  return null;
}

/**
 * Updates the progress bar UI with the current evaluation progress.
 * @param {object} progress - The progress object returned by parseProgress.
 */
function updateProgressBar(progress) {
  $("#progress-bar")
    .removeAttr('style')
    .addClass('progress-bar-custom')
    .text(progress.evalMsg);
  if (!isNaN(progress.currentEval) && !isNaN(progress.totalEval) && progress.totalEval > 0) {
    const percent = Math.round((progress.currentEval / progress.totalEval) * 100);
    $("#progress-bar").css("width", percent + "%");
  }
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
 * Handles the streaming response from the batch evaluation POST request.
 * Reads and processes each chunk of streamed data.
 * @param {Response} response - The fetch response object.
 * @returns {Promise<void>} Resolves when the stream is fully processed.
 */
function handleBatchEvalStream(response) {
  if (!response.ok) {
    $("#loading-indicator").hide();
    $("#batch-eval-results").html("Error starting batch evaluation.");
    throw new Error("Network response was not ok");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = '';
  window._batchEvalFinished = false; // To detect if the stream finished normally

  function processStream({ done, value }) {
    if (done) {
      $("#loading-indicator").hide();

      // If the "done" message was not received, we assume the stream was interrupted
      if (!window._batchEvalFinished) {
        const now = new Date();
        const datetimeStr = now.toLocaleString();
        $("#batch-eval-errors").append(
          `<div class="batch-eval-error">
            <span class="batch-eval-error-date">${datetimeStr}</span>
            Evaluation stream was interrupted or did not finish properly.
            Please check the server logs for more details.
          </div>`
        );
      }

      return;
    }

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || '';
    chunks.forEach(chunk => processBatchEvalChunk(chunk));
    return reader.read().then(processStream);
  }
  return reader.read().then(processStream);
}

/**
 * Processes a single chunk of streamed data from the batch evaluation.
 * Updates the UI based on the type of message received.
 * @param {string} chunk - The chunk of data to process.
 */
function processBatchEvalChunk(chunk) {
  if (chunk.trim() === "") return;
  try {
    const data = JSON.parse(chunk.replace("data: ", ""));
    if (data.error) {
      // Add a row to the table indicating that there was an error
      const lastRow = window._batchEvalLastRow || {};
      const now = new Date();
      const datetimeStr = now.toLocaleString();
      const evalId = window._lastEvalId || '';
      const headingLink = `<a href="#${evalId}" class="details-link" title="View details"><span class="details-icon" aria-label="Details">🔍</span></a>`;

      $("#batch-eval-table").show();
      $("#batch-eval-table tbody").append(
        `<tr class="batch-eval-error-row">
          <td data-label="Date">${headingLink} ${datetimeStr}</td>
          <td data-label="Model">${escapeHtml(lastRow.model || '')}</td>
          <td data-label="Subject">${escapeHtml(lastRow.subject || '')}</td>
          <td data-label="Exam">${escapeHtml(lastRow.exam || '')}</td>
          <td data-label="Repetition">${escapeHtml(lastRow.repetition || '')}</td>
          <td data-label="Grade">Error</td>
          <td data-label="Time">-</td>
        </tr>`
      );

      const errorMsg = `Evaluating <b>${escapeHtml(lastRow.model)}</b> on <b>${escapeHtml(lastRow.subject)}</b> with <b>${escapeHtml(lastRow.exam)}</b> (Repetition ${escapeHtml(lastRow.repetition)}/${escapeHtml(lastRow.totalReps)}): ${escapeHtml(data.error)}`;
      $("#batch-eval-errors").append(`<div class="batch-eval-error">${errorMsg}</div>`);


    } else if (data.progress) {
      const progress = parseProgress(data.progress);
      if (progress) {
        window._batchEvalLastRow = {
          model: progress.model,
          subject: progress.subject,
          exam: progress.exam,
          repetition: progress.repetition,
          totalReps: progress.totalReps,
        };
        window._currentExamDetailKey = `${progress.subject}|||${progress.exam}`;
        window._examDetailHeadingShown = false;
        updateProgressBar(progress);
        $("#batch-eval-results").html(`<div class="batch-eval-progress-detail">${progress.detailMsg}</div>`);
      } else {
        $("#progress-bar").text(typeof data.progress === 'string' ? data.progress : '');
      }
    } else if (data.processed_questions && data.response) {
      // Show per-question result as it arrives
      // Insert heading if not already shown for this exam
      if (!window._examDetailHeadingShown) {
        const key = window._currentExamDetailKey || '';
        if (key) {
          const [subject, exam] = key.split('|||');
          const lastRow = window._batchEvalLastRow || {};
          const model = lastRow.model || '-';
          const repetition = lastRow.repetition || '-';
          const totalReps = lastRow.totalReps || '-';

          // Create a unique evalId for this evaluation
          const evalId = `eval-${btoa(`${model}|${subject}|${exam}|${repetition}|${Date.now()}`).replace(/[^a-zA-Z0-9]/g, '')}`;
          window._lastEvalId = evalId; // Store for use in table row

          const headingHtml = `
            <div id="${evalId}" class="exam-detail-heading exam-detail-heading-margin eval-details-section">
              <span class="exam-detail-label">Model:</span> <span class="exam-detail-value">${escapeHtml(model)} - </span>
              <span class="exam-detail-label">Subject:</span> <span class="exam-detail-value">${escapeHtml(subject)} - </span>
              <span class="exam-detail-label">Exam:</span> <span class="exam-detail-value">${escapeHtml(exam)} - </span>
              <span class="exam-detail-label">Repetition:</span> <span class="exam-detail-value">${escapeHtml(repetition)}/${escapeHtml(totalReps)}</span>
            </div>
          `;
          $("#exam-details").append(headingHtml);
        }
        window._examDetailHeadingShown = true;
      }
      const response = data.response;
      const detailsHtml = `
        <div class="exam-detail-box">
          <b>Question ${data.processed_questions}:</b>
          <pre>${escapeHtml(response.question_prompt)}</pre>
          <b>Model response:</b> <span class="model-response-text ${response.is_correct ? 'correct-response' : 'incorrect-response'}">${escapeHtml(response.response)}</span><br>
          <b>Correct option:</b> ${escapeHtml(response.correct_option)}
          <span class="correctness-icon">${response.is_correct ? "✅" : "❌"}</span>
          <div class="question-time">Time: ${data.time || "-"}s</div>
        </div>
      `;
      $("#exam-details").append(detailsHtml);

      // Add Back to Top link after the last question
      if (
        (typeof response.total_questions !== 'undefined' && data.processed_questions == response.total_questions) ||
        (typeof data.total_questions !== 'undefined' && data.processed_questions == data.total_questions)
      ) {
        $("#exam-details").append('<div class="back-to-top-link-container"><a href="#top" class="back-to-top-link no-underline">⬆ Back to Top</a></div>');
      }

    } else if (data.response) {
      // Use appendResponseDetails from utils.js for consistent UI
      const progressLike = {
        response: data.response,
        time: data.response.time || '-',
        processed_questions: data.response.processed_questions || '-',
        total_questions: data.response.total_questions || '-',
      };
      appendResponseDetails(progressLike);
    } else if (data.processed_questions && data.total_questions) {
      const percent = Math.round((data.processed_questions / data.total_questions) * 100);
      $("#progress-bar").css("width", percent + "%");
    } else if (data.eval_result) {
      // Show the result of the last eval (grade and time)
      const grade = data.eval_result.grade;
      const time = data.eval_result.time;

      // Find or create a summary area
      let $summary = $("#batch-eval-summary");
      if ($summary.length === 0) {
        $summary = $("<div id='batch-eval-summary' class='batch-eval-summary'></div>");
        $("#batch-eval-results").append($summary);
      }
      $summary.html(
        `Result: <b>${escapeHtml(grade)}</b> correct, Time: <b>${escapeHtml(time)}s</b>`
      );

      // Move the summary above the details, but below the progress message
      $("#batch-eval-summary").insertAfter("#batch-eval-results > div:first-child");

      // --- Add row to table ---
      const lastRow = window._batchEvalLastRow || {};
      const now = new Date();
      const datetimeStr = now.toLocaleString();

      // Use the lastEvalId created with the headingHtml for the link
      const evalId = window._lastEvalId || '';
      const headingLink = `<a href="#${evalId}" class="details-link" title="View details"><span class="details-icon" aria-label="Details">🔍</span></a>`;
      $("#batch-eval-table").show();
      $("#batch-eval-table tbody").append(
        `<tr>
          <td data-label="Date">${headingLink} ${datetimeStr}</td>
          <td data-label="Model">${escapeHtml(lastRow.model || '')}</td>
          <td data-label="Subject">${escapeHtml(lastRow.subject || '')}</td>
          <td data-label="Exam">${escapeHtml(lastRow.exam || '')}</td>
          <td data-label="Repetition">${escapeHtml(lastRow.repetition || '')}</td>
          <td data-label="Grade">${escapeHtml(grade)}</td>
          <td data-label="Time">${escapeHtml(time)}</td>
        </tr>`
      );
      if (!document.getElementById(evalId)) {
        // Now append the details section after the table row
        $("#exam-details").append(`<div id="${evalId}" class="eval-details-section"></div>`);
      }
    } else if (data.done) {
      // Do not clear or append, just mark finished
      window._batchEvalFinished = true; // Mark as finished correctly
      let finishedMsg = "Batch evaluation finished.";
      if (window._batchEvalStartTime) {
        const elapsedMs = Date.now() - window._batchEvalStartTime;
        const elapsedStr = formatDuration(elapsedMs);
        finishedMsg += ` <span class="batch-eval-time">(Total time: ${elapsedStr})</span>`;
      }
      $("#batch-eval-results").html(`<div>${finishedMsg}</div>`);
      $("#loading-indicator").hide();
    }
  } catch (e) {
    $("#batch-eval-errors").append(`<div class="batch-eval-error">Error parsing chunk: ${escapeHtml(e.message)}</div>`);
    console.error("Error parsing chunk:", e);
  }
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
    $("#batch-eval-errors").html("");
    $("#exam-details").html("");
    
    // Record start time for batch evaluation
    window._batchEvalStartTime = Date.now();
    
    // Collect and prepare data
    const data = collectBatchEvalFormData(this);
    
    // Fetch and handle stream
    fetch(window.location.pathname, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": $("input[name='csrfmiddlewaretoken']").val(),
      },
      body: JSON.stringify(data),
    })
      .then(handleBatchEvalStream)
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
