// charts.js — Chart.js renderers

const COLORS = [
  '#1a73e8', '#059669', '#d97706', '#dc2626', '#7c3aed',
  '#0891b2', '#be185d', '#4f46e5', '#065f46', '#92400e'
];

function buildDatasets(series, seriesMeta, seriesIds, days) {
  const cutoff = days ? new Date(Date.now() - days * 86400000) : null;

  return seriesIds.map((id, i) => {
    const meta = seriesMeta[id] || { label: id };
    const points = (series[id] || []).filter(p => {
      if (!cutoff) return true;
      return new Date(p.d) >= cutoff;
    });

    return {
      label: meta.label || id,
      data: points.map(p => ({ x: p.d, y: p.p })),
      borderColor: COLORS[i % COLORS.length],
      backgroundColor: COLORS[i % COLORS.length] + '20',
      tension: 0.3,
      spanGaps: false,
      pointRadius: 2,
      pointHoverRadius: 5,
      borderWidth: 2,
    };
  });
}

export function renderLineChart(canvasId, series, seriesMeta, seriesIds, days) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;

  const ctx = canvas.getContext('2d');

  // Destroy previous chart if re-rendering
  if (canvas._chart) {
    canvas._chart.destroy();
  }

  const datasets = buildDatasets(series, seriesMeta, seriesIds, days);

  const chart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            usePointStyle: true,
            pointStyle: 'line',
            padding: 16,
            font: { size: 12 }
          }
        },
        tooltip: {
          callbacks: {
            label(ctx) {
              const val = ctx.parsed.y;
              return `${ctx.dataset.label}: ${val != null ? '$' + val.toFixed(2) : '—'}`;
            }
          }
        }
      },
      scales: {
        x: {
          type: 'category',
          labels: [...new Set(datasets.flatMap(d => d.data.map(p => p.x)))].sort(),
          ticks: {
            maxTicksLimit: 10,
            font: { size: 11 }
          }
        },
        y: {
          ticks: {
            callback(v) { return '$' + v.toFixed(2); },
            font: { size: 11 }
          },
          grid: { color: '#f0f0f0' }
        }
      }
    }
  });

  canvas._chart = chart;
  return chart;
}
