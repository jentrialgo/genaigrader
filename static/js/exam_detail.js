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
                    columns: [0, 1, 2, 3, 4],
                    format: {
                        body: function(data, row, column, node) {
                            return data.replace(/<[^>]*>/g, '').replace(/�/g, '✓');
                        }
                    }
                },
                customize: function(csv) {
                    return 'Date,Model,Prompt,Grade,Time\n' + csv;
                }
            },
            {
                extend: 'pdf',
                text: 'Export PDF',
                filename: 'evaluations_' + new Date().toISOString().split('T')[0],
                exportOptions: {
                    columns: [0, 1, 2, 3, 4],
                    stripHtml: true
                },
                customize: function(doc) {
                    doc.pageOrientation = 'landscape';
                    doc.content[1].table.widths = ['15%', '20%', '35%', '15%', '15%'];
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
            { orderable: true, targets: [0,1,2,3] },
            { orderable: false, targets: [4] },
            { width: '15%', targets: [0,3,4] },
            { className: 'dt-body-center', targets: [3,4] }
        ],
        language: {
            url: '//cdn.datatables.net/plug-ins/1.13.7/i18n/en-US.json',
            buttons: {
                csv: 'Export CSV',
                pdf: 'Export PDF'
            }
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
//TODO FUNCTION TO SHOW THE AVERAGE PER QUESTION
//Input: A question ID
//Output: A chart with the average grade and time for that question across all evaluations, including the model used.


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