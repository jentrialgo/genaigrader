// Function to get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// DataTables configuration
$(document).ready(function() {
    $('#evaluationsTable').DataTable({
        dom: 'Bfrtip',
        buttons: [
            {
                extend: 'csv',
                text: 'Export CSV',
                filename: 'evaluations_' + new Date().toISOString().split('T')[0],
                exportOptions: {
                    columns: [0, 1, 2, 3, 4, 5],
                    format: {
                        body: function(data, row, column, node) {
                            return data.replace(/<[^>]*>/g, '').replace(/�/g, '✓');
                        }
                    }
                },
                customize: function(csv) {
                    return 'Date,Model,Prompt,Grade,Time,Notes\n' + csv;
                }
            },
            {
                extend: 'pdf',
                text: 'Export PDF',
                filename: 'evaluations_' + new Date().toISOString().split('T')[0],
                exportOptions: {
                    columns: [0, 1, 2, 3, 4, 5],
                    stripHtml: true
                },
                customize: function(doc) {
                    doc.pageOrientation = 'landscape';
                    doc.content[1].table.widths = ['15%', '20%', '30%', '10%', '10%', '15%'];
                    doc.styles.tableHeader = {
                        fillColor: '#3498db',
                        color: '#ffffff',
                        alignment: 'left'
                    };
                    doc.defaultStyle.fontSize = 10;
                    doc.content[0].text = 'Evaluation History - ' + document.querySelector('.course-name').textContent;
                    doc.content[0].alignment = 'center';
                    doc.content[0].margin = [0, 0, 0, 15];
                    doc.content[1].layout = {
                        hLineWidth: function(i, node) { return (i === 0 || i === node.table.body.length) ? 2 : 1; },
                        vLineWidth: function(i, node) { return 0; },
                        hLineColor: function(i) { return '#3498db'; },
                        paddingLeft: function(i) { return 5; },
                        paddingRight: function(i) { return 5; }
                    };
                }
            }
        ],
        order: [[0, 'desc']],
        columnDefs: [
            { orderable: true, targets: [0,1,2,3,4] },
            { orderable: false, targets: [5,6,7] },
            { width: '15%', targets: [0,3,4] },
            { width: '8%', targets: [6,7] },
            { className: 'dt-body-center', targets: [3,4,6,7] }
        ],
        language: {
            url: '//cdn.datatables.net/plug-ins/1.13.7/i18n/en-US.json',
            buttons: {
                csv: 'Export CSV',
                pdf: 'Export PDF'
            }
        }
    });

    // Hardware info modal functionality
    $(document).on('click', '.hardware-info-trigger', function() {
        const hardwareData = $(this).data('hardware');
        if (hardwareData) {
            showHardwareModal(hardwareData);
        }
    });
});

