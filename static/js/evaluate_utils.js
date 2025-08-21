function updateProgressBar(progress) {
  const percentage = (progress.processed_questions / progress.total_questions) * 100;
  $("#progress-bar").css("width", percentage + "%").text(percentage.toFixed(0) + "%");
}

function appendResponseDetails(progress) {
  const response = progress.response;
  const responseClass = response.is_correct ? "correct-response" : "incorrect-response";
  const correctnessIcon = response.is_correct ? "✅" : "❌";
  
  const detailsHtml = `
    <div class="exam-detail-box">
      <p><strong>Response time:</strong> ${progress.time}s</p>
      <p><strong>Prompt:</strong></p>
      <pre>${response.user_prompt}</pre>
      <p><strong>Question ${progress.processed_questions}:</strong></p>
      <pre>${response.question_prompt}</pre>
      <p><strong>Model response:</strong> <span class="model-response-text ${responseClass}">${response.response}</span><span class="correctness-icon">${correctnessIcon}</span></p>
      <p><strong>Correct option:</strong> ${response.correct_option}</p>
      <div class="question-time">Time: ${progress.time}s</div>
    </div>
  `;
  $("#exam-details").append(detailsHtml);
}

function displayFinalResults(progress) {
  let totalTime = progress.total_time ? progress.total_time.toFixed(2) : 'N/A';
  $("#exam-results").html(`
    File processed.<br>
    Correct answers: ${progress.correct_count}/${progress.total_questions}<br>
    Total evaluation time: ${totalTime}s
  `);
}

function updateUI(progress) {
  updateProgressBar(progress);
  appendResponseDetails(progress);
  if (progress.processed_questions === progress.total_questions) {
    displayFinalResults(progress);
  }
}

function handleStreamingResponse(response, onProgress) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = '';

  function processStream({ done, value }) {
    if (done) {
      $("#loading-indicator").hide();
      return;
    }

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || '';

    chunks.forEach(chunk => {
      if (chunk.trim() === "") return;
      try {
        const data = JSON.parse(chunk.replace("data: ", ""));

        // Check for error in stream data
        if (data.error) {
          $("#loading-indicator").hide();
          $("#exam-results").append(`<div class="error-message">${data.error}</div>`);
          return; // Skip further processing of this chunk
        }

        onProgress(data);
      } catch (e) {
        console.error("Error parsing chunk:", e);
      }
    });

    return reader.read().then(processStream);
  }

  return reader.read().then(processStream);
}

function handleErrorResponse(response, defaultMessage) {
  return response.text().then((text) => {
    alert("Model error: " + text);
    $("#loading-indicator").hide();
    $("#exam-results").html(defaultMessage);
    throw new Error(text);
  });
}

function resetUI() {
  $("#exam-results").html("");
  $("#exam-details").html("");
  $("#loading-indicator").show();
  $("#progress-bar").css("width", "0%").text("0%");
}

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}
