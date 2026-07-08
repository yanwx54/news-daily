#!/usr/bin/env python3
"""
每日国际及国内热点新闻行业日报自动生成脚本
从多个 RSS 源抓取新闻，分类整理后生成 HTML 日报。
支持部署到服务器或 GitHub Actions，可推送到微信公众号草稿和 PushPlus。
"""

import os
import sys
import json
import hashlib
import re
import shutil
from datetime import datetime, timezone, timedelta
from html import escape
from urllib.parse import urlparse

import feedparser
import requests

# 导入微信公众号草稿推送模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wechat_draft

# ============================================================
# 配置
# ============================================================

BEIJING_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(BEIJING_TZ)
TODAY_STR = TODAY.strftime("%Y年%m月%d日")
TODAY_DATE_STR = TODAY.strftime("%Y-%m-%d")
TODAY_WEEKDAY = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][TODAY.weekday()]
REPORT_SLUG = TODAY.strftime("intl-news-daily-%Y%m%d")
ISSUE_DATE_KEY = TODAY.strftime("%Y%m%d")

WORKSPACE = os.path.dirname(os.path.abspath(__file__))
ECHARTS_SRC = os.path.join(WORKSPACE, "echarts", "echarts.min.js")
ISSUE_TRACKER = os.path.join(WORKSPACE, "issue_tracker.json")

# RSS 新闻源
# 使用 Google News RSS（聚合多源）+ BBC RSS 作为国际补充
RSS_SOURCES = {
    "domestic": [
        {
            "name": "Google News 国内",
            "url": "https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "lang": "zh",
        },
        {
            "name": "Google News 中国要闻",
            "url": "https://news.google.com/rss/search?q=中国+OR+国内+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "lang": "zh",
        },
    ],
    "international": [
        {
            "name": "Google News 国际",
            "url": "https://news.google.com/rss/search?q=国际+OR+全球+OR+world+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "lang": "zh",
        },
        {
            "name": "BBC World",
            "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
            "lang": "en",
        },
    ],
    "finance": [
        {
            "name": "Google News 财经",
            "url": "https://news.google.com/rss/search?q=财经+OR+股市+OR+经济+OR+market+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "lang": "zh",
        },
        {
            "name": "BBC Business",
            "url": "http://feeds.bbci.co.uk/news/business/rss.xml",
            "lang": "en",
        },
    ],
    "tech": [
        {
            "name": "Google News 科技AI",
            "url": "https://news.google.com/rss/search?q=AI+OR+科技+OR+人工智能+OR+technology+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "lang": "zh",
        },
        {
            "name": "BBC Technology",
            "url": "http://feeds.bbci.co.uk/news/technology/rss.xml",
            "lang": "en",
        },
    ],
    "aerospace": [
        {
            "name": "Google News 航天",
            "url": "https://news.google.com/rss/search?q=航天+OR+火箭+OR+太空+OR+space+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "lang": "zh",
        },
    ],
    "commodities": [
        {
            "name": "Google News 大宗商品",
            "url": "https://news.google.com/rss/search?q=原油+OR+黄金+OR+外汇+OR+oil+OR+gold+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "lang": "zh",
        },
    ],
    "climate": [
        {
            "name": "Google News 气候安全",
            "url": "https://news.google.com/rss/search?q=高温+OR+极端天气+OR+climate+OR+洪水+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "lang": "zh",
        },
    ],
}

# 板块中文名
SECTION_NAMES = {
    "domestic": "国内热点新闻",
    "international": "国际政治与地缘动态",
    "finance": "全球财经与市场",
    "tech": "科技与AI产业前沿",
    "aerospace": "航天与前沿科技",
    "commodities": "大宗商品与外汇",
    "climate": "气候、安全与社会",
}

SECTION_SUBTITLES = {
    "domestic": ["时政民生与政策法规", "产业经济与市场动态", "社会治理与安全整治"],
    "international": ["多边外交与地缘冲突"],
    "finance": ["市场行情与财经动态"],
    "tech": ["AI算力与基础设施", "芯片竞争与产品动态", "AI研究与监管"],
    "aerospace": ["航天发射与前沿突破"],
    "commodities": ["大宗商品与外汇动态"],
    "climate": ["极端天气与社会安全"],
}

