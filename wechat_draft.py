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
    """构建微信公众号文章 HTML 内容（适配微信渲染）"""
    today = datetime.now(BEIJING_TZ)
    today_date = today.strftime("%Y-%m-%d")

    # 头条速览
    headlines = []
    for section in ["domestic", "international", "finance", "tech", "aerospace", "climate"]:
        items = all_news.get(section, [])
        if items:
            for item in items[:1]:
                link_html = f' <a href="{escape(item["link"])}">[原文]</a>' if item.get("link") else ""
                headlines.append(f'<li><strong>{escape(item["title"])}</strong>{link_html}</li>')
    headlines_html = "\n".join(headlines[:6])

    # 各板块
    section_names = {
        "domestic": "国内热点新闻",
        "international": "国际政治与地缘动态",
        "finance": "全球财经与市场",
        "tech": "科技与AI产业前沿",
        "aerospace": "航天与前沿科技",
        "commodities": "大宗商品与外汇",
        "climate": "气候、安全与社会",
    }

    sections_html = []
    section_order = ["domestic", "international", "finance", "tech", "aerospace", "commodities", "climate"]
    for section in section_order:
        items = all_news.get(section, [])
        if not items:
            continue
        section_name = section_names.get(section, section)
        item_list = []
        for item in items[:5]:
            link_html = f' <a href="{escape(item["link"])}">[原文]</a>' if item.get("link") else ""
            summary = escape(item["summary"][:100]) if item.get("summary") else ""
            item_list.append(f'<li>{escape(item["title"])}{link_html}<br/><span style="color:#888;font-size:13px;">{summary}</span></li>')
        sections_html.append(f'<h2 style="color:#1447e6;border-bottom:2px solid #1447e6;padding-bottom:6px;">{section_name}</h2><ul style="padding-left:16px;line-height:1.8;">{"".join(item_list)}</ul>')

    sections_content = "\n".join(sections_html)

    html = f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:677px;margin:0 auto;padding:15px;">

<div style="background:linear-gradient(135deg,#0f1e4d 0%,#1447e6 100%);color:#fff;padding:24px 20px;border-radius:12px;margin-bottom:20px;">
<h1 style="font-size:22px;margin:0 0 8px;font-weight:800;">国际及国内热点新闻行业日报</h1>
<p style="margin:0;opacity:0.85;font-size:14px;">{today_str}（{today_weekday}）· 第 {issue_num} 期</p>
</div>

<h2 style="color:#1447e6;font-size:17px;border-bottom:2px solid #1447e6;padding-bottom:8px;">📌 今日头条速览</h2>
<ul style="padding-left:18px;line-height:1.8;">
{headlines_html}
</ul>

{sections_content}

<div style="background:#f0f3f9;padding:16px 20px;border-radius:10px;margin:20px 0;">
<p style="margin:0;font-size:14px;">📄 完整日报已生成，请查看服务器本地存档。</p>
</div>

<p style="font-size:12px;color:#888;margin-top:16px;border-top:1px solid #eee;padding-top:10px;">免责声明：本日报由程序自动从公开 RSS 源抓取生成，仅供信息参考，不构成投资建议。数据截至北京时间{today_str} 08:00。</p>

</div>"""

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

    try:
        resp = requests.post(
            url,
            json=payload,
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