function deleteEvaluation(button) {
    const row = $(button).closest('tr');
    const evalId = row.data('eval-id');
    const table = $('#evaluationsTable').DataTable();

    if (confirm('Delete this evaluation?')) {
        fetch(`/evaluation/delete/${evalId}/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        }).then(response => {
            if(response.ok) {
                table.row(row).remove().draw(false);
            } else {
                alert('Error deleting');
            }
        });
    }
}

function showHardwareModal(hardwareJson) {
    try {
        const hardware = JSON.parse(hardwareJson);
        let content = '<div class="hardware-info-content">';
        
        // System information
        if (hardware.system || hardware.machine || hardware.processor) {
            content += '<h4>System Information</h4><ul>';
            if (hardware.system) content += `<li><strong>OS:</strong> ${hardware.system}</li>`;
            if (hardware.machine) content += `<li><strong>Architecture:</strong> ${hardware.machine}</li>`;
            if (hardware.processor) content += `<li><strong>Processor:</strong> ${hardware.processor}</li>`;
            if (hardware.cpu_count) content += `<li><strong>CPU Cores:</strong> ${hardware.cpu_count}</li>`;
            content += '</ul>';
        }
        
        // GPU/Memory information
        if (hardware.gpu_vram_mb) {
            content += '<h4>Graphics</h4><ul>';
            content += `<li><strong>GPU VRAM:</strong> ${hardware.gpu_vram_mb} MB</li>`;
            content += '</ul>';
        }
        
        // Ollama information  
        if (hardware.ollama_running || hardware.ollama_version) {
            content += '<h4>Ollama Information</h4><ul>';
            if (hardware.ollama_running) content += `<li><strong>Status:</strong> Running</li>`;
            if (hardware.ollama_version) content += `<li><strong>Version:</strong> ${hardware.ollama_version}</li>`;
            content += '</ul>';
        }
        
        // Platform details
        if (hardware.platform) {
            content += '<h4>Platform Details</h4><ul>';
            content += `<li><strong>Platform:</strong> ${hardware.platform}</li>`;
            content += '</ul>';
        }
        
        content += '</div>';
        
        // Create and show modal
        const modal = $(`
            <div class="hardware-modal-overlay">
                <div class="hardware-modal">
                    <div class="hardware-modal-header">
                        <h3>Hardware Information</h3>
                        <button class="hardware-modal-close">&times;</button>
                    </div>
                    <div class="hardware-modal-body">
                        ${content}
                    </div>
                </div>
            </div>
        `);
        
        $('body').append(modal);
        
        // Close modal handlers
        modal.on('click', '.hardware-modal-close, .hardware-modal-overlay', function(e) {
            if (e.target === this) {
                modal.remove();
            }
        });
        
    } catch (e) {
        alert('Error parsing hardware information');
    }
}

// Charts with confidence intervals
document.addEventListener('DOMContentLoaded', function () {
    const modelAverages = JSON.parse(document.getElementById('model-averages-data').textContent);
    const timeAverages = JSON.parse(document.getElementById('time-averages-data').textContent);
    const gradeBarColour = '59,130,246';
    const timeBarColour = '255,99,132';

    const calculateRange = (data) => {
        const yValues = data.flatMap(d => [d.yMin, d.avg, d.yMax]);
        
        if (yValues.length === 0) return { min: -1, max: 1 }; 
        
        const globalMin = Math.min(...yValues);
        const globalMax = Math.max(...yValues);
        
    
        if (globalMin === globalMax) {
            const buffer = Math.abs(globalMin) * 0.5 || 1; 
            return {
                min: globalMin - buffer,
                max: globalMax + buffer
            };
        }
        
    
        const rangeBuffer = (globalMax - globalMin) * 0.2;
        return {
            min: globalMin - rangeBuffer,
            max: globalMax + rangeBuffer
        };
    }

    const createErrorBarChart = (canvas, data, field, title, color, decimals = 2) => {
        const yRange = calculateRange(data);
        
        new Chart(canvas, {
            type: 'barWithErrorBars',
            data: {
                labels: data.map(d => d.model__description),
                datasets: [{
                    label: title,
                    data: data.map(item => ({
                        x: item.model__description,
                        y: item[field],
                        yMin: item.yMin,
                        yMax: item.yMax
                    })),
                    backgroundColor: `rgba(${color}, 0.3)`,
                    borderColor: `rgba(${color}, 1)`,
                    borderWidth: 1,
                    borderRadius: 4,
                    errorBarWhiskerColor: '#FFF',
                    errorBarColor: '#FFF'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: ctx => {
                                const r = ctx.raw;
                                return `${title}: ${r.y.toFixed(decimals)} (${r.yMin.toFixed(decimals)} - ${r.yMax.toFixed(decimals)})`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'category',
                        ticks: { color: '#94a3b8' },
                        grid: { display: false }
                    },
                    y: {
                        beginAtZero: false,
                        ticks: {
                            color: '#94a3b8',
                            callback: v => v.toFixed(decimals)
                        },
                        grid: { color: 'rgba(51, 65, 85, 0.5)' },
                        min: yRange.min,
                        max: yRange.max
                    }
                }
            }
        });
    };

    if (modelAverages.length) {
        createErrorBarChart(
            document.getElementById('modelAveragesChart'),
            modelAverages,
            'avg',
            'Grades',
            gradeBarColour,
            2
        );
    }
    
    if (timeAverages.length) {
        createErrorBarChart(
            document.getElementById('timeAveragesChart'),
            timeAverages,
            'avg',
            'Time (s)',
            timeBarColour,
            1
        );
    }
});