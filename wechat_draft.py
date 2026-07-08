#!/usr/bin/env python3
"""
微信公众号草稿推送模块
通过微信公众平台 API 将日报推送到公众号草稿箱。
需要环境变量：
  WECHAT_APPID     - 公众号 AppID
  WECHAT_APP_SECRET - 公众号 AppSecret
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from html import escape

BEIJING_TZ = timezone(timedelta(hours=8))

# token 缓存文件
TOKEN_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wechat_token.json")
# 永久封面图 media_id 缓存（避免每天重复上传，永久素材有数量限制）
THUMB_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wechat_thumb.json")


def get_access_token():
    """获取微信公众号 access_token，带缓存（有效期2小时，提前10分钟刷新）"""
    appid = os.environ.get("WECHAT_APPID", "")
    secret = os.environ.get("WECHAT_APP_SECRET", "")

    if not appid or not secret:
        print("[SKIP] 未配置 WECHAT_APPID 或 WECHAT_APP_SECRET，跳过公众号推送")
        return None

    # 检查缓存
    if os.path.exists(TOKEN_CACHE):
        try:
            with open(TOKEN_CACHE, "r", encoding="utf-8") as f:
                cache = json.load(f)
                if cache.get("expires_at", 0) > time.time() + 600:
                    print(f"  使用缓存的 access_token（剩余 {int(cache['expires_at'] - time.time())} 秒）")
                    return cache["access_token"]
        except (json.JSONDecodeError, KeyError):
            pass

    # 请求新 token
    url = "https://api.weixin.qq.com/cgi-bin/token"
    params = {
        "grant_type": "client_credential",
        "appid": appid,
        "secret": secret,
    }
    try:
        print("  正在获取 access_token...")
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()

        if "access_token" not in data:
            errcode = data.get("errcode", "?")
            errmsg = data.get("errmsg", "unknown")
            print(f"  [ERROR] 获取 access_token 失败: errcode={errcode}, errmsg={errmsg}")
            if errcode == 40164:
                print("  [HINT] IP 不在白名单中，请在微信公众平台 -> 设置 -> 安全中心 -> IP白名单 中添加服务器IP")
            return None

        token = data["access_token"]
        expires_in = data.get("expires_in", 7200)

        # 缓存
        cache = {
            "access_token": token,
            "expires_at": time.time() + expires_in,
        }
        with open(TOKEN_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f)

        print(f"  access_token 获取成功（有效期 {expires_in} 秒）")
        return token

    except Exception as e:
        print(f"  [ERROR] 获取 access_token 异常: {e}", file=sys.stderr)
        return None


def upload_thumb_image(access_token, image_path=None):
    """上传封面图片到微信公众号，返回 media_id"""
    # 如果没有指定图片，生成一个简单的纯色封面
    if not image_path or not os.path.exists(image_path):
        # 使用内嵌的 1x1 蓝色 PNG 作为最小封面（微信要求至少 200x200）
        # 实际使用中应该提供一个真正的封面图片
        print("  [WARN] 未提供封面图片，跳过上传")
        return None

    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    try:
        with open(image_path, "rb") as f:
            files = {"media": f}
            resp = requests.post(url, files=files, timeout=60)
            data = resp.json()

            if "media_id" in data:
                print(f"  封面图片上传成功: media_id={data['media_id']}")
                return data["media_id"]
            else:
                print(f"  [ERROR] 封面上传失败: {data}")
                return None
    except Exception as e:
        print(f"  [ERROR] 封面上传异常: {e}", file=sys.stderr)
        return None


def get_permanent_thumb(access_token):
    """获取或创建永久封面图，使用永久素材接口上传并缓存 media_id"""
    import struct
    import zlib

    # 1. 检查缓存文件
    if os.path.exists(THUMB_CACHE):
        try:
            with open(THUMB_CACHE, "r", encoding="utf-8") as f:
                cache = json.load(f)
                cached_media_id = cache.get("thumb_media_id", "")
                if cached_media_id:
                    print(f"  使用缓存的永久封面图: media_id={cached_media_id}")
                    return cached_media_id
        except (json.JSONDecodeError, KeyError):
            pass

    # 2. 生成 200x200 蓝色 PNG
    width, height = 200, 200
    raw = b""
    for y in range(height):
        raw += b"\x00"
        for x in range(width):
            raw += b"\x14\x47\xe6\xff"

    def png_chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    png = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png += png_chunk(b"IHDR", ihdr)
    compressed = zlib.compress(raw)
    png += png_chunk(b"IDAT", compressed)
    png += png_chunk(b"IEND", b"")

    # 3. 上传为永久素材（draft/add 要求永久 media_id）
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    try:
        resp = requests.post(url, files={"media": ("thumb.png", png, "image/png")}, timeout=60)
        data = resp.json()
        if "media_id" in data:
            media_id = data["media_id"]
            print(f"  永久封面图上传成功: media_id={media_id}")
            # 缓存
            with open(THUMB_CACHE, "w", encoding="utf-8") as f:
                json.dump({"thumb_media_id": media_id}, f)
            return media_id
        else:
            print(f"  [ERROR] 永久封面图上传失败: {data}")
            return None
    except Exception as e:
        print(f"  [ERROR] 封面图上传异常: {e}", file=sys.stderr)
        return None


def build_article_content(all_news, issue_num, today_str, today_weekday):
    """构建微信公众号文章 HTML 内容 - 完整版日报，现代排版，全内联样式兼容微信"""

    # 板块配置：名称、主色
    section_config = [
        ("domestic", "国内热点新闻", "#1447e6"),
        ("international", "国际政治与地缘动态", "#d93025"),
        ("finance", "全球财经与市场", "#0f9d58"),
        ("tech", "科技与AI产业前沿", "#7c3aed"),
        ("aerospace", "航天与前沿科技", "#0891b2"),
        ("commodities", "大宗商品与外汇", "#c9a227"),
        ("climate", "气候、安全与社会", "#ea580c"),
    ]

    total_news = sum(len(all_news.get(s, [])) for s, _, _ in section_config)
    max_count = max((len(all_news.get(s, [])) for s, _, _ in section_config), default=1)

    # === 1. 统计进度条 ===
    stat_rows = []
    for section_key, section_name, color in section_config:
        count = len(all_news.get(section_key, []))
        if count == 0:
            continue
        bar_pct = int(count / max_count * 100)
        stat_rows.append(
            f'<section style="margin-bottom:7px;font-size:0;">'
            f'<span style="display:inline-block;width:72px;font-size:12px;color:#1a2233;vertical-align:middle;">{escape(section_name[:4])}</span>'
            f'<span style="display:inline-block;width:55%;height:14px;background:#eef0f5;border-radius:7px;vertical-align:middle;overflow:hidden;">'
            f'<span style="display:block;height:100%;width:{bar_pct}%;background:{color};border-radius:7px;"></span>'
            f'</span>'
            f'<span style="display:inline-block;font-size:12px;color:#5c6577;margin-left:8px;vertical-align:middle;">{count}条</span>'
            f'</section>'
        )
    stats_html = "\n".join(stat_rows)

    # === 2. 头条速览（各板块第1条）===
    headline_items = []
    for section_key, section_name, color in section_config:
        items = all_news.get(section_key, [])
        if not items:
            continue
        item = items[0]
        link_html = f' <a href="{escape(item["link"])}" style="font-size:12px;color:{color};text-decoration:none;">原文</a>' if item.get("link") else ""
        headline_items.append(
            f'<section style="padding:10px 14px;border-left:3px solid {color};margin-bottom:8px;background:#f8f9fc;border-radius:0 6px 6px 0;">'
            f'<span style="font-size:11px;font-weight:700;color:{color};letter-spacing:1px;">{escape(section_name[:4])}</span>'
            f'<p style="font-size:14.5px;font-weight:700;color:#1a2233;margin:3px 0 0;line-height:1.5;">{escape(item["title"])}{link_html}</p>'
            f'</section>'
        )
    headlines_html = "\n".join(headline_items)

    # === 3. 各板块完整新闻 ===
    sections_html = []
    for idx, (section_key, section_name, color) in enumerate(section_config):
        items = all_news.get(section_key, [])
        if not items:
            continue
        section_num = idx + 2  # 02 开始

        # 板块标题
        section_header = (
            f'<section style="margin-bottom:16px;margin-top:28px;">'
            f'<section style="border-bottom:2px solid {color};padding-bottom:8px;margin-bottom:14px;">'
            f'<span style="display:inline-block;background:{color};color:#fff;font-size:12px;font-weight:700;'
            f'padding:2px 8px;border-radius:4px;margin-right:8px;">{section_num:02d}</span>'
            f'<span style="font-size:17px;font-weight:800;color:#1a2233;">{escape(section_name)}</span>'
            f'<span style="float:right;font-size:12px;color:#9aa3b2;padding-top:4px;">{len(items)}条</span>'
            f'</section>'
        )

        # 新闻条目（全部）
        news_items = []
        for item in items:
            link_html = f' <a href="{escape(item["link"])}" style="font-size:12px;color:{color};text-decoration:none;">[原文]</a>' if item.get("link") else ""
            summary = escape(item["summary"][:120]) if item.get("summary") else ""
            summary_html = f'<p style="font-size:13px;color:#5c6577;margin:2px 0 0;line-height:1.6;">{summary}</p>' if summary else ""
            news_items.append(
                f'<section style="padding-left:14px;border-left:3px solid #e3e6ec;margin-bottom:12px;">'
                f'<p style="font-size:14.5px;font-weight:700;color:#1a2233;margin:0;line-height:1.5;">{escape(item["title"])}{link_html}</p>'
                f'{summary_html}'
                f'</section>'
            )

        sections_html.append(section_header + "\n".join(news_items) + "</section>")

    full_sections = "\n".join(sections_html)

    # === 组装完整文章 ===
    html = f"""<section style="max-width:677px;margin:0 auto;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">

