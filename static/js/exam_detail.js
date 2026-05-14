// DataTables configuration
$(document).ready(function() {
    // Poll for evaluation task completion if eval_id is in the URL
    var urlParams = new URLSearchParams(window.location.search);
    var evalId = urlParams.get('eval_id');
    if (evalId) {
        var taskIds = JSON.parse(sessionStorage.getItem("eval_task_ids") || "[]");
        if (taskIds.length) {
            var activePoller = null;
            var renderedTasks = {};
            var pollStartTimer = null;

            function cleanupPolling() {
                sessionStorage.removeItem("eval_task_ids");
                if (activePoller) {
                    activePoller.stop();
                    activePoller = null;
                }
                if (pollStartTimer) {
                    clearTimeout(pollStartTimer);
                    pollStartTimer = null;
                }
            }

            $(window).on("beforeunload", cleanupPolling);

            pollStartTimer = setTimeout(function() {
                activePoller = pollBatchTasks(taskIds, function(finished, total, results, pending) {
                    var pct = Math.round((finished / total) * 100);
                    $('#eval-progress-fill').css('width', pct + '%');
                    $('#eval-progress-text').text(finished + ' / ' + total);

                    for (var i = 0; i < results.length; i++) {
                        var r = results[i];
                        if (r.status === 'success' && r.result && !renderedTasks[r.task_id]) {
                            renderedTasks[r.task_id] = true;
                            appendQuestionResult(r.result);
                        } else if (r.status === 'failed' && !renderedTasks[r.task_id]) {
                            renderedTasks[r.task_id] = true;
                            appendQuestionResult({error: r.result || 'Task failed', task_id: r.task_id});
                        }
                    }
                }, function(results) {
                    // All tasks finished – confirm via evaluation status endpoint
                    checkEvaluationComplete(evalId, function() {
                        cleanupPolling();
                        window.location.search = '';
                    });
                }, 2000);
            }, 1000);
        }
    }

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
                        body: function(data) {
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
                        vLineWidth: function() { return 0; },
                        hLineColor: function() { return '#3498db'; },
                        paddingLeft: function() { return 5; },
                        paddingRight: function() { return 5; }
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
            buttons: {
                csv: 'Export CSV',
                pdf: 'Export PDF'
            }
        }
    });
});

function appendQuestionResult(result) {
    var $container = $('#live-evaluation-results');
    if ($container.length === 0) return;

    if (result.error) {
        $container.append(
            '<div class="eval-question-card eval-question-error">' +
            '<b>Error:</b> ' + escapeHtml(result.error) +
            '</div>'
        );
        return;
    }

    var correctnessClass = result.is_correct ? 'correct-response' : 'incorrect-response';
    var icon = result.is_correct ? '✅' : '❌';
    var html =
        '<div class="eval-question-card">' +
        '<div class="eval-question-header">Question ' + result.question_id + ' ' + icon + '</div>' +
        '<div class="eval-question-body">' +
        '<b>Response:</b> <span class="model-response-text ' + correctnessClass + '">' + escapeHtml(result.response) + '</span><br>' +
        '<b>Time:</b> ' + (result.question_time || '-') + 's' +
        '</div>' +
        '</div>';
    $container.append(html);
}

function escapeHtml(text) {
    if (!text) return '';
    return $('<div>').text(text).html();
}

function checkEvaluationComplete(evalId, onComplete) {
    var attempts = 0;
    var maxAttempts = 30;
    function check() {
        fetch('/evaluation/' + evalId + '/status/')
            .then(function(r) {
                var ct = r.headers.get("content-type") || "";
                if (!r.ok || r.redirected || ct.indexOf("application/json") === -1) {
                    throw new Error("Invalid response or session expired");
                }
                return r.json();
            })
            .then(function(data) {
                if (data.status === 'completed' || data.status === 'failed') {
                    onComplete();
                } else if (attempts < maxAttempts) {
                    attempts++;
                    setTimeout(check, 2000);
                } else {
                    onComplete();
                }
            })
            .catch(function() {
                if (attempts < maxAttempts) {
                    attempts++;
                    setTimeout(check, 2000);
                } else {
                    onComplete();
                }
            });
    }
    check();
}

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

const DEFAULT_MODEL_COLOR = JSON.parse(document.getElementById('default-model-color').textContent);

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

// Global function to convert HEX colors to RGBA so all charts can use it
const hexToRgba = (hex, alpha = 0.3) => {
    if (!hex || typeof hex !== 'string' || !hex.startsWith('#')) {
        hex = DEFAULT_MODEL_COLOR;
    }
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
};

