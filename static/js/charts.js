// Helper Chart.js sederhana. Data selalu datang dari database lewat template.
const WONTON_RED = '#d65b62', WONTON_PINK = '#f3b9bb';
function rupiahFmt(v) { return 'Rp' + Number(v).toLocaleString('id-ID'); }
function drawChart(id, type, labels, data, label, isMoney, horizontal) {
  const el = document.getElementById(id);
  if (!el || typeof Chart === 'undefined') return;
  new Chart(el, {
    type: type,
    data: { labels: labels, datasets: [{ label: label, data: data, backgroundColor: type === 'line' ? '#d65b6222' : WONTON_PINK,
      borderColor: WONTON_RED, borderWidth: 2, borderRadius: 8, fill: type === 'line', tension: .3, pointRadius: 3 }] },
    options: {
      indexAxis: horizontal ? 'y' : 'x', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ' ' + (isMoney ? rupiahFmt(c.parsed[horizontal ? 'x' : 'y']) : c.parsed[horizontal ? 'x' : 'y'] + ' porsi') } } },
      scales: { [horizontal ? 'x' : 'y']: { beginAtZero: true, ticks: { precision: 0, callback: v => isMoney ? rupiahFmt(v) : v } } }
    }
  });
}