<section style="background:linear-gradient(135deg,#0f1e4d 0%,#1447e6 100%);color:#fff;padding:28px 22px;border-radius:0 0 14px 14px;margin-bottom:24px;">
<p style="font-size:11px;letter-spacing:2.5px;opacity:0.6;margin:0 0 10px;font-weight:600;">DAILY BRIEFING</p>
<p style="font-size:22px;font-weight:800;margin:0 0 6px;line-height:1.3;">国际及国内热点新闻行业日报</p>
<p style="margin:0;opacity:0.82;font-size:14px;">{today_str}（{today_weekday}）· 第 {issue_num} 期 · 共 {total_news} 条</p>
</section>

<section style="margin-bottom:28px;">
<p style="font-size:13px;font-weight:700;color:#1a2233;margin:0 0 12px;letter-spacing:0.5px;">今日各板块新闻数量</p>
{stats_html}
</section>

<section style="margin-bottom:28px;">
<p style="font-size:13px;font-weight:700;color:#1a2233;margin:0 0 12px;letter-spacing:0.5px;">今日头条速览</p>
{headlines_html}
</section>

{full_sections}

<section style="background:linear-gradient(135deg,#0f1e4d 0%,#1a3a8f 100%);color:#fff;border-radius:12px;padding:22px 20px;margin:28px 0 20px;">
<p style="font-size:15px;font-weight:800;margin:0 0 12px;color:#fff;">明日值得关注</p>
<p style="font-size:13px;color:#dfe6f5;margin:0 0 8px;line-height:1.7;"><strong style="color:#7db4ff;">全球市场</strong>　关注美股及亚太股市开盘走势，关税政策对供应链影响持续发酵</p>
<p style="font-size:13px;color:#dfe6f5;margin:0 0 8px;line-height:1.7;"><strong style="color:#7db4ff;">科技前沿</strong>　AI 大模型及芯片产业最新动态，关注重大产品发布或融资事件</p>
<p style="font-size:13px;color:#dfe6f5;margin:0 0 8px;line-height:1.7;"><strong style="color:#7db4ff;">地缘局势</strong>　中东、红海及主要地区冲突演变，关注外交进展</p>
<p style="font-size:13px;color:#dfe6f5;margin:0 0 8px;line-height:1.7;"><strong style="color:#7db4ff;">气候预警</strong>　北半球极端天气持续，关注灾害预警及应对措施</p>
<p style="font-size:13px;color:#dfe6f5;margin:0;line-height:1.7;"><strong style="color:#7db4ff;">国内政策</strong>　关注最新政策法规发布及经济数据公布</p>
</section>

