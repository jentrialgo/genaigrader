/**
 * GenAI Grader - Profile Settings Logic
 * Handles enabling the save button only when there are real changes.
 */

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("profile-settings-form");
    const saveBtn = document.getElementById("save-settings-btn");

    // Exit if elements do not exist on the current page
    if (!form || !saveBtn) return;

    // Select only fields that are not disabled (Username is usually disabled)
    const editableFields = Array.from(
        form.querySelectorAll("input[name='first_name'], input[name='last_name'], input[name='email']:not([disabled])")
    );

    // Store the original values when the page loads
    const initialState = editableFields.map(field => field.value);

    /**
     * Compares the current state with the initial to enable/disable the button
     */
    const updateButtonState = () => {
        const isChanged = editableFields.some((field, index) => field.value !== initialState[index]);
        saveBtn.disabled = !isChanged;
    };

    editableFields.forEach(field => {
        field.addEventListener("input", updateButtonState);
        field.addEventListener("change", updateButtonState);
    });

    updateButtonState();
});