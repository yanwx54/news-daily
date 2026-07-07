(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var accent3 = style.getPropertyValue('--accent3').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- Chart 1: 美国对14国加征关税税率（横向柱状图）---
  var tariffEl = document.getElementById('chart-tariff');
  if (tariffEl) {
    var tariffChart = echarts.init(tariffEl, null, { renderer: 'svg' });
    // 按税率从高到低排列
    var countries = ['老挝', '缅甸', '柬埔寨', '泰国', '孟加拉国', '塞尔维亚', '印度尼西亚', '波黑', '南非', '日本', '韩国', '哈萨克斯坦', '马来西亚', '突尼斯'];
    var rates = [40, 40, 36, 36, 35, 35, 32, 30, 30, 25, 25, 25, 25, 25];
    var colors = rates.map(function(r) {
      if (r >= 38) return accent2;          // 40% 红
      if (r >= 33) return '#e8730f';        // 35-36% 橙
      if (r >= 28) return '#c9a227';        // 30-32% 金
      return accent;                        // 25% 蓝
    });
    tariffChart.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        appendToBody: true,
        formatter: function(p) { return p[0].name + '：' + p[0].value + '%'; }
      },
      grid: { left: 90, right: 48, top: 16, bottom: 28 },
      xAxis: {
        type: 'value',
        max: 45,
        axisLabel: { color: muted, fontSize: 12, formatter: '{value}%' },
        axisLine: { lineStyle: { color: rule } },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      yAxis: {
        type: 'category',
        data: countries,
        axisLabel: { color: ink, fontSize: 13 },
        axisLine: { lineStyle: { color: rule } },
        axisTick: { show: false }
      },
      series: [{
        type: 'bar',
        data: rates.map(function(v, i) { return { value: v, itemStyle: { color: colors[i], borderRadius: [0, 4, 4, 0] } }; }),
        barWidth: '58%',
        label: {
          show: true,
          position: 'right',
          formatter: '{c}%',
          color: ink,
          fontSize: 12,
          fontWeight: 600
        }
      }]
    });
    window.addEventListener('resize', function() { tariffChart.resize(); });
  }

  // --- Chart 2: 三星电子Q2营业利润同比对比 ---
  var samEl = document.getElementById('chart-samsung');
  if (samEl) {
    var samChart = echarts.init(samEl, null, { renderer: 'svg' });
    samChart.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        appendToBody: true,
        formatter: function(p) {
          return p[0].name + '<br/>营业利润：' + p[0].value + ' 万亿韩元';
        }
      },
      grid: { left: 72, right: 40, top: 48, bottom: 36 },
      title: {
        text: '同比增幅 +1810%',
        right: 12,
        top: 6,
        textStyle: { color: accent3, fontSize: 15, fontWeight: 700 }
      },
      xAxis: {
        type: 'category',
        data: ['2025年 Q2', '2026年 Q2'],
        axisLabel: { color: ink, fontSize: 13, fontWeight: 600 },
        axisLine: { lineStyle: { color: rule } },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        name: '万亿韩元',
        nameTextStyle: { color: muted, fontSize: 12 },
        axisLabel: { color: muted, fontSize: 12 },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      series: [{
        type: 'bar',
        data: [
          { value: 4.68, itemStyle: { color: muted, borderRadius: [6, 6, 0, 0] } },
          { value: 89.4, itemStyle: { color: accent, borderRadius: [6, 6, 0, 0] } }
        ],
        barWidth: '42%',
        label: {
          show: true,
          position: 'top',
          formatter: '{c}',
          color: ink,
          fontSize: 14,
          fontWeight: 700
        }
      }]
    });
    window.addEventListener('resize', function() { samChart.resize(); });
  }
})();
