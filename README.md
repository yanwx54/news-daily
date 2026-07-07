# 每日国际及国内热点新闻行业日报

自动抓取全球新闻，生成结构化 HTML 日报，通过 GitHub Actions 每日云端运行。

## 特性

- **全自动运行**：GitHub Actions 每天北京时间 08:00 自动执行，无需本地电脑开机
- **多源聚合**：从 Google News RSS、BBC RSS 等多个源抓取新闻
- **七大板块**：国内热点、国际政治、全球财经、科技AI、航天前沿、大宗商品外汇、气候安全
- **可视化图表**：使用 ECharts 生成新闻分布饼图
- **自包含 HTML**：每个日报文件可独立打开，无需外部依赖
- **自动期号管理**：期号自动递增，不会重复
- **首页索引**：自动生成 `index.html` 列出所有历史日报

## 目录结构

```
news-daily/
├── .github/
│   └── workflows/
│       └── daily-news.yml        # GitHub Actions 工作流
├── generate_report.py            # 日报生成主脚本
├── requirements.txt              # Python 依赖
├── issue_tracker.json            # 期号追踪文件
├── echarts/
│   └── echarts.min.js            # ECharts 库（供每日报告复制）
├── index.html                    # 首页索引（自动生成）
├── .gitignore
└── intl-news-daily-YYYYMMDD/     # 每日报告目录
    ├── intl-news-daily-YYYYMMDD.html
    ├── assets/
    │   └── charts.js
    └── _shared/
        └── js/
            └── echarts.min.js
```

## 本地运行

```bash
pip install -r requirements.txt
python generate_report.py
```

## GitHub Actions 自动运行

工作流配置在 `.github/workflows/daily-news.yml`：

- **定时触发**：每天 UTC 00:00（北京时间 08:00）
- **手动触发**：在 GitHub 仓库 Actions 页面点击 "Run workflow"
- **自动提交**：生成的日报自动 commit 并 push 到 main 分支

## 新闻来源

| 板块 | RSS 源 |
|------|--------|
| 国内热点 | Google News 中文版、中国要闻搜索 |
| 国际政治 | Google News 国际、BBC World |
| 全球财经 | Google News 财经、BBC Business |
| 科技AI | Google News 科技、BBC Technology |
| 航天前沿 | Google News 航天搜索 |
| 大宗商品 | Google News 原油/黄金/外汇搜索 |
| 气候安全 | Google News 高温/极端天气搜索 |

## 技术栈

- Python 3.11 + feedparser + requests
- ECharts 5.x（数据可视化）
- GitHub Actions（CI/CD 自动化）
- 纯 HTML/CSS（无前端框架依赖）

## License

MIT
