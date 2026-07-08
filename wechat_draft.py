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
import re
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from html import escape


def clean_text(text):
    """清理文本中的 HTML 实体、多余空白"""
    if not text:
        return ""
    text = text.replace("&amp;", "&").replace("&nbsp;", " ").replace("&amp;nbsp;", " ")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    text = text.replace("&ldquo;", "\u201c").replace("&rdquo;", "\u201d")
    text = text.replace("&hellip;", "\u2026")
    text = re.sub(r'[\u00a0\u2000-\u200b\u202f\u205f\u3000]+', ' ', text)
    text = re.sub(r' {3,}', '  ', text)
    return text.strip()


def strip_source_from_title(title):
    """从标题中去除来源后缀"""
    if not title:
        return title
    if re.search(r'[\u4e00-\u9fff]', title):
        match = re.search(r'\s+[-\u2013\u2014]+\s+', title)
        if match:
            prefix = title[:match.start()].strip()
            suffix = title[match.end():].strip()
            if len(prefix) > 5 and len(suffix) <= 15:
                return prefix
    return title


def dedup_title_summary(title, summary):
    """从摘要中提取标题之外的额外内容作为主要内容"""
    if not summary:
        return ""
    t = title.strip()
    s = summary.strip()
    
    # 如果摘要以标题开头，提取标题之后的内容
    if s.startswith(t):
        extra = s[len(t):].strip()
        # 去掉开头的分隔符 &nbsp; 等
        extra = re.sub(r'^[\s\u00a0&nbsp;]+', '', extra)
        if len(extra) > 10:
            return extra
        return ""
    
    # 如果去掉来源后缀的标题和摘要开头匹配
    t2 = strip_source_from_title(t)
    if t2 and s.startswith(t2):
        extra = s[len(t2):].strip()
        extra = re.sub(r'^[\s\u00a0]+', '', extra)
        if len(extra) > 10:
            return extra
        return ""
    
    # 摘要和标题完全一样
    if t == s:
        return ""
    
    # 摘要不以标题开头，直接用摘要
    return s


def is_chinese_text(text):
    """判断文本是否主要为中文"""
    if not text:
        return False
    chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return chinese_count / len(text) > 0.3

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
    """构建微信公众号文章 - 今日最热15条新闻，不分板块，简洁排版"""

    # 1. 汇总所有新闻，统一清理
    all_items = []
    for section_key, items in all_news.items():
        for item in items:
            title = clean_text(item.get("title", ""))
            summary = clean_text(item.get("summary", ""))
            title = strip_source_from_title(title)
            summary = dedup_title_summary(title, summary)
            if not title or not is_chinese_text(title):
                continue
            # 没有主要内容的新闻不要
            if not summary:
                continue
            all_items.append({
                "title": title,
                "summary": summary[:150] if summary else "",
                "link": item.get("link", ""),
            })

    # 2. 去重（不同板块可能有相同新闻）
    seen = set()
    unique_items = []
    for item in all_items:
        key = item["title"][:20]
        if key not in seen:
            seen.add(key)
            unique_items.append(item)

    # 3. 取前15条
    top_news = unique_items[:15]

    # 4. 构建新闻列表
    news_cards = []
    colors = ["#1447e6", "#d93025", "#0f9d58", "#7c3aed", "#0891b2",
              "#c9a227", "#ea580c", "#1447e6", "#d93025", "#0f9d58",
              "#7c3aed", "#0891b2", "#c9a227", "#ea580c", "#1447e6"]

    for idx, item in enumerate(top_news):
        color = colors[idx % len(colors)]
        num = idx + 1
        link_html = f' <a href="{escape(item["link"])}" style="font-size:12px;color:{color};text-decoration:none;">原文</a>' if item.get("link") else ""
        summary = item.get("summary", "")
        summary_html = f'<p style="font-size:13.5px;color:#5c6577;margin:5px 0 0;line-height:1.7;">{escape(summary)}</p>' if summary else ""
        news_cards.append(
            f'<section style="margin-bottom:18px;padding:14px 16px;background:#f8f9fc;border-radius:8px;border-left:3px solid {color};">'
            f'<p style="margin:0;line-height:1.5;">'
            f'<span style="display:inline-block;width:22px;height:22px;line-height:22px;text-align:center;background:{color};color:#fff;font-size:12px;font-weight:700;border-radius:50%;margin-right:8px;">{num}</span>'
            f'<span style="font-size:15px;font-weight:700;color:#1a2233;">{escape(item["title"])}</span>'
            f'{link_html}'
            f'</p>'
            f'{summary_html}'
            f'</section>'
        )
    news_html = "\n".join(news_cards)

    # 5. 组装
    html = f"""<section style="max-width:677px;margin:0 auto;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">

<section style="background:linear-gradient(135deg,#0f1e4d 0%,#1447e6 100%);color:#fff;padding:28px 22px;border-radius:0 0 14px 14px;margin-bottom:24px;">
<p style="font-size:11px;letter-spacing:2.5px;opacity:0.6;margin:0 0 10px;font-weight:600;">TOP 15 DAILY</p>
<p style="font-size:22px;font-weight:800;margin:0 0 6px;line-height:1.3;">热点新闻行业日报</p>
<p style="margin:0;opacity:0.82;font-size:14px;">{today_str}（{today_weekday}）· 第 {issue_num} 期</p>
</section>

<p style="font-size:14px;color:#5c6577;margin:0 0 20px;line-height:1.6;">今日最热 <strong style="color:#1447e6;">{len(top_news)}</strong> 条新闻速递，涵盖国内外时政、财经、科技、社会等领域。</p>

{news_html}

<p style="font-size:12px;color:#9aa3b2;margin-top:24px;border-top:1px solid #e3e6ec;padding-top:12px;line-height:1.6;">免责声明：本日报由程序自动从公开 RSS 源抓取生成，仅供信息参考，不构成任何投资建议。数据截至北京时间{today_str} 08:00。</p>

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
    # 标题格式：热点新闻行业日报_20260708
    title_date = datetime.now(BEIJING_TZ).strftime("%Y%m%d")
    title = f"热点新闻行业日报_{title_date}"
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
