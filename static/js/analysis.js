document.addEventListener('DOMContentLoaded', function () {
    const courseData = JSON.parse(document.getElementById('course-data').textContent);
    const overallGrades = JSON.parse(document.getElementById('overall-grades').textContent);
    const overallTimes = JSON.parse(document.getElementById('overall-times').textContent);

    /**
     * Creates a bar chart with error bars only for models with data
     * @param {HTMLCanvasElement} canvas
     * @param {Array} rawData
     * @param {string} field
     * @param {string} title
     * @param {string} colorRGB
     * @param {number} decimals
     * @param {{min: number, max: number}} yRange
     */
    const createErrorBarChart = (canvas, rawData, field, title, colorRGB, decimals = 2, yRange) => {
        const labels = rawData.map(d => d.model__description);
        const data = rawData.map(item => ({ x: item.model__description, y: item[field], yMin: item.yMin, yMax: item.yMax, count: item.count }));

        if (canvas.chartInstance) canvas.chartInstance.destroy();
        canvas.chartInstance = new Chart(canvas.getContext('2d'), {
            type: 'barWithErrorBars',
            data: { labels, datasets: [{ label: title, data, backgroundColor: `rgba(${colorRGB}, 0.3)`, borderColor: `rgba(${colorRGB}, 1)`, borderWidth: 1, borderRadius: 4, errorBarWhiskerColor: `#FFF`, errorBarColor: `#FFF` }] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                parsing: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: ctx => {
                                const r = ctx.raw;
                                const evaluationText = r.count === 1 ? 'evaluation' : 'evaluations';
                                return `${title}: ${r.y.toFixed(decimals)} (${r.yMin.toFixed(decimals)} - ${r.yMax.toFixed(decimals)}) | ${r.count} ${evaluationText}`;
                            } } }
                },
                scales: {
                    x: { type: 'category', ticks: { color: '#94a3b8' }, grid: { display: false } },
                    y: Object.assign({
                        beginAtZero: false,
                        ticks: { color: '#94a3b8', callback: v => v.toFixed(decimals) },
                        grid: { color: 'rgba(51, 65, 85, 0.5)' }
                    }, yRange)
                }
            }
        });
    };

    const calculateRange = (data) => {
        const yMins = data.map(d => d.yMin);
        const yMaxs = data.map(d => d.yMax);
        return {
            min: Math.min(...yMins, 0),
            max: Math.max(...yMaxs) + 2
        };
    };

    const gradeBarColour = '59,130,246';
    const timeBarColour = '255,99,132';
    
    // Course charts
    courseData.forEach(course => {
        const g = document.getElementById(`grade-chart-${course.course.id}`);
        const t = document.getElementById(`time-chart-${course.course.id}`);
        
        if (course.model_averages.length) {
            const yRange = calculateRange(course.model_averages);
            createErrorBarChart(g, course.model_averages, 'avg', 'Grades', gradeBarColour, 2, yRange);
        }
        if (course.time_averages.length) {
            const yRange = calculateRange(course.time_averages);
            createErrorBarChart(t, course.time_averages, 'avg', 'Time (s)', timeBarColour, 1, yRange);
        }
    });

    // Global charts
    if (overallGrades.length) {
        const yRange = calculateRange(overallGrades);
        createErrorBarChart(document.getElementById('overall-grade-chart'), overallGrades, 'avg', 'Global Grades', gradeBarColour, 2, yRange);
    }
    if (overallTimes.length) {
        const yRange = calculateRange(overallTimes);
        createErrorBarChart(document.getElementById('overall-time-chart'), overallTimes, 'avg', 'Global Time (s)', timeBarColour, 1, yRange);
    }
});