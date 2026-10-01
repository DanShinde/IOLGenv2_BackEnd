// Shared chart look ("Soft Gradient") for the tracker's Reports page and Dashboard.
// Load after Chart.js; call RS.applyDefaults() once ChartDataLabels is registered.
// Only appearance lives here -- each chart keeps its own data, tooltip content and clicks.

const RS = {
    font: "Inter, 'Segoe UI', Tahoma, sans-serif",
    ink: '#374151', muted: '#6b7280', grid: '#eef0f6', tooltipBg: '#312e81', target: '#312e81',
    // [solid end, light end] pairs for gradient fills
    indigo: ['#6366f1', '#a5b4fc'], indigoLight: ['#a5b4fc', '#c7d2fe'],
    teal: ['#14b8a6', '#5eead4'], rose: ['#f43f5e', '#fda4af'],
    amber: ['#f59e0b', '#fcd34d'], violet: ['#8b5cf6', '#c4b5fd'],
    amberLine: '#f59e0b',
    // Doughnut slices, in fixed order
    slices: ['#6366f1', '#14b8a6', '#f59e0b', '#f43f5e', '#8b5cf6', '#0ea5e9', '#84cc16', '#ec4899', '#94a3b8', '#f97316', '#0f766e', '#a16207'],

    // Scriptable gradient along the bar's length (left->right for horizontal bars,
    // bottom->top for vertical ones).
    gradient(pair, horizontal) {
        return (ctx) => {
            const area = ctx.chart.chartArea;
            if (!area) return pair[0];
            const g = horizontal
                ? ctx.chart.ctx.createLinearGradient(area.left, 0, area.right, 0)
                : ctx.chart.ctx.createLinearGradient(0, area.bottom, 0, area.top);
            g.addColorStop(0, pair[1]);
            g.addColorStop(1, pair[0]);
            return g;
        };
    },
    // Bar look shared by every bar chart.
    bar(extra) {
        return Object.assign({ borderWidth: 0, borderRadius: 20, borderSkipped: false }, extra);
    },
    // Axes for a horizontal bar chart: value grid only, no axis lines.
    hScales(x) {
        return {
            x: Object.assign({ beginAtZero: true, grid: { color: RS.grid, drawTicks: false }, border: { display: false }, ticks: { padding: 6 } }, x),
            // Small safety margin so the longest name is never clipped at the card edge.
            y: { grid: { display: false }, border: { display: false }, ticks: { autoSkip: false, color: RS.ink, padding: 6 },
                 afterFit: (scale) => { scale.width += 10; } }
        };
    },
    // Axes for a vertical bar chart: value grid only, no axis lines.
    vScales(y) {
        return {
            x: { grid: { display: false }, border: { display: false }, ticks: { color: RS.ink, padding: 6 } },
            y: Object.assign({ beginAtZero: true, grace: '12%', grid: { color: RS.grid, drawTicks: false }, border: { display: false }, ticks: { padding: 6 } }, y)
        };
    },
    // Value labels at the bar end, kept inside the chart.
    endLabels(extra) {
        return Object.assign({ anchor: 'end', align: 'end', offset: 4, clamp: true, color: RS.ink, font: { weight: '600', size: 11 } }, extra);
    },
    applyDefaults() {
        Chart.defaults.font.family = RS.font;
        Chart.defaults.color = RS.muted;
        Chart.defaults.borderColor = RS.grid;
        Object.assign(Chart.defaults.plugins.tooltip, {
            backgroundColor: RS.tooltipBg, titleColor: '#fff', bodyColor: '#e0e7ff',
            padding: 10, cornerRadius: 8, boxPadding: 4, usePointStyle: true,
            titleFont: { family: RS.font, weight: '600', size: 12 }, bodyFont: { family: RS.font, size: 12 }
        });
        Object.assign(Chart.defaults.plugins.legend.labels, {
            usePointStyle: true, pointStyle: 'rectRounded', boxWidth: 10, boxHeight: 10, padding: 14, color: RS.ink
        });
        if (Chart.defaults.plugins.datalabels) {
            Object.assign(Chart.defaults.plugins.datalabels, { color: RS.ink, font: { family: RS.font, weight: '600', size: 11 } });
        }
    }
};

// Dashed 80% target line on the horizontal OTIF bar charts (enable per chart with
// options.plugins.otifTarget = { show: true }).
const otifTargetPlugin = {
    id: 'otifTarget',
    afterDatasetsDraw(chart, _args, opts) {
        if (!opts || !opts.show) return;
        const x = chart.scales.x.getPixelForValue(80);
        const { top, bottom } = chart.chartArea;
        const c = chart.ctx;
        c.save();
        c.strokeStyle = RS.target; c.lineWidth = 1.5; c.setLineDash([5, 4]);
        c.beginPath(); c.moveTo(x, top - 2); c.lineTo(x, bottom); c.stroke();
        c.setLineDash([]);
        c.fillStyle = RS.target; c.font = `600 11px ${RS.font}`; c.textAlign = 'center';
        c.fillText('Target 80%', x, top - 6);
        c.restore();
    }
};

// Total in the middle of a doughnut (options.plugins.centerTotal = { caption: '...',
// format: optional (total) => text }).
const centerTotalPlugin = {
    id: 'centerTotal',
    afterDraw(chart, _args, opts) {
        if (!opts || !opts.caption) return;
        const meta = chart.getDatasetMeta(0);
        if (!meta.data.length) return;
        const { x, y } = meta.data[0];
        const total = chart.data.datasets[0].data.reduce((a, b) => a + (Number(b) || 0), 0);
        const c = chart.ctx;
        c.save();
        c.textAlign = 'center';
        c.fillStyle = '#1b263b'; c.font = `700 24px ${RS.font}`; c.fillText(opts.format ? opts.format(total) : total.toLocaleString(), x, y + 4);
        c.fillStyle = RS.muted; c.font = `500 11px ${RS.font}`; c.fillText(opts.caption, x, y + 21);
        c.restore();
    }
};

// Doughnut look shared by both round charts; slice labels only where they fit.
function doughnutStyle(labels) {
    return {
        backgroundColor: labels.map((_, i) => RS.slices[i % RS.slices.length]),
        borderColor: '#fff', borderWidth: 2, borderRadius: 6, spacing: 3, hoverOffset: 6
    };
}
function doughnutOptions(caption, format) {
    return {
        responsive: true, maintainAspectRatio: false, cutout: '68%',
        layout: { padding: 8 },
        plugins: {
            // Tighter rows so a long list (10+ segments) still fits in one column.
            legend: { position: 'right', labels: { padding: 8 } },
            centerTotal: { caption: caption, format: format },
            datalabels: {
                color: '#fff', font: { weight: '700', size: 11 },
                display: (ctx) => {
                    const data = ctx.dataset.data;
                    const total = data.reduce((a, b) => a + (Number(b) || 0), 0);
                    return total > 0 && data[ctx.dataIndex] / total >= 0.06;
                }
            }
        }
    };
}