<p style="font-size:12px;color:#9aa3b2;margin-top:20px;border-top:1px solid #e3e6ec;padding-top:12px;line-height:1.6;">免责声明：本日报由程序自动从公开 RSS 源抓取生成，仅供信息参考，不构成任何投资建议。数据截至北京时间{today_str} 08:00。</p>

</section>"""

    return html


def push_to_draft(all_news, issue_num, today_str, today_weekday):
    """推送日报到微信公众号草稿箱"""
    print("正在推送到微信公众号草稿箱...")

    # 1. 获取 access_token
    access_token = get_access_token()
    if not access_token:
        return False

    # 2. 上传封面图
    thumb_media_id = get_permanent_thumb(access_token)
    if not thumb_media_id:
        print("  [WARN] 封面图上传失败，草稿将无封面图")

    # 3. 构建文章内容
    content = build_article_content(all_news, issue_num, today_str, today_weekday)
    # 微信草稿标题限制 64 字节，使用精简标题
    title = f"新闻日报·第{issue_num}期"
    # 安全截断：确保 UTF-8 字节数不超过 60
    title_bytes = len(title.encode("utf-8"))
    if title_bytes > 60:
        title = title[:15]
    print(f"  草稿标题: {title}（{len(title.encode('utf-8'))} 字节）")

    # 摘要（取前两条新闻标题）
    digest_items = []
    for section in ["domestic", "international"]:
        items = all_news.get(section, [])
        if items:
            digest_items.append(items[0]["title"][:30])
    digest = "；".join(digest_items)[:120] if digest_items else "每日国际及国内热点新闻速递"

    # 4. 创建草稿
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}"

    article = {
        "title": title,
        "author": "新闻日报Bot",
        "digest": digest,
        "content": content,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }

    if thumb_media_id:
        article["thumb_media_id"] = thumb_media_id

    payload = {"articles": [article]}

    # 调试输出：打印各字段字节数
    print(f"  [DEBUG] 草稿字段大小:")
    print(f"    title:  {len(title.encode('utf-8'))} 字节 | {title}")
    print(f"    author: {len(article['author'].encode('utf-8'))} 字节 | {article['author']}")
    print(f"    digest: {len(digest.encode('utf-8'))} 字节 | {digest[:50]}")
    print(f"    content: {len(content.encode('utf-8'))} 字节")

    try:
        # 使用 ensure_ascii=False 发送原生 UTF-8，避免中文被转义为 \uXXXX 导致长度膨胀
        json_str = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        resp = requests.post(
            url,
            data=json_str,
            timeout=60,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        data = resp.json()

        if data.get("errcode", 0) == 0 and "media_id" in data:
            media_id = data["media_id"]
            print(f"✓ 公众号草稿创建成功！media_id={media_id}")
            print(f"  标题: {title}")
            print(f"  请到微信公众平台 -> 草稿箱 查看和发布")
            return True
        else:
            errcode = data.get("errcode", "?")
            errmsg = data.get("errmsg", "unknown")
            print(f"  [ERROR] 草稿创建失败: errcode={errcode}, errmsg={errmsg}")
            if errcode == 40007:
                print("  [HINT] thumb_media_id 无效，可能需要上传永久素材")
            elif errcode == 45009:
                print("  [HINT] 接口调用频率超限")
            return False

    except Exception as e:
        print(f"  [ERROR] 草稿创建异常: {e}", file=sys.stderr)
        return False
