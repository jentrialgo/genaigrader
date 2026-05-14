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
