function createCourse() {
    const nameInput = document.getElementById('new-course-name');
    const name = nameInput.value.trim();
    
    if (!name) {
        alert('Please enter a valid name');
        return;
    }

    fetch('/course/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: `course_name=${encodeURIComponent(name)}`
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            nameInput.value = '';
            location.reload(); // Reload to show the new course
        } else {
            alert(`Error: ${data.message}`);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error creating the course');
    });
}

function editCourse(button) {
    const courseItem = button.closest('.course-item');
    const courseId = courseItem.dataset.courseId;
    const nameSpan = courseItem.querySelector('.course-name');
    const currentName = nameSpan.textContent;
    
    // Create editing elements
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentName;
    input.className = 'edit-input';
    
    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.className = 'save-btn';
    
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.className = 'cancel-btn';
    
    // Replace element
    const editContainer = document.createElement('div');
    editContainer.className = 'edit-container';
    editContainer.appendChild(input);
    editContainer.appendChild(saveBtn);
    editContainer.appendChild(cancelBtn);
    
    nameSpan.replaceWith(editContainer);
    input.focus();
    
    // Handle save
    saveBtn.onclick = () => {
        const newName = input.value.trim();
        if (!newName) return;
        
        fetch(`/course/update/${courseId}/`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: `name=${encodeURIComponent(newName)}`
        }).then(response => {
            if (response.ok) {
                nameSpan.textContent = newName;
                editContainer.replaceWith(nameSpan);
            }
        });
    };
    
    // Handle cancel
    cancelBtn.onclick = () => {
        editContainer.replaceWith(nameSpan);
    };
}

function deleteCourse(button) { // Receive the button as a parameter
    const courseItem = button.closest('.course-item');
    const courseId = courseItem.dataset.courseId;
    
    // Create confirmation elements
    const confirmationDiv = document.createElement('div');
    confirmationDiv.className = 'confirmation-box';
    
    const confirmText = document.createElement('span');
    confirmText.textContent = 'Delete course?';
    
    const confirmBtn = document.createElement('button');
    confirmBtn.textContent = '✓';
    confirmBtn.className = 'confirm-delete-btn';
    
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = '✕';
    cancelBtn.className = 'cancel-delete-btn';
    
    // Insert elements
    confirmationDiv.appendChild(confirmText);
    confirmationDiv.appendChild(confirmBtn);
    confirmationDiv.appendChild(cancelBtn);
    
    // Replace original buttons
    const actionsDiv = courseItem.querySelector('.course-actions');
    actionsDiv.replaceWith(confirmationDiv);
    
    // Handle confirmation
    confirmBtn.onclick = () => {
        fetch(`/course/delete/${courseId}/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'Content-Type': 'application/json'
            }
        }).then(response => {
            if (response.ok) {
                courseItem.remove(); // Remove element from the DOM without reloading
            } else {
                location.reload(); // Reload on error
            }
        });
    };
    
    // Handle cancel
    cancelBtn.onclick = () => {
        confirmationDiv.replaceWith(actionsDiv); // Restore original buttons
    };
}


function editExam(button) {
    const examItem = button.closest('.exam-item');
    const examId = examItem.dataset.examId;
    const examContent = examItem.querySelector('.exam-content');
    const examLink = examContent.querySelector('.exam-link');
    const originalUrl = examLink.dataset.url; // URL from data-url
    const currentDescription = examContent.querySelector('.exam-description').textContent;

    // Create editing elements
    const editContainer = document.createElement('div');
    editContainer.className = 'exam-edit-container';

    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentDescription;
    input.className = 'exam-edit-input';

    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.className = 'exam-save-btn';

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.className = 'exam-cancel-btn';

    // Replace content
    examContent.replaceWith(editContainer);
    editContainer.append(input, saveBtn, cancelBtn);
    input.focus();

    // Function to restore the content
    const restoreContent = (description) => {
        const newExamContent = document.createElement('div');
        newExamContent.className = 'exam-content';

        const newLink = document.createElement('a');
        newLink.className = 'exam-link';
        newLink.href = originalUrl; // Use saved URL
        newLink.dataset.url = originalUrl;

        const newDescription = document.createElement('span');
        newDescription.className = 'exam-description';
        newDescription.textContent = description;

        const newActions = document.createElement('div');
        newActions.className = 'exam-actions';

        const newEditBtn = document.createElement('button');
        newEditBtn.className = 'edit-btn';
        newEditBtn.textContent = '✏️';
        newEditBtn.onclick = () => editExam(newEditBtn); // Reconnect event

        const newDeleteBtn = document.createElement('button');
        newDeleteBtn.className = 'delete-btn';
        newDeleteBtn.textContent = '🗑️';
        newDeleteBtn.onclick = () => deleteExam(newDeleteBtn); // Reconnect event

        // Build structure
        newLink.appendChild(newDescription);
        newActions.append(newEditBtn, newDeleteBtn);
        newExamContent.append(newLink, newActions);
        
        // Replace in DOM
        editContainer.replaceWith(newExamContent);
    };

    // Save handler
    saveBtn.onclick = async (e) => {
        e.stopPropagation(); // Important!
        const newDescription = input.value.trim();
        
        if (!newDescription) return;

        try {
            const response = await fetch(`/course/exam/update/${examId}/`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: `description=${encodeURIComponent(newDescription)}`
            });
            
            if (response.ok) {
                restoreContent(newDescription);
            }
        } catch (error) {
            console.error('Error:', error);
        }
    };

    // Cancel handler
    cancelBtn.onclick = (e) => {
        e.stopPropagation();
        restoreContent(currentDescription);
    };
}

function deleteExam(button) {
    const examItem = button.closest('li');
    const examId = examItem.dataset.examId;
    
    if (confirm('Delete this exam?')) {
        fetch(`/course/exam/delete/${examId}/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        }).then(response => {
            if (response.ok) {
                examItem.remove(); // Remove from DOM without reloading
            }
        });
    }
}
