(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();

  var el = document.getElementById('chart-summary');
  if (!el) return;
  var chart = echarts.init(el, null, { renderer: 'svg' });
  chart.setOption({
    animation: false,
    tooltip: { trigger: 'item', appendToBody: true },
    legend: { bottom: 5, textStyle: { color: muted, fontSize: 12 } },
    series: [{
      type: 'pie',
      radius: ['35%', '65%'],
      center: ['50%', '45%'],
      data: window.NEWS_SUMMARY || [],
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      label: { color: ink, fontSize: 12 }
    }],
    color: [accent, accent2, '#0f9d58', '#e8730f', '#c9a227', muted, '#7db4ff']
  });
  window.addEventListener('resize', function() { chart.resize(); });
})();