// Charts with confidence intervals
document.addEventListener('DOMContentLoaded', function () {
    const modelAverages = JSON.parse(document.getElementById('model-averages-data').textContent);
    const timeAverages = JSON.parse(document.getElementById('time-averages-data').textContent);

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
    const createErrorBarChart = (canvas, data, field, title, decimals = 2) => {
        const yRange = calculateRange(data);
        const labels = data.map(d => d.model__description);

        const bgColors = data.map(item => hexToRgba(item.model_color || DEFAULT_MODEL_COLOR, 0.3));
        const borderColors = data.map(item => item.model_color || DEFAULT_MODEL_COLOR);

        const datasets = [{
            label: title,
            data: data.map(item => ({
                x: item.model__description,
                y: item[field],
                yMin: item.yMin,
                yMax: item.yMax
            })),
            backgroundColor: bgColors,
            borderColor: borderColors,
            borderWidth: 2,
            borderRadius: 4,
            errorBarWhiskerColor: '#cbd5e1',
            errorBarColor: '#cbd5e1'
        }];

        if (canvas.chartInstance) canvas.chartInstance.destroy();

        canvas.chartInstance = new Chart(canvas, {
            type: 'barWithErrorBars',
            data: {
                labels,
                datasets
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
            2
        );
    }

    if (timeAverages.length) {
        createErrorBarChart(
            document.getElementById('timeAveragesChart'),
            timeAverages,
            'avg',
            'Time (s)',
            1
        );
    }
});

function loadQuestionAnalytics(questionId, questionNumber) {
    const tbody = document.getElementById(`analyticsBody--${questionId}`);
    const table = document.getElementById(`questionAnalyticsTable--${questionId}`);
    tbody.innerHTML = '<tr><td colspan="3" class="analytics-state-cell">Loading data...</td></tr>';
    if (table) {
        table.classList.remove('analytics-table-hidden');
        table.style.display = 'table';
    }

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

                    const row = document.createElement('tr');

                    const nameCell = document.createElement('td');
                    nameCell.className = 'analytics-model-cell';
                    const colorDot = document.createElement('span');
                    colorDot.className = 'analytics-model-dot';
                    colorDot.style.backgroundColor = stat.model_color || DEFAULT_MODEL_COLOR;
                    const nameText = document.createElement('span');
                    nameText.textContent = stat.model_name;
                    nameCell.appendChild(colorDot);
                    nameCell.appendChild(nameText);

                    const accuracyCell = document.createElement('td');
                    accuracyCell.textContent = `${stat.accuracy} %`;

                    const totalCell = document.createElement('td');
                    totalCell.textContent = stat.total_evaluations;

                    row.appendChild(nameCell);
                    row.appendChild(accuracyCell);
                    row.appendChild(totalCell);
                    tbody.appendChild(row);
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="3" class="analytics-state-error">Error: ${data.error}</td></tr>`;
            }
        })
        .catch(error => {
            console.error("Error loading analytics:", error);
            tbody.innerHTML = '<tr><td colspan="3" class="analytics-state-error">Connection error.</td></tr>';
            if (table) {
                table.classList.remove('analytics-table-hidden');
                table.style.display = 'table';
            }
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
            color: stat.model_color || DEFAULT_MODEL_COLOR,
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

            const color = model.color || questionAnalyticsState.colors[index % questionAnalyticsState.colors.length];
            const values = questionOrder.map(question => model.values.get(question.id) ?? null);
            const totals = questionOrder.map(question => model.totals.get(question.id) ?? 0);

            return {
                label: model.modelName,
                data: values,
                backgroundColor: hexToRgba(color, 0.6),
                borderColor: color,
                borderWidth: 1,
                borderRadius: 4,
                totals: totals
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
        type: 'bar',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    labels: { color: '#cbd5e1' }
                },
                tooltip: {
                    callbacks: {
                        label(context) {
                            const accuracy = context.raw;
                            const total = context.dataset.totals[context.dataIndex];
                            if (accuracy === null || Number.isNaN(accuracy)) {
                                return `${context.dataset.label}: no data`;
                            }
                            return `${context.dataset.label}: ${Number(accuracy).toFixed(2)}% (${total} evals)`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#94a3b8' },
                    grid: { display: false }
                },
                y: {
                    min: 0,
                    max: 100,
                    ticks: {
                        color: '#94a3b8',
                        callback: value => `${value}%`
                    },
                    grid: { color: 'rgba(51, 65, 85, 0.2)' }
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