# 关键词分类映射（用于子板块分类）
KEYWORDS = {
    "domestic_politics": ["政策", "法规", "民生", "保障", "规定", "法律", "法院", "判例", "网信办", "整治"],
    "domestic_economy": ["企业", "市场", "股市", "A股", "经济", "产业", "手机", "芯片", "交易", "停牌", "业绩"],
    "domestic_society": ["安全", "防汛", "救灾", "暴雨", "灾害", "火箭军", "导弹", "新能源", "机票", "附加费"],
    "intl_conflict": ["关税", "贸易", "冲突", "战争", "制裁", "外交", "北约", "红海", "中东", "核污染"],
    "finance_market": ["美股", "道指", "纳指", "标普", "欧股", "财报", "利润", "央行", "加息", "利率", "美联储"],
    "tech_ai": ["AI", "人工智能", "大模型", "算力", "数据中心", "Anthropic", "OpenAI", "英伟达", "NVIDIA", "微软"],
    "tech_chip": ["芯片", "半导体", "GPU", "字节", "苹果", "谷歌", "高通", "亚马逊", "SAP"],
    "tech_regulation": ["监管", "安全标准", "版权", "隐私", "社交", "禁令", "OpenAI"],
    "aerospace_space": ["火箭", "长征", "发射", "登月", "SpaceX", "卫星", "核聚变", "人造太阳", "ICML"],
    "commodities_fx": ["原油", "黄金", "比特币", "咖啡", "外汇", "美元", "欧元", "日元", "韩元", "通胀"],
    "climate_weather": ["高温", "洪水", "洪涝", "暴雨", "极端", "气候", "预警", "灾难", "台风", "干旱"],
}


# ============================================================
# 期号管理
# ============================================================

def get_issue_number():
    """读取或初始化期号"""
    if os.path.exists(ISSUE_TRACKER):
        try:
            with open(ISSUE_TRACKER, "r", encoding="utf-8") as f:
                data = json.load(f)
                last_issue = data.get("last_issue", 188)
                last_date = data.get("last_date", "")
                if last_date == ISSUE_DATE_KEY:
                    return last_issue  # 同一天不重复递增
                new_issue = last_issue + 1
                data["last_issue"] = new_issue
                data["last_date"] = ISSUE_DATE_KEY
                with open(ISSUE_TRACKER, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return new_issue
        except (json.JSONDecodeError, KeyError):
            pass
    # 初始化
    data = {"last_issue": 189, "last_date": ISSUE_DATE_KEY}
    with open(ISSUE_TRACKER, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return 189


# ============================================================
# RSS 抓取
# ============================================================

def fetch_rss(source):
    """抓取单个 RSS 源，返回新闻条目列表"""
    try:
        resp = requests.get(source["url"], timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (compatible; NewsDailyBot/1.0)"
        })
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        items = []
        for entry in feed.entries[:15]:  # 每源最多15条
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()
            link = entry.get("link", "")
            published = entry.get("published", entry.get("updated", ""))

            # 清理 HTML 标签
            summary = re.sub(r'<[^>]+>', '', summary)
            if len(summary) > 200:
                summary = summary[:197] + "..."

            if title:
                items.append({
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "source": source["name"],
                    "published": published,
                    "lang": source["lang"],
                })
        return items
    except Exception as e:
        print(f"  [WARN] 抓取 {source['name']} 失败: {e}", file=sys.stderr)
        return []


def fetch_all_news():
    """抓取所有板块的新闻"""
    all_news = {}
    for section, sources in RSS_SOURCES.items():
        print(f"抓取板块: {SECTION_NAMES[section]}")
        items = []
        for src in sources:
            print(f"  源: {src['name']}")
            items.extend(fetch_rss(src))
        # 去重（按标题）
        seen = set()
        unique = []
        for item in items:
            key = hashlib.md5(item["title"].encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                unique.append(item)
        all_news[section] = unique
        print(f"  → 共 {len(unique)} 条")
    return all_news


# ============================================================
# 新闻分类
# ============================================================

def classify_news(items, keyword_list):
    """根据关键词将新闻分类到子板块"""
    matched = []
    for item in items:
        text = (item["title"] + " " + item["summary"]).lower()
        for kw in keyword_list:
            if kw.lower() in text:
                matched.append(item)
                break
    return matched


def organize_news(all_news):
    """将新闻按子板块组织"""
    organized = {}
    for section, items in all_news.items():
        subtitles = SECTION_SUBTITLES.get(section, ["综合要闻"])
        if section == "domestic":
            organized[section] = [
                ("时政民生与政策法规", classify_news(items, KEYWORDS["domestic_politics"]) or items[:3]),
                ("产业经济与市场动态", classify_news(items, KEYWORDS["domestic_economy"]) or items[3:6]),
                ("社会治理与安全整治", classify_news(items, KEYWORDS["domestic_society"]) or items[6:9]),
            ]
        elif section == "tech":
            organized[section] = [
                ("AI算力与基础设施", classify_news(items, KEYWORDS["tech_ai"]) or items[:3]),
                ("芯片竞争与产品动态", classify_news(items, KEYWORDS["tech_chip"]) or items[3:6]),
                ("AI研究与监管政策", classify_news(items, KEYWORDS["tech_regulation"]) or items[6:9]),
            ]
        elif section == "international":
            organized[section] = [
                ("国际政治与贸易动态", items[:5]),
                ("多边外交与地缘冲突", classify_news(items, KEYWORDS["intl_conflict"]) or items[5:8]),
            ]
        elif section == "finance":
            organized[section] = [
                ("市场行情与财经动态", items[:8]),
            ]
        elif section == "aerospace":
            organized[section] = [
                ("航天发射与前沿突破", items[:6]),
            ]
        elif section == "commodities":
            organized[section] = [
                ("大宗商品与外汇动态", items[:6]),
            ]
        elif section == "climate":
            organized[section] = [
                ("极端天气与社会安全", items[:6]),
            ]
        else:
            organized[section] = [(subtitles[0], items[:6])]

        # 确保每个子板块有内容
        for i, (subtitle, sub_items) in enumerate(organized[section]):
            if not sub_items and items:
                organized[section][i] = (subtitle, items[:3])

    return organized


# ============================================================
# HTML 生成
# ============================================================

def build_headline_cards(all_news):
    """构建头条速览卡片（选取最重要的6-8条）"""
    cards = []
    colors = ["green", "alt", "", "green", "alt", "", "green", "alt"]
    tags = [
        ("国内 · 要闻", "green"),
        ("贸易 · 关税", "alt"),
        ("财经 · 市场", ""),
        ("科技 · AI", "green"),
        ("航天 · 前沿", ""),
        ("地缘 · 安全", "alt"),
        ("气候 · 极端", "green"),
        ("大宗 · 外汇", ""),
    ]

    # 从各板块各取1-2条
    selection = []
    for section in ["domestic", "international", "finance", "tech", "aerospace", "climate"]:
        items = all_news.get(section, [])
        if items:
            selection.append((section, items[0]))
        if len(items) > 1 and len(selection) < 8:
            selection.append((section, items[1]))

    for idx, (section, item) in enumerate(selection[:8]):
        tag_text, color = tags[idx] if idx < len(tags) else ("要闻", "")
        card_class = f"hl-card {color}".strip()
        cite_link = ""
        if item.get("link"):
            domain = urlparse(item["link"]).netloc or item.get("source", "")
            cite_link = f' <a href="{escape(item["link"])}" target="_blank" rel="noopener" style="font-size:11px;color:var(--accent)">[来源]</a>'

        cards.append(f'''    <div class="{card_class}">
      <div class="tag">{escape(tag_text)}</div>
      <h4>{escape(item["title"])}</h4>
      <p>{escape(item["summary"][:80]) if item["summary"] else ""}{cite_link}</p>
    </div>''')

    return "\n".join(cards)


def build_section_html(section_key, subsections, section_num):
    """构建单个板块的 HTML"""
    section_name = SECTION_NAMES[section_key]
    html_parts = []
    html_parts.append(f'<h2 class="sec"><span class="num">{section_num:02d}</span>{section_name}</h2>')

    for subtitle, items in subsections:
        if not items:
            continue
        html_parts.append(f'<h3 class="sub">{escape(subtitle)}</h3>')
        for item in items[:5]:  # 每子板块最多5条
            cite_link = ""
            if item.get("link"):
                cite_link = f' <a href="{escape(item["link"])}" target="_blank" rel="noopener" style="font-size:12px;color:var(--accent)">[原文]</a>'
            summary_html = f'<div class="nb">{escape(item["summary"]) if item["summary"] else escape(item["source"])}{cite_link}</div>' if item.get("summary") else ""
            html_parts.append(f'''<div class="news-item">
  <div class="nh">{escape(item["title"])}</div>
  {summary_html}
</div>''')

    return "\n".join(html_parts)


def build_sources_section(all_news):
    """构建信息来源列表"""
    sources = []
    seen = set()
    idx = 1
    for section, items in all_news.items():
        for item in items:
            link = item.get("link", "")
            if link and link not in seen:
                seen.add(link)
                source_name = item.get("source", urlparse(link).netloc or "未知")
                sources.append(f'''        <li id="cite-{idx}">
          <span class="src-title">{escape(source_name)}，{escape(item["title"][:60])}</span>
          <a class="src-url" href="{escape(link)}" target="_blank" rel="noopener">{escape(link)}</a>
        </li>''')
                idx += 1
            if idx > 30:
                break
        if idx > 30:
            break

    return f'''<div class="sources">
  <h2>信息来源</h2>
  <ol>
{chr(10).join(sources)}
  </ol>
</div>'''


def build_watchlist():
    """构建明日关注"""
    tomorrow = (TODAY + timedelta(days=1)).strftime("%Y年%m月%d日")
    return f'''<div class="watch-box">
  <h2 class="sec" style="color:#fff;border-bottom:2px solid rgba(255,255,255,.25);margin-top:0"><span class="num" style="background:#7db4ff;color:#0f1e4d">09</span>明日值得关注</h2>
  <div class="w-item"><strong>全球市场</strong>：关注美股及亚太股市开盘走势，关税政策对供应链影响持续发酵。</div>
  <div class="w-item"><strong>科技前沿</strong>：AI 大模型及芯片产业最新动态，关注重大产品发布或融资事件。</div>
  <div class="w-item"><strong>地缘局势</strong>：中东、红海及主要地区冲突演变，关注外交进展。</div>
  <div class="w-item"><strong>气候预警</strong>：北半球极端天气持续，关注灾害预警及应对措施。</div>
  <div class="w-item"><strong>国内政策</strong>：关注最新政策法规发布及经济数据公布。</div>
</div>'''


def generate_charts_js(report_dir):
    """生成 charts.js（如果有可用的数值数据）"""
    # 默认生成一个简单的板块新闻数量统计图
    chart_code = '''(function() {
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
'''
    return chart_code


def generate_html(all_news, organized, issue_num):
    """生成完整 HTML 日报"""

    headline_cards = build_headline_cards(all_news)

    # 构建各板块 HTML
    sections_html = []
    section_order = ["domestic", "international", "finance", "tech", "aerospace", "commodities", "climate"]
    for idx, section in enumerate(section_order):
        if section in organized:
            sections_html.append(build_section_html(section, organized[section], idx + 2))

    sources_html = build_sources_section(all_news)
    watchlist_html = build_watchlist()

    # 新闻数量统计（用于饼图）
    summary_data = []
    for section in section_order:
        count = len(all_news.get(section, []))
        if count > 0:
            summary_data.append(f'{{name: "{SECTION_NAMES[section]}", value: {count}}}')
    summary_json = "[" + ", ".join(summary_data) + "]"

    html = f'''<!-- Generated by News Daily Bot -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>国际及国内热点新闻行业日报 · {TODAY_STR}</title>
<style>
  :root{{
    --bg:#f4f5f8; --bg2:#ffffff; --ink:#1a2233; --muted:#5c6577;
    --rule:#e3e6ec; --accent:#1447e6; --accent2:#d93025; --accent3:#0f9d58;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  html{{scroll-behavior:smooth}}
  body{{
    background:var(--bg); color:var(--ink);
    font-family:"PingFang SC","Microsoft YaHei","Noto Sans SC","Hiragino Sans GB",sans-serif;
    font-size:16px; line-height:1.75; -webkit-font-smoothing:antialiased;
  }}
  .wrap{{max-width:920px;margin:0 auto;padding:0 24px 80px}}
  .masthead{{
    background:linear-gradient(135deg,#0f1e4d 0%,#1447e6 100%);
    color:#fff; padding:56px 24px 40px; border-radius:0 0 18px 18px; margin-bottom:36px;
  }}
  .masthead .kicker{{font-size:13px;letter-spacing:.18em;text-transform:uppercase;opacity:.78;font-weight:600}}
  .masthead h1{{font-size:38px;font-weight:800;line-height:1.25;margin:10px 0 8px;letter-spacing:.01em}}
  .masthead .sub{{font-size:15px;opacity:.85;max-width:620px}}
  .masthead .meta-row{{display:flex;flex-wrap:wrap;gap:10px 22px;margin-top:22px;font-size:13px;opacity:.9}}
  .masthead .meta-row span{{display:inline-flex;align-items:center;gap:6px}}
  .masthead .dot{{width:7px;height:7px;border-radius:50%;background:#7db4ff;display:inline-block}}
  h2.sec{{
    font-size:22px;font-weight:800;margin:44px 0 18px;padding-bottom:10px;
    border-bottom:2px solid var(--ink);display:flex;align-items:center;gap:10px;
  }}
  h2.sec .num{{
    font-size:13px;font-weight:700;color:#fff;background:var(--accent);
    width:26px;height:26px;display:inline-flex;align-items:center;justify-content:center;
    border-radius:6px;flex-shrink:0;
  }}
  h3.sub{{
    font-size:17px;font-weight:700;color:var(--ink);margin:26px 0 10px;
    padding-left:12px;border-left:4px solid var(--accent);
  }}
  p{{margin:0 0 14px}}
  strong{{font-weight:700;color:var(--ink)}}
  a{{color:var(--accent);text-decoration:none}}
  a:hover{{text-decoration:underline}}
  .hl-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-bottom:8px}}
  .hl-card{{background:var(--bg2);border:1px solid var(--rule);border-radius:12px;padding:18px 20px;border-left:4px solid var(--accent)}}
  .hl-card.alt{{border-left-color:var(--accent2)}}
  .hl-card.green{{border-left-color:var(--accent3)}}
  .hl-card .tag{{font-size:11px;font-weight:700;letter-spacing:.06em;color:var(--accent);text-transform:uppercase;margin-bottom:6px}}
  .hl-card.alt .tag{{color:var(--accent2)}}
  .hl-card.green .tag{{color:var(--accent3)}}
  .hl-card h4{{font-size:15.5px;font-weight:700;line-height:1.45;margin-bottom:6px}}
  .hl-card p{{font-size:13.5px;color:var(--muted);margin:0;line-height:1.55}}
  .news-item{{margin-bottom:16px;padding-left:18px;position:relative}}
  .news-item::before{{content:"";position:absolute;left:0;top:11px;width:7px;height:7px;border-radius:50%;background:var(--accent)}}
  .news-item .nh{{font-weight:700;font-size:15px;margin-bottom:3px}}
  .news-item .nb{{font-size:14px;color:var(--muted);line-height:1.65}}
  .chart-figure{{margin:22px 0;background:var(--bg2);border:1px solid var(--rule);border-radius:12px;padding:18px 18px 8px}}
  .chart-figure figcaption{{font-size:15px;font-weight:700;color:var(--ink);margin-bottom:10px}}
  .chart-figure .chart-sub{{font-size:12.5px;color:var(--muted);margin-bottom:12px}}
  .watch-box{{background:linear-gradient(135deg,#0f1e4d 0%,#1a3a8f 100%);color:#fff;border-radius:14px;padding:26px 28px;margin:30px 0}}
  .watch-box h2{{color:#fff;border-bottom-color:rgba(255,255,255,.25);font-size:20px}}
  .watch-box .w-item{{padding-left:18px;position:relative;margin-bottom:12px;color:#dfe6f5;font-size:14.5px}}
  .watch-box .w-item::before{{content:"";position:absolute;left:0;top:10px;width:7px;height:7px;border-radius:50%;background:#7db4ff}}
  .watch-box .w-item strong{{color:#fff}}
  footer{{margin-top:50px;padding-top:24px;border-top:1px solid var(--rule)}}
  footer .sources h2{{font-size:18px;font-weight:700;margin-bottom:14px}}
  footer .sources ol{{padding-left:1.2rem;font-size:13px;color:var(--muted)}}
  footer .sources li{{margin-bottom:.5rem;overflow-wrap:break-word;word-break:break-all}}
  footer .sources .src-title{{color:var(--ink);word-break:normal}}
  footer .sources .src-url{{display:block;margin-top:.15rem;font-size:12.5px;color:var(--accent);word-break:break-all}}
  footer .disclaim{{margin-top:24px;font-size:12px;color:var(--muted);line-height:1.6}}
  @media(max-width:680px){{
    .masthead h1{{font-size:28px}}
    .hl-grid{{grid-template-columns:1fr}}
    h2.sec{{font-size:19px}}
    body{{font-size:15px}}
  }}
</style>
</head>
<body>

<header class="masthead">
  <div class="kicker">International &amp; Domestic Daily Briefing</div>
  <h1>国际及国内热点新闻行业日报</h1>
  <p class="sub">覆盖国内时政民生、全球地缘政治、财经市场、科技 AI、航天前沿、大宗商品与气候安全的一站式每日要闻速递。</p>
  <div class="meta-row">
    <span><span class="dot"></span>{TODAY_STR}（{TODAY_WEEKDAY}）</span>
    <span><span class="dot"></span>第 {issue_num} 期</span>
    <span><span class="dot"></span>北京时间 08:00 自动生成</span>
  </div>
</header>

<div class="wrap">

<h2 class="sec"><span class="num">01</span>今日头条速览</h2>
<div class="hl-grid">
{headline_cards}
</div>

{chr(10).join(sections_html)}

<figure class="chart-figure">
  <figcaption>各板块新闻数量分布</figcaption>
  <div class="chart-sub">数据来源：今日 RSS 抓取统计，{TODAY_STR}</div>
  <div id="chart-summary" style="width:100%;min-height:360px"></div>
</figure>

{watchlist_html}

</div>

<footer>
  <div class="wrap">
    {sources_html}
    <p class="disclaim">免责声明：本日报由程序自动从公开 RSS 源抓取生成，仅供信息参考，不构成任何投资建议。市场有风险，决策需谨慎。数据截至北京时间{TODAY_STR} 08:00。</p>
  </div>
</footer>

<script>window.NEWS_SUMMARY = {summary_json};</script>
<script src="./_shared/js/echarts.min.js"></script>
<script src="assets/charts.js"></script>
</body>
</html>'''

    return html


# ============================================================
# PushPlus 微信推送
# ============================================================

def push_to_wechat(html_content, all_news, issue_num):
    """通过 PushPlus 推送日报摘要到微信"""
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not token:
        print("[SKIP] 未配置 PUSHPLUS_TOKEN 环境变量，跳过微信推送")
        return False

    # 构建微信推送内容（精简版 HTML，适合手机阅读）
    title = f"国际及国内热点新闻行业日报 · {TODAY_STR}（第{issue_num}期）"

    # 头条速览（取前6条）
    headlines = []
    for section in ["domestic", "international", "finance", "tech", "aerospace", "climate"]:
        items = all_news.get(section, [])
        if items:
            for item in items[:1]:
                headlines.append(f"<li><strong>{escape(item['title'])}</strong></li>")
    headlines_html = "\n".join(headlines[:6])

    # 各板块摘要（每板块取前3条标题）
    sections_html = []
    section_order = ["domestic", "international", "finance", "tech", "aerospace", "commodities", "climate"]
    for section in section_order:
        items = all_news.get(section, [])
        if not items:
            continue
        section_name = SECTION_NAMES[section]
        item_list = []
        for item in items[:3]:
            item_list.append(f"<li>{escape(item['title'])}</li>")
        sections_html.append(f"<h3>{section_name}</h3><ul>{''.join(item_list)}</ul>")
    sections_content = "\n".join(sections_html)

    # GitHub 仓库链接
    repo_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com") + "/" + \
               os.environ.get("GITHUB_REPOSITORY", "yanwx54/news-daily")
    report_url = f"{repo_url}/blob/main/{REPORT_SLUG}/{REPORT_SLUG}.html"

    content = f"""<div style="font-family:sans-serif;max-width:680px;margin:0 auto;">
<div style="background:linear-gradient(135deg,#0f1e4d 0%,#1447e6 100%);color:#fff;padding:24px 20px;border-radius:12px;margin-bottom:20px;">
<h1 style="font-size:22px;margin:0 0 8px;">国际及国内热点新闻行业日报</h1>
<p style="margin:0;opacity:.85;font-size:14px;">{TODAY_STR}（{TODAY_WEEKDAY}）· 第 {issue_num} 期 · 北京时间 08:00 自动生成</p>
</div>
<h2 style="font-size:17px;border-bottom:2px solid #1447e6;padding-bottom:8px;">今日头条速览</h2>
<ul style="padding-left:18px;line-height:1.8;">{headlines_html}</ul>
{sections_content}
<div style="background:#f0f3f9;padding:16px 20px;border-radius:10px;margin:20px 0;">
<p style="margin:0;font-size:14px;">📄 完整日报（含图表）：<a href="{report_url}">点击查看</a></p>
<p style="margin:6px 0 0;font-size:13px;color:#5c6577;">仓库地址：<a href="{repo_url}">{repo_url}</a></p>
</div>
<p style="font-size:12px;color:#5c6577;margin-top:16px;">免责声明：本日报由程序自动从公开 RSS 源抓取生成，仅供信息参考，不构成投资建议。</p>
</div>"""

    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
    }

    try:
        print("正在推送到微信（PushPlus）...")
        resp = requests.post(
            "https://www.pushplus.plus/send",
            json=payload,
            timeout=30,
            headers={"Content-Type": "application/json"},
        )
        result = resp.json()
        if result.get("code") == 200:
            print(f"✓ 微信推送成功！{result.get('msg', '')}")
            return True
        else:
            print(f"  [WARN] PushPlus 返回: code={result.get('code')}, msg={result.get('msg')}")
            return False
    except Exception as e:
        print(f"  [ERROR] 微信推送失败: {e}", file=sys.stderr)
        return False


# ============================================================
# 主流程
# ============================================================

def main():
    print(f"=== 每日新闻日报生成 ===")
    print(f"日期: {TODAY_STR}（{TODAY_WEEKDAY}）")
    print()

    # 1. 获取期号
    issue_num = get_issue_number()
    print(f"期号: 第 {issue_num} 期")
    print()

    # 2. 抓取新闻
    all_news = fetch_all_news()
    total = sum(len(v) for v in all_news.values())
    print(f"\n总抓取: {total} 条新闻\n")

    # 3. 如果完全没有抓到新闻，使用占位
    if total == 0:
        print("[ERROR] 未抓取到任何新闻，跳过生成", file=sys.stderr)
        # 仍然生成一个基本报告
        for section in SECTION_NAMES:
            all_news[section] = [{
                "title": f"今日{SECTION_NAMES[section]}暂无可用新闻源",
                "summary": "可能由于网络限制或 RSS 源不可用，请稍后重试。",
                "link": "",
                "source": "系统",
                "published": "",
                "lang": "zh",
            }]

    # 4. 分类组织
    organized = organize_news(all_news)

    # 5. 生成 HTML
    html = generate_html(all_news, organized, issue_num)

    # 6. 创建目录结构
    report_dir = os.path.join(WORKSPACE, REPORT_SLUG)
    assets_dir = os.path.join(report_dir, "assets")
    shared_js_dir = os.path.join(report_dir, "_shared", "js")
    os.makedirs(assets_dir, exist_ok=True)
    os.makedirs(shared_js_dir, exist_ok=True)

    # 7. 写入文件
    html_path = os.path.join(report_dir, f"{REPORT_SLUG}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ HTML 报告已生成: {html_path}")

    # 写入 charts.js
    charts_path = os.path.join(assets_dir, "charts.js")
    with open(charts_path, "w", encoding="utf-8") as f:
        f.write(generate_charts_js(report_dir))
    print(f"✓ 图表脚本已生成: {charts_path}")

    # 复制 echarts.min.js
    echarts_dest = os.path.join(shared_js_dir, "echarts.min.js")
    if os.path.exists(ECHARTS_SRC):
        shutil.copy2(ECHARTS_SRC, echarts_dest)
        print(f"✓ ECharts 库已复制: {echarts_dest}")
    else:
        print(f"  [WARN] ECharts 源文件不存在: {ECHARTS_SRC}", file=sys.stderr)

    # 8. 更新首页索引
    index_path = os.path.join(WORKSPACE, "index.html")
    build_index_page(index_path, issue_num)
    print(f"✓ 首页索引已更新: {index_path}")

    print(f"\n=== 完成！===")
    print(f"报告目录: {report_dir}")
    print(f"报告文件: {html_path}")

    # 9. 推送到微信公众号草稿箱
    wechat_draft.push_to_draft(all_news, issue_num, TODAY_STR, TODAY_WEEKDAY)

    # 10. 推送到微信（PushPlus，作为备选通知渠道）
    push_to_wechat(html, all_news, issue_num)


def build_index_page(index_path, issue_num):
    """生成/更新首页索引，列出所有日报"""
    # 扫描所有日报目录
    reports = []
    for entry in sorted(os.listdir(WORKSPACE), reverse=True):
        if entry.startswith("intl-news-daily-") and os.path.isdir(os.path.join(WORKSPACE, entry)):
            html_file = os.path.join(WORKSPACE, entry, f"{entry}.html")
            if os.path.exists(html_file):
                # 从目录名提取日期
                date_match = re.search(r'(\d{4})(\d{2})(\d{2})', entry)
                if date_match:
                    y, m, d = date_match.groups()
                    date_str = f"{y}年{m}月{d}日"
                    reports.append((date_str, entry, f"{entry}/{entry}.html"))

    items_html = "\n".join([
        f'<li><a href="{path}"><span class="date">{date}</span><span class="title">国际及国内热点新闻行业日报</span></a></li>'
        for date, slug, path in reports
    ])

    html = f'''<!-- Generated by News Daily Bot -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日新闻日报索引</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:"PingFang SC","Microsoft YaHei",sans-serif;background:#f4f5f8;color:#1a2233;padding:40px 20px}}
  .container{{max-width:720px;margin:0 auto}}
  h1{{font-size:28px;font-weight:800;margin-bottom:8px}}
  .subtitle{{color:#5c6577;font-size:15px;margin-bottom:30px}}
  ul{{list-style:none}}
  li{{margin-bottom:12px}}
  a{{display:flex;align-items:center;gap:16px;padding:16px 20px;background:#fff;border:1px solid #e3e6ec;border-radius:10px;color:#1a2233;text-decoration:none;transition:box-shadow .2s}}
  a:hover{{box-shadow:0 2px 8px rgba(0,0,0,.08);border-color:#1447e6}}
  .date{{font-size:14px;font-weight:700;color:#1447e6;min-width:120px;white-space:nowrap}}
  .title{{font-size:15px}}
  .footer{{margin-top:40px;font-size:13px;color:#5c6577}}
</style>
</head>
<body>
<div class="container">
  <h1>每日国际及国内热点新闻行业日报</h1>
  <p class="subtitle">GitHub Actions 自动生成 · 每日 08:00 北京时间推送 · 第 {issue_num} 期</p>
  <ul>
{items_html}
  </ul>
  <p class="footer">本仓库由 GitHub Actions 自动维护，无需本地电脑开机。</p>
</div>
</body>
</html>'''

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
