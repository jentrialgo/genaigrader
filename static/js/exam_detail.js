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
                            return data.replace(/<[^>]*>/g, '').replace(/\?/g, '✓');
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

const questionAnalyticsState = {
    questionOrder: [],
    modelMap: new Map(),
    pendingRequests: 0,
    chart: null,
    colors: [
        '#60a5fa', '#f472b6', '#34d399', '#fbbf24', '#a78bfa',
        '#fb7185', '#22d3ee', '#f97316', '#818cf8', '#4ade80'
    ]
};

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

function loadQuestionAnalytics(questionId, questionNumber) {
    const tbody = document.getElementById(`analyticsBody--${questionId}`);
    const table = document.getElementById(`questionAnalyticsTable--${questionId}`);
    tbody.innerHTML = '<tr><td colspan="3" class="analytics-state-cell">Loading data...</td></tr>';
    table.style.display = 'table';

    fetch(`/question/${questionId}/analytics/`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                tbody.innerHTML = '';
                if (data.data.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="3" class="analytics-state-cell">No evaluations yet.</td></tr>';
                    return;
                }
                data.data.forEach(stat => {
                    registerQuestionAnalytics(stat, questionId, questionNumber);
                    tbody.innerHTML += `
                        <tr>
                            <td><strong>${stat.model_name}</strong></td>
                            <td>${stat.accuracy} %</td>
                            <td>${stat.total_evaluations}</td>
                        </tr>
                    `;
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="3" class="analytics-state-error">Error: ${data.error}</td></tr>`;
            }
        })
        .catch(error => {
            console.error("Error loading analytics:", error);
            tbody.innerHTML = '<tr><td colspan="3" class="analytics-state-error">Connection error.</td></tr>';
        })
        .finally(() => {
            questionAnalyticsState.pendingRequests -= 1;
            if (questionAnalyticsState.pendingRequests === 0) {
                initializeModelFilters();
                renderQuestionAccuracyChart();
            }
        });
}

function registerQuestionAnalytics(stat, questionId, questionNumber) {
    const modelId = String(stat.model_id);
    const accuracy = Number(stat.accuracy);
    const totalEvaluations = Number(stat.total_evaluations);

    if (!questionAnalyticsState.modelMap.has(modelId)) {
        questionAnalyticsState.modelMap.set(modelId, {
            modelId,
            modelName: stat.model_name,
            values: new Map(),
            totals: new Map()
        });
    }

    const modelEntry = questionAnalyticsState.modelMap.get(modelId);
    modelEntry.values.set(String(questionId), accuracy);
    modelEntry.totals.set(String(questionId), totalEvaluations);

    if (!questionAnalyticsState.questionOrder.find(item => item.id === String(questionId))) {
        questionAnalyticsState.questionOrder.push({
            id: String(questionId),
            number: Number(questionNumber)
        });
        questionAnalyticsState.questionOrder.sort((a, b) => a.number - b.number);
    }
}

function initializeModelFilters() {
    const filterContainer = document.getElementById('modelFilterContainer');
    const feedback = document.getElementById('questionAccuracyFeedback');

    if (!filterContainer || !feedback) {
        return;
    }

    filterContainer.innerHTML = '';

    const models = Array.from(questionAnalyticsState.modelMap.values())
        .sort((a, b) => a.modelName.localeCompare(b.modelName));

    if (!models.length) {
        feedback.textContent = 'No analytics available yet. Run evaluations to see this chart.';
        return;
    }

    feedback.textContent = `${models.length} model(s) available. Use the filters to compare results.`;

    models.forEach(model => {
        const label = document.createElement('label');
        label.className = 'model-filter-item';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'model-filter-checkbox';
        checkbox.value = model.modelId;
        checkbox.checked = true;
        checkbox.addEventListener('change', renderQuestionAccuracyChart);

        const text = document.createElement('span');
        text.className = 'model-filter-label';
        text.textContent = model.modelName;

        label.appendChild(checkbox);
        label.appendChild(text);
        filterContainer.appendChild(label);
    });
}

function getSelectedModelIds() {
    return Array.from(document.querySelectorAll('.model-filter-checkbox:checked')).map(input => input.value);
}

function renderQuestionAccuracyChart() {
    const chartCanvas = document.getElementById('questionAccuracyChart');
    const feedback = document.getElementById('questionAccuracyFeedback');
    const selectedIds = getSelectedModelIds();

    if (!chartCanvas || !feedback) {
        return;
    }

    if (questionAnalyticsState.chart) {
        questionAnalyticsState.chart.destroy();
        questionAnalyticsState.chart = null;
    }

    if (!selectedIds.length) {
        feedback.textContent = 'Select at least one model to display the chart.';
        updateProblematicQuestions([]);
        return;
    }

    const questionOrder = questionAnalyticsState.questionOrder;
    const labels = questionOrder.map(item => `Q${item.number}`);

    const datasets = selectedIds
        .map((modelId, index) => {
            const model = questionAnalyticsState.modelMap.get(modelId);
            if (!model) {
                return null;
            }

            const color = questionAnalyticsState.colors[index % questionAnalyticsState.colors.length];
            const values = questionOrder.map(question => model.values.get(question.id) ?? null);
            const totals = questionOrder.map(question => model.totals.get(question.id) ?? 0);

            return {
                label: model.modelName,
                data: values,
                borderColor: color,
                backgroundColor: `${color}22`,
                tension: 0.25,
                spanGaps: true,
                pointRadius: 4,
                pointHoverRadius: 6,
                totals
            };
        })
        .filter(Boolean);

    if (!datasets.length) {
        feedback.textContent = 'No data available for the selected model set.';
        updateProblematicQuestions([]);
        return;
    }

    feedback.textContent = `Showing ${datasets.length} model(s) across ${labels.length} question(s).`;

    questionAnalyticsState.chart = new Chart(chartCanvas, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'nearest',
                intersect: false
            },
            plugins: {
                legend: {
                    labels: { color: '#cbd5e1' }
                },
                tooltip: {
                    callbacks: {
                        label(context) {
                            const accuracy = context.parsed.y;
                            const total = context.dataset.totals[context.dataIndex];
                            if (accuracy === null || Number.isNaN(accuracy)) {
                                return `${context.dataset.label}: no data`;
                            }
                            return `${context.dataset.label}: ${accuracy.toFixed(2)}% (${total} evals)`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#94a3b8' },
                    grid: { color: 'rgba(51, 65, 85, 0.35)' }
                },
                y: {
                    min: 0,
                    max: 100,
                    ticks: {
                        color: '#94a3b8',
                        callback: value => `${value}%`
                    },
                    grid: { color: 'rgba(51, 65, 85, 0.5)' }
                }
            }
        }
    });

    updateProblematicQuestions(datasets);
}

function updateProblematicQuestions(datasets) {
    const problematicContainer = document.getElementById('problematicQuestions');
    if (!problematicContainer) {
        return;
    }

    if (!datasets.length) {
        problematicContainer.innerHTML = '';
        return;
    }

    const ranking = questionAnalyticsState.questionOrder
        .map((question, index) => {
            const values = datasets
                .map(dataset => dataset.data[index])
                .filter(value => value !== null && value !== undefined);

            if (!values.length) {
                return null;
            }

            const average = values.reduce((sum, value) => sum + value, 0) / values.length;
            return {
                number: question.number,
                average
            };
        })
        .filter(Boolean)
        .sort((a, b) => a.average - b.average)
        .slice(0, 5);

    if (!ranking.length) {
        problematicContainer.innerHTML = '';
        return;
    }

    problematicContainer.innerHTML = [
        '<h4 class="problematic-title">Most problematic questions</h4>',
        '<div class="problematic-list">',
        ...ranking.map(item =>
            `<div class="problematic-item">Question ${item.number}: ${item.average.toFixed(2)}% avg accuracy</div>`
        ),
        '</div>'
    ].join('');
}

$(document).ready(function() {
    const questionContainers = document.querySelectorAll('[id^="questionAnalyticsContainer--"]');
    questionAnalyticsState.pendingRequests = questionContainers.length;

    questionContainers.forEach(container => {
        const questionId = container.id.split('--')[1];
        const questionNumber = container.dataset.questionNumber;
        if (questionId && questionNumber) {
            loadQuestionAnalytics(questionId, questionNumber);
        } else {
            questionAnalyticsState.pendingRequests -= 1;
        }
    });

    const selectAllModelsBtn = document.getElementById('selectAllModels');
    const clearAllModelsBtn = document.getElementById('clearAllModels');

    if (selectAllModelsBtn) {
        selectAllModelsBtn.addEventListener('click', function() {
            document.querySelectorAll('.model-filter-checkbox').forEach(input => {
                input.checked = true;
            });
            renderQuestionAccuracyChart();
        });
    }

    if (clearAllModelsBtn) {
        clearAllModelsBtn.addEventListener('click', function() {
            document.querySelectorAll('.model-filter-checkbox').forEach(input => {
                input.checked = false;
            });
            renderQuestionAccuracyChart();
        });
    }

    if (!questionContainers.length) {
        const feedback = document.getElementById('questionAccuracyFeedback');
        if (feedback) {
            feedback.textContent = 'No questions available for analytics.';
        }
    }
});