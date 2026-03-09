$(document).ready(function () {
  function toggleCourseInputs() {
    const courseChoice = $('input[name="course_choice"]:checked').val();
    if (courseChoice === 'new') {
      $('#course-select').hide();
      $('#new-course-input').show().prop('required', true);
    } else {
      $('#course-select').show();
      $('#new-course-input').hide().prop('required', false);
    }
  }

  toggleCourseInputs();
  $('input[name="course_choice"]').change(toggleCourseInputs);

  // Handle form submission
  $("#exam-form").submit(function (event) {
    event.preventDefault();

    const courseChoice = $('input[name="course_choice"]:checked').val();
    if (courseChoice === 'new' && !$('#new-course-input').val().trim()) {
      alert('Please enter the name of the new course');
      return;
    }

    resetUI();
    const formData = new FormData(this);

    //Calls the backend (urls.py) to process the file and stream the results back
    fetch("/upload/", {
      method: "POST",
      body: formData,
      headers: { "Cache-Control": "no-cache" },
    })
      .then((response) => {
        if (!response.ok) {
          //Code that handles in case the exam is already in the BD and has been processed with the same model
          if(response.status === 409){
             //We use a promise that will resolve with the text content of the error.
             return response.text().then((ErrorText) => {
               throw new Error(ErrorText);
               });
          }else{
            return handleErrorResponse(response, "There was an error processing the file.");
          }

        }
        return handleStreamingResponse(response, updateUI);
      })
      .catch((error) => {
        console.error("Error:", error);
        $("#loading-indicator").hide();
        errorMessage = error.message ? error.message : "Error processing the file.";
        $("#exam-results").html(errorMessage);
      });
  });
});
