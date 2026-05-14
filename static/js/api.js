document.addEventListener("DOMContentLoaded", () => {
    const getContrastColor = (hex) => {
        if (!hex || !hex.startsWith('#') || (hex.length !== 7 && hex.length !== 4)) {
            return '#ffffff';
        }
        const normalized = hex.length === 4
            ? `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}`
            : hex;
        const r = parseInt(normalized.slice(1, 3), 16);
        const g = parseInt(normalized.slice(3, 5), 16);
        const b = parseInt(normalized.slice(5, 7), 16);
        const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
        return luminance > 0.5 ? '#0f172a' : '#ffffff';
    };

    const applyBadgeColors = () => {
        document.querySelectorAll('.family-badge').forEach(badge => {
            const color = badge.dataset.color;
            if (!color) return;
            badge.style.backgroundColor = color;
            badge.style.color = getContrastColor(color);
        });
    };

    // Show form
    document.getElementById('show-form').addEventListener('click', () => {
        document.getElementById('creation-form').style.display = 'block';
    });

    // Create new model
    document.getElementById('create-btn').addEventListener('click', createModel);

    // Main table handler
    document.getElementById('model-table').addEventListener('click', async (e) => {
        const target = e.target;
        const row = target.closest('tr');
        if (!row) return;
        
        const modelId = row.dataset.id;

        // Delete
        if (target.classList.contains('delete-btn')) {
            if (confirm('Delete this model?')) {
                try {
                    const response = await fetch(`/model/delete/${modelId}/`, {
                        method: 'DELETE',
                        headers: {
                            'X-CSRFToken': getCookie('csrftoken')
                        }
                    });
                    
                    if (response.ok) {
                        row.remove();
                    } else {
                        const data = await response.json();
                        alert(data.message || 'Delete error');
                    }
                } catch(error) {
                    alert(error.message);
                }
            }
        }
        
        // Edit
        if (target.classList.contains('edit-btn')) {
            enterEditMode(row);
        }
        
        // Save changes
        if (target.classList.contains('save-btn')) {
            await saveChanges(row, modelId);
        }
        
        // Cancel edit
        if (target.classList.contains('cancel-btn')) {
            cancelEdit(row);
        }
    });

    // Create model function
    async function createModel() {
        const desc = document.getElementById('desc').value.trim();
        const url = document.getElementById('url').value.trim();
        const key = document.getElementById('key').value.trim();

        if (!desc || !url || !key) {
            alert('All fields are required');
            return;
        }

        try {
            const response = await fetch('/model/create/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: new URLSearchParams({description: desc, api_url: url, api_key: key})
            });
            
            const data = await response.json();
            
            if (response.ok) {
                location.reload();
            } else {
                alert(data.message || 'Server error');
            }
        } catch(error) {
            console.error('Error:', error);
            alert('Error creating model: ' + error.message);
        }
    }

    // Edit mode
    function enterEditMode(row) {
        const cells = row.querySelectorAll('td');
        const descCell = cells[0];
        const urlCell = cells[2];
        const keyCell = cells[3];
        const actionsCell = cells[4];

        row.originalContent = {
            description: descCell.dataset.fullValue,
            url: urlCell.dataset.fullValue,
            key: keyCell.dataset.fullValue,
            html: actionsCell.innerHTML
        };

        descCell.innerHTML = `<input type="text" value="${row.originalContent.description}" class="edit-input">`;
        urlCell.innerHTML = `<input type="text" value="${row.originalContent.url}" class="edit-input">`;
        keyCell.innerHTML = `<input type="text" value="${row.originalContent.key}" class="edit-input">`;

        actionsCell.innerHTML = `
            <button class="save-btn">Save</button>
            <button class="cancel-btn">Cancel</button>
        `;
    }

    // Save changes
    async function saveChanges(row, modelId) {
        const inputs = row.querySelectorAll('.edit-input');
        const newData = {
            description: inputs[0].value,
            api_url: inputs[1].value,
            api_key: inputs[2].value
        };

        try {
            const response = await fetch(`/model/update/${modelId}/`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: new URLSearchParams(newData)
            });

            if (response.ok) {
                const cells = row.querySelectorAll('td');
                cells[0].dataset.fullValue = newData.description;
                cells[2].dataset.fullValue = newData.api_url;
                cells[3].dataset.fullValue = newData.api_key;
                
                cells[0].textContent = newData.description;
                cells[2].textContent = newData.api_url;
                cells[3].textContent = newData.api_key.length > 10 
                    ? newData.api_key.substring(0, 7) + '...' 
                    : newData.api_key;
                
                cells[4].innerHTML = row.originalContent.html;
            } else {
                const data = await response.json();
                alert(data.message || 'Save error');
            }
        } catch(error) {
            alert(error.message);
            cancelEdit(row);
        }
    }

    // Cancel edit
    function cancelEdit(row) {
        const cells = row.querySelectorAll('td');
        cells[0].textContent = row.originalContent.description;
        cells[2].textContent = row.originalContent.url;
        cells[3].textContent = row.originalContent.key.length > 10 
            ? row.originalContent.key.substring(0, 7) + '...' 
            : row.originalContent.key;
        cells[4].innerHTML = row.originalContent.html;
    }
document.getElementById('download-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const modelName = document.getElementById('model-name').value;
    const messageBox = document.getElementById('message');

    messageBox.style.display = 'block';
    messageBox.textContent = 'Enqueuing download...';
    messageBox.className = 'message info';

    fetch('/model/pull/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({ model: modelName })
    })
    .then(function(response) {
        if (!response.ok) {
            return response.json().then(function(data) {
                throw new Error(data.message || 'Request failed');
            });
        }
        return response.json();
    })
    .then(function(data) {
        if (data.status === 'queued') {
            messageBox.textContent = 'Downloading ' + modelName + '...';
            messageBox.className = 'message info';
            if (window.addPendingDownload && data.task_id) {
                window.addPendingDownload(data.task_id, modelName);
            }
            pollTask(data.task_id, function(status, result) {
                if (status === 'success') {
                    messageBox.textContent = 'Model downloaded successfully!';
                    messageBox.className = 'message success';
                    setTimeout(function() { location.reload(); }, 2000);
                } else if (status === 'failed') {
                    messageBox.textContent = 'Download failed: ' + (result || 'Unknown error');
                    messageBox.className = 'message error';
                }
            });
        } else if (data.status === 'success') {
            messageBox.textContent = 'Model already downloaded.';
            messageBox.className = 'message success';
            setTimeout(function() { location.reload(); }, 1500);
        } else {
            messageBox.textContent = data.message || 'Unexpected response';
            messageBox.className = 'message error';
        }
    })
    .catch(function(error) {
        messageBox.textContent = error.message || 'Connection error';
        messageBox.className = 'message error';
    });
});

    applyBadgeColors();
});
