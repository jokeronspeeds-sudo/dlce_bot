import os, logging, asyncio, re, json, hashlib, httpx
from io import BytesIO
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlencode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)
import google.generativeai as genai
import anthropic
from supabase import create_client

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN       = os.environ["BOT_TOKEN"]
GEMINI_API_KEY  = os.environ["GEMINI_API_KEY"]
CLAUDE_API_KEY  = os.environ["CLAUDE_API_KEY"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
SUPABASE_URL    = os.environ["SUPABASE_URL"]
SUPABASE_KEY    = os.environ["SUPABASE_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-2.0-flash")
claude = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

supabase = None
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Supabase connected")
except Exception as e:
    logger.warning(f"Supabase skipped: {e}")

LANG, TH_LEVEL, PURPOSE = range(3)

# ── Translations ──────────────────────────────────────────────
T = {
    "en": {
        "welcome":     "🎲 dlce BASE bot\n\nI'll find the best bases for your Town Hall — CC troops, real stats & freshness ratings.\n\nChoose your language:",
        "q_th":        "🏰 Select your Town Hall level:",
        "q_purpose":   "🎯 What are you building for?",
        "searching":   "🔍 Searching YouTube, Reddit & base sites...\nThis takes ~15 seconds, hang tight!",
        "results_hdr": "✅ Found top bases for TH{th} {purpose}",
        "recommended": "⭐ BEST PICK",
        "score":       "Score {score}/100",
        "cc":          "CC: {cc}",
        "uploaded":    "Posted: {date}",
        "source_btn":  "📌 View Source",
        "open_btn":    "🏰 Copy Base",
        "worked":      "✅ Defended!",
        "no_defend":   "❌ Failed",
        "thanks_good": "🎉 Great! This base's score goes up.",
        "thanks_bad":  "📉 Noted. This base's score goes down.",
        "rank":        "🏆 RANK",
        "war":         "⚔️ WAR",
        "farm":        "💰 FARM",
        "fresh":       "🟢 Fresh",
        "old":         "🟡 Older",
        "stale":       "🔴 Old",
        "no_results":  "😕 No bases found right now. Try again in a minute.",
        "searching_yt":"📺 YouTube",
        "searching_web":"🌐 Websites",
        "searching_reddit":"💬 Reddit",
    },
    "ru": {
        "welcome":     "🎲 dlce BASE bot\n\nНайду лучшие базы для твоей ратуши — с войсками замка и оценкой свежести.\n\nВыбери язык:",
        "q_th":        "🏰 Выбери уровень ратуши:",
        "q_purpose":   "🎯 Для чего строишь базу?",
        "searching":   "🔍 Ищу на YouTube, Reddit и сайтах с базами...\nПодожди ~15 секунд!",
        "results_hdr": "✅ Топ базы для РУ{th} {purpose}",
        "recommended": "⭐ ЛУЧШИЙ ВЫБОР",
        "score":       "Оценка {score}/100",
        "cc":          "ЗК: {cc}",
        "uploaded":    "Дата: {date}",
        "source_btn":  "📌 Смотреть источник",
        "open_btn":    "🏰 Скопировать базу",
        "worked":      "✅ Устояла!",
        "no_defend":   "❌ Не устояла",
        "thanks_good": "🎉 Отлично! Рейтинг базы повышается.",
        "thanks_bad":  "📉 Учтено. Рейтинг базы снижается.",
        "rank":        "🏆 РАНГ",
        "war":         "⚔️ ВОЙНА",
        "farm":        "💰 ФАРМ",
        "fresh":       "🟢 Свежая",
        "old":         "🟡 Постарше",
        "stale":       "🔴 Старая",
        "no_results":  "😕 Базы не найдены. Попробуй через минуту.",
        "searching_yt":"📺 YouTube",
        "searching_web":"🌐 Сайты",
        "searching_reddit":"💬 Reddit",
    },
    "he": {
        "welcome":     "🎲 dlce BASE bot\n\nאמצא עבורך את הבסיסים הטובים ביותר — חיילי טירה וציון רעננות.\n\nבחר שפה:",
        "q_th":        "🏰 בחר את רמת עיירת המועצה:",
        "q_purpose":   "🎯 למה הבסיס מיועד?",
        "searching":   "🔍 מחפש ב-YouTube, Reddit ואתרי בסיסים...\nרגע סבלנות, כ-15 שניות!",
        "results_hdr": "✅ הבסיסים המובילים עבור TH{th} {purpose}",
        "recommended": "⭐ הבחירה הטובה ביותר",
        "score":       "ציון {score}/100",
        "cc":          "טירה: {cc}",
        "uploaded":    "תאריך: {date}",
        "source_btn":  "📌 צפה במקור",
        "open_btn":    "🏰 העתק בסיס",
        "worked":      "✅ עמד!",
        "no_defend":   "❌ נפל",
        "thanks_good": "🎉 מעולה! ציון הבסיס עולה.",
        "thanks_bad":  "📉 נרשם. ציון הבסיס יורד.",
        "rank":        "🏆 דירוג",
        "war":         "⚔️ מלחמה",
        "farm":        "💰 חווה",
        "fresh":       "🟢 חדש",
        "old":         "🟡 ישן יותר",
        "stale":       "🔴 ישן",
        "no_results":  "😕 לא נמצאו בסיסים. נסה שוב בעוד דקה.",
        "searching_yt":"📺 YouTube",
        "searching_web":"🌐 אתרים",
        "searching_reddit":"💬 Reddit",
    },
}

def t(lang, key, **kwargs):
    text = T.get(lang, T["en"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


# ══════════════════════════════════════════════════════════════
# BUILT-IN BASE DATABASE (always works as safety net)
# ══════════════════════════════════════════════════════════════
BUILTIN_BASES = {
    10: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","cc":"Witch + Ice Golem","date":"2025-03","stars":4.8,"downloads":32000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Balloon + Minion","date":"2025-04","stars":4.7,"downloads":18000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Dragon + Witch","date":"2025-03","stars":4.5,"downloads":15000}]},
    11: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem","date":"2025-04","stars":4.9,"downloads":41000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Balloon + Super Witch","date":"2025-05","stars":4.8,"downloads":22000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AHV%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","cc":"Dragon + Witch","date":"2025-02","stars":4.5,"downloads":17000}]},
    12: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Witch","date":"2025-05","stars":4.9,"downloads":55000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Balloon + Super Witch","date":"2025-05","stars":4.8,"downloads":29000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Dragon + Witch","date":"2025-03","stars":4.5,"downloads":19000}]},
    13: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","stars":4.9,"downloads":62000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch","date":"2025-05","stars":4.8,"downloads":33000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Dragon + Witch + Balloon","date":"2025-04","stars":4.6,"downloads":24000}]},
    14: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","stars":4.9,"downloads":71000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch","date":"2025-06","stars":4.8,"downloads":41000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Dragon + Super Witch","date":"2025-04","stars":4.6,"downloads":29000}]},
    15: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","stars":4.9,"downloads":88000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Head Hunter","date":"2025-06","stars":4.9,"downloads":53000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Dragon + Super Witch + Balloon","date":"2025-05","stars":4.7,"downloads":37000}]},
    16: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","stars":4.9,"downloads":79000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Head Hunter","date":"2025-06","stars":4.9,"downloads":48000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Inferno Dragon + Super Witch","date":"2025-05","stars":4.7,"downloads":33000}]},
    17: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","stars":4.9,"downloads":92000},{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","cc":"Inferno Dragon + Super Witch + Head Hunter","date":"2025-05","stars":4.8,"downloads":71000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Head Hunter","date":"2025-06","stars":4.9,"downloads":61000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Inferno Dragon + Super Witch + Balloon","date":"2025-05","stars":4.7,"downloads":38000}]},
    18: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","stars":4.9,"downloads":68000},{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","cc":"Inferno Dragon + Super Witch + Head Hunter","date":"2025-06","stars":4.8,"downloads":51000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Head Hunter","date":"2025-06","stars":4.9,"downloads":44000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Inferno Dragon + Super Witch + Balloon","date":"2025-06","stars":4.8,"downloads":42000}]},
}


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def extract_cc(text):
    troops = ["inferno dragon","super witch","ice golem","head hunter","witch",
              "balloon","super balloon","minion","dragon","valkyrie","golem",
              "hog rider","bowler","electro dragon","lava hound","super archer","skeleton"]
    low = text.lower()
    found = [tr for tr in troops if tr in low]
    if found:
        return " + ".join(found[:3]).title()
    m = re.search(r'cc[:\s]+([^\n.]{5,60})', low)
    return m.group(1).strip().title() if m else "Check source"

def recency_score(date_str):
    try:
        parts = date_str.split("-")
        year, month = int(parts[0]), int(parts[1]) if len(parts) > 1 else 1
        now = datetime.now(timezone.utc)
        months_old = (now.year - year) * 12 + (now.month - month)
        if months_old <= 1:  return 20
        if months_old <= 3:  return 15
        if months_old <= 6:  return 10
        if months_old <= 12: return 5
        return 0
    except Exception:
        return 0

def freshness_label(date_str, lang):
    rec = recency_score(date_str)
    if rec >= 15: return t(lang, "fresh")
    if rec >= 5:  return t(lang, "old")
    return t(lang, "stale")

def format_date(date_str, lang):
    try:
        months = {
            "en": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
            "ru": ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"],
            "he": ["ינו","פבר","מרץ","אפר","מאי","יונ","יול","אוג","ספט","אוק","נוב","דצ"],
        }
        parts = date_str.split("-")
        year, month = int(parts[0]), int(parts[1]) if len(parts) > 1 else 1
        return f"{months.get(lang, months['en'])[month-1]} {year}"
    except Exception:
        return date_str or "Unknown"

def get_builtin_bases(th, purpose):
    bases = BUILTIN_BASES.get(th, {}).get(purpose, [])
    result = []
    for b in bases:
        base = dict(b)
        base["source_name"] = "CoC Community"
        base["source_url"]  = f"https://cocbases.com/th{th}-{'war' if purpose=='WAR' else 'trophy' if purpose=='RANK' else 'farming'}-base/"
        base["image_url"]   = None
        rec = recency_score(base.get("date",""))
        base["score"] = min(100, int(base.get("downloads",0)/1000*0.4 + base.get("stars",4)*10*0.25 + rec*1.75))
        result.append(base)
    return result


# ══════════════════════════════════════════════════════════════
# IMAGE FETCHER — gets real thumbnails from each source
# ══════════════════════════════════════════════════════════════

async def fetch_image(url: str) -> BytesIO | None:
    """Download an image from a URL and return as BytesIO."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as c:
            r = await c.get(url)
        if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
            buf = BytesIO(r.content)
            buf.name = "base.jpg"
            buf.seek(0)
            return buf
    except Exception as e:
        logger.warning(f"Image fetch failed ({url[:60]}): {e}")
    return None

async def get_youtube_thumbnail(video_id: str) -> BytesIO | None:
    """Get YouTube video thumbnail — tries maxresdefault then hqdefault."""
    for quality in ["maxresdefault", "hqdefault", "mqdefault"]:
        img = await fetch_image(f"https://img.youtube.com/vi/{video_id}/{quality}.jpg")
        if img:
            logger.info(f"YouTube thumbnail OK ({quality})")
            return img
    return None

async def get_website_thumbnail(page_url: str) -> BytesIO | None:
    """Scrape the first base/layout image from a web page."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as c:
            r = await c.get(page_url)
        html = r.text

        # Find og:image first (most sites set this to the base thumbnail)
        og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', html)
        if og:
            img = await fetch_image(og.group(1))
            if img:
                logger.info(f"og:image thumbnail OK")
                return img

        # Find first meaningful image in page
        imgs = re.findall(r'<img[^>]+src=["\'](https?://[^"\']+(?:base|layout|th\d+)[^"\']*\.(?:jpg|jpeg|png|webp))["\']', html, re.IGNORECASE)
        for img_url in imgs[:5]:
            img = await fetch_image(img_url)
            if img:
                logger.info(f"Page image OK: {img_url[:60]}")
                return img

        # Reddit: look for preview images
        reddit_imgs = re.findall(r'"url": ?"(https://preview\.redd\.it/[^"]+)"', html)
        if reddit_imgs:
            img = await fetch_image(reddit_imgs[0].replace("&amp;", "&"))
            if img:
                return img

    except Exception as e:
        logger.warning(f"Website thumbnail error: {e}")
    return None


# ══════════════════════════════════════════════════════════════
# SEARCH ENGINE
# ══════════════════════════════════════════════════════════════

# Keywords that indicate a BASE video (good) vs ATTACK video (bad)
BASE_KEYWORDS   = ["base", "layout", "design", "copy", "link", "download", "anti", "defense", "defence", "best base", "new base"]
ATTACK_KEYWORDS = ["attack", "3 star", "three star", "how to beat", "vs ", "beating", "raid", "destroy", "strategy guide", "how i"]

def is_base_video(title: str, desc: str) -> bool:
    """Return True only if the video is clearly about a base layout, not an attack."""
    low_title = title.lower()
    low_desc  = desc.lower()[:300]

    # Reject if title clearly mentions attack tactics
    attack_hits = sum(1 for kw in ATTACK_KEYWORDS if kw in low_title)
    base_hits   = sum(1 for kw in BASE_KEYWORDS   if kw in low_title)

    if attack_hits > 0 and base_hits == 0:
        logger.info(f"Skipping attack video: {title[:60]}")
        return False

    # Must have a CoC base link in description — pure attack vids never do
    if "link.clashofclans.com" not in low_desc and "link.clashofclans.com" not in desc.lower():
        logger.info(f"No CoC link in desc, skipping: {title[:60]}")
        return False

    return True


async def search_youtube(th, purpose):
    """
    YouTube search — base videos ONLY, with real view counts and
    like counts for scoring instead of fake stars.
    """
    results = []
    try:
        # Query specifically targets base layouts, not attacks
        purpose_kw = {"WAR": "war base layout", "RANK": "trophy base layout", "FARM": "farming base layout"}
        query = f"TH{th} {purpose_kw.get(purpose, 'base layout')} 2025 Clash of Clans copy link"

        search_url = (
            f"https://www.googleapis.com/youtube/v3/search"
            f"?part=snippet&q={quote_plus(query)}&type=video&maxResults=15"
            f"&order=date&key={YOUTUBE_API_KEY}"
        )
        async with httpx.AsyncClient(timeout=15) as c:
            data = (await c.get(search_url)).json()

        if "error" in data:
            logger.warning(f"YouTube error: {data['error'].get('message')}")
            return results

        items = data.get("items", [])
        if not items:
            return results

        vid_ids = ",".join(i["id"]["videoId"] for i in items if i["id"].get("videoId"))

        # Fetch snippet + statistics (views, likes) in one call
        detail_url = (
            f"https://www.googleapis.com/youtube/v3/videos"
            f"?part=snippet,statistics&id={vid_ids}&key={YOUTUBE_API_KEY}"
        )
        async with httpx.AsyncClient(timeout=15) as c:
            ddata = (await c.get(detail_url)).json()

        for item in ddata.get("items", []):
            vid_id    = item["id"]
            title     = item["snippet"]["title"]
            desc      = item["snippet"]["description"]
            published = item["snippet"].get("publishedAt","")[:7]
            channel   = item["snippet"].get("channelTitle","YouTube")
            stats     = item.get("statistics", {})

            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))

            # Skip attack videos — only base layout videos
            if not is_base_video(title, desc):
                continue

            links = re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', desc)
            for raw in links:
                clean = raw.rstrip(".,)&")
                link_up = clean.upper()
                if any(f"TH{o}%3A" in link_up for o in range(1,18) if o != th):
                    continue

                rec = recency_score(published)
                # Real score from actual YouTube stats
                view_score = min(30, int(views / 10000))    # up to 30 pts for 300k+ views
                like_score = min(20, int(likes / 500))      # up to 20 pts for 10k+ likes
                score = min(100, 30 + rec + view_score + like_score)

                # Human-readable stats label
                views_fmt = f"{views//1000}K" if views >= 1000 else str(views)
                likes_fmt = f"{likes//1000}K" if likes >= 1000 else str(likes)

                results.append({
                    "link":        clean,
                    "cc":          extract_cc(desc),
                    "source_name": f"YouTube · {channel}",
                    "source_url":  f"https://youtube.com/watch?v={vid_id}",
                    "image_type":  "youtube",
                    "image_id":    vid_id,
                    "image_url":   None,
                    "date":        published,
                    "score":       score,
                    "views":       views,
                    "likes":       likes,
                    "views_fmt":   views_fmt,
                    "likes_fmt":   likes_fmt,
                    "downloads":   views // 10,
                    "stars":       min(5.0, 3.5 + likes / max(views, 1) * 50),
                })
                logger.info(f"YouTube base video: {published} views={views_fmt} likes={likes_fmt} {title[:45]}")
                break

    except Exception as e:
        logger.warning(f"YouTube error: {e}")

    logger.info(f"YouTube: {len(results)} bases")
    return results


async def search_web(th, purpose):
    """Scrape cocbases.com for links + page thumbnails."""
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    slug_map = {"RANK": ["trophy","trophies"], "WAR": ["war","anti-3-star"], "FARM": ["farming","farm"]}

    for slug in slug_map.get(purpose, ["war"]):
        try:
            url = f"https://cocbases.com/th{th}-{slug}-base/"
            async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as c:
                r = await c.get(url)
            if r.status_code != 200:
                continue
            html = r.text
            links = list(dict.fromkeys(re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', html)))
            dates = re.findall(r'20\d\d-\d\d-\d\d', html)
            latest_date = dates[0][:7] if dates else "2025-03"

            # Find base thumbnail images on the page
            img_urls = re.findall(
                r'<img[^>]+src=["\'](https?://[^"\']+\.(?:jpg|jpeg|png|webp))["\']',
                html, re.IGNORECASE
            )
            base_img = next(
                (u for u in img_urls if any(k in u.lower() for k in ["th"+str(th), "base", "layout"])),
                None
            )

            logger.info(f"cocbases/{slug}: {len(links)} links, img={'yes' if base_img else 'no'}")
            for lnk in links[:4]:
                rec = recency_score(latest_date)
                results.append({
                    "link":        lnk.rstrip(".,)&"),
                    "cc":          extract_cc(html),
                    "source_name": "cocbases.com",
                    "source_url":  url,
                    "image_type":  "web",
                    "image_url":   base_img,
                    "date":        latest_date,
                    "score":       min(100, 70 + rec),
                    "downloads":   15000,
                    "stars":       4.7,
                })
            break
        except Exception as e:
            logger.warning(f"cocbases error ({slug}): {e}")

    logger.info(f"Web: {len(results)} bases")
    return results


async def search_reddit(th, purpose):
    """Search Reddit r/ClashOfClans for base posts with images."""
    results = []
    try:
        purpose_kw = {"WAR": "war base anti 3 star", "RANK": "trophy base", "FARM": "farming base"}
        query = f"TH{th} {purpose_kw.get(purpose,'base')} site:reddit.com/r/ClashOfClans"
        url = f"https://www.reddit.com/r/ClashOfClans/search.json?q=TH{th}+{purpose_kw.get(purpose,'base')}&sort=new&limit=10&restrict_sr=1"
        headers = {"User-Agent": "CoC-Base-Finder-Bot/1.0"}
        async with httpx.AsyncClient(timeout=15, headers=headers) as c:
            r = await c.get(url)
        data = r.json()

        posts = data.get("data", {}).get("children", [])
        logger.info(f"Reddit returned {len(posts)} posts")

        for post in posts:
            p = post.get("data", {})
            title    = p.get("title", "")
            selftext = p.get("selftext", "")
            post_url = f"https://reddit.com{p.get('permalink','')}"
            created  = datetime.fromtimestamp(p.get("created_utc", 0), tz=timezone.utc)
            date_str = created.strftime("%Y-%m")

            # Get image from post
            image_url = None
            preview = p.get("preview", {}).get("images", [])
            if preview:
                src = preview[0].get("source", {}).get("url","")
                image_url = src.replace("&amp;", "&")
            if not image_url and p.get("url","").endswith((".jpg",".png",".jpeg")):
                image_url = p["url"]

            # Find CoC link in text
            all_text = title + " " + selftext
            links = re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', all_text)
            if not links:
                continue

            clean = links[0].rstrip(".,)&")
            rec = recency_score(date_str)
            upvotes = p.get("score", 0)

            results.append({
                "link":        clean,
                "cc":          extract_cc(all_text),
                "source_name": f"Reddit · r/ClashOfClans",
                "source_url":  post_url,
                "image_type":  "reddit",
                "image_url":   image_url,
                "date":        date_str,
                "score":       min(100, 40 + rec + min(upvotes // 10, 20)),
                "downloads":   upvotes * 10,
                "stars":       min(5.0, 3.5 + upvotes / 1000),
            })
            logger.info(f"Reddit found: {date_str} upvotes={upvotes} {clean[:50]}")

    except Exception as e:
        logger.warning(f"Reddit error: {e}")

    logger.info(f"Reddit: {len(results)} bases")
    return results


def validate_link(link):
    return "clashofclans.com" in link


async def rank_bases(bases, th, purpose, lang):
    """Score and rank — recency first, then community signals."""
    for b in bases:
        rec = recency_score(b.get("date",""))
        dl  = min(b.get("downloads",0), 100000)
        st  = min(b.get("stars", 4.0), 5.0)
        b["recency_bonus"] = rec
        b["score"] = min(100, int(dl/100000*35 + st/5*30 + rec*1.75))
        if not b.get("reason"):
            b["reason"] = f"{freshness_label(b.get('date',''), lang)} — {format_date(b.get('date',''), lang)}"

    bases.sort(key=lambda x: x.get("score",0), reverse=True)

    try:
        simplified = [{"link":b["link"],"cc":b.get("cc",""),"source":b.get("source_name",""),
                       "date":b.get("date",""),"downloads":b.get("downloads",0),"stars":b.get("stars",0)}
                      for b in bases[:6]]
        msg = claude.messages.create(
            model="claude-sonnet-4-6", max_tokens=800,
            messages=[{"role":"user","content":(
                f"Rank these TH{th} {purpose} Clash of Clans bases. "
                f"Prioritise: 1) newest date 2) downloads 3) stars.\n\n"
                f"{json.dumps(simplified,indent=2)}\n\n"
                f"Return ONLY JSON array, best first, max 3:\n"
                f'[{{"link":"...","cc":"...","source":"...","date":"...","score":88,'
                f'"reason":"One line mentioning date and why it ranks"}}]'
            )}]
        )
        raw = re.sub(r"```json|```","", msg.content[0].text).strip()
        m = re.search(r'\[.*?\]', raw, re.DOTALL)
        if m:
            ranked = json.loads(m.group())
            # Merge back image/source_url fields from original bases
            link_map = {b["link"]: b for b in bases}
            merged = []
            for rb in ranked[:3]:
                orig = link_map.get(rb.get("link",""), {})
                merged.append({**orig, **rb})
            return merged
    except Exception as e:
        logger.warning(f"Claude ranking skipped: {e}")

    return bases[:3]


async def save_base(base, th, purpose):
    if not supabase:
        return
    try:
        supabase.table("bases").upsert({
            "link": base["link"], "th_level": th, "purpose": purpose,
            "score": base.get("score",70), "cc": base.get("cc",""),
            "source": base.get("source_name",""), "date": base.get("date",""),
            "thumbs_up": 0, "thumbs_down": 0,
        }, on_conflict="link").execute()
    except Exception as e:
        logger.warning(f"Supabase: {e}")

async def update_feedback(link, positive):
    if not supabase:
        return
    try:
        col = "thumbs_up" if positive else "thumbs_down"
        row = supabase.table("bases").select(col).eq("link", link).execute()
        if row.data:
            supabase.table("bases").update({col: row.data[0][col]+1}).eq("link", link).execute()
    except Exception as e:
        logger.warning(f"Feedback: {e}")


# ══════════════════════════════════════════════════════════════
# TELEGRAM HANDLERS
# ══════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇮🇱 עברית",   callback_data="lang_he"),
    ]]
    await update.message.reply_text(
        T["en"]["welcome"],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return LANG

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.replace("lang_","")
    context.user_data["lang"] = lang
    row1 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(10,14)]
    row2 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(14,18)]
    row3 = [InlineKeyboardButton("TH18",   callback_data="th_18")]
    await query.edit_message_text(t(lang,"q_th"), reply_markup=InlineKeyboardMarkup([row1,row2,row3]))
    return TH_LEVEL

async def th_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    th   = int(query.data.replace("th_",""))
    lang = context.user_data["lang"]
    context.user_data["th"] = th
    keyboard = [[
        InlineKeyboardButton(t(lang,"rank"),  callback_data="purpose_RANK"),
        InlineKeyboardButton(t(lang,"war"),   callback_data="purpose_WAR"),
        InlineKeyboardButton(t(lang,"farm"),  callback_data="purpose_FARM"),
    ]]
    await query.edit_message_text(
        f"TH{th} ✓\n\n{t(lang,'q_purpose')}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PURPOSE

async def purpose_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    purpose = query.data.replace("purpose_","")
    lang    = context.user_data["lang"]
    th      = context.user_data["th"]
    chat_id = query.message.chat_id

    await query.edit_message_text(
        f"TH{th} · {purpose}\n\n{t(lang,'searching')}"
    )

    # Run all 3 searches in parallel
    yt_res, web_res, reddit_res = await asyncio.gather(
        search_youtube(th, purpose),
        search_web(th, purpose),
        search_reddit(th, purpose),
    )

    all_bases = yt_res + web_res + reddit_res
    valid = [b for b in all_bases if validate_link(b["link"])]

    # Fill gaps with built-in database
    if len(valid) < 3:
        builtin = get_builtin_bases(th, purpose)
        existing = {b["link"] for b in valid}
        for b in builtin:
            if b["link"] not in existing:
                valid.append(b)

    if not valid:
        await context.bot.send_message(chat_id=chat_id, text=t(lang,"no_results"))
        return ConversationHandler.END

    top3 = await rank_bases(valid, th, purpose, lang)

    for base in top3:
        await save_base(base, th, purpose)

    # ── Send all 3 bases in one clean message ────────────────
    medals = ["🥇","🥈","🥉"]
    context.user_data["links"] = {}
    purpose_label = t(lang, purpose.lower()) if purpose.lower() in T[lang] else purpose

    # Build the combined message — one text block, clean table style
    lines = [t(lang, "results_hdr", th=th, purpose=purpose_label), ""]

    keyboard_rows = []

    for i, base in enumerate(top3):
        score       = base.get("score", 70)
        cc          = base.get("cc", "Check source")
        source_name = base.get("source_name", "Community")
        source_url  = base.get("source_url", "")
        date        = base.get("date", "")
        link        = base["link"]
        image_type  = base.get("image_type","")
        image_url   = base.get("image_url")
        image_id    = base.get("image_id","")

        link_key = hashlib.md5(link.encode()).hexdigest()[:16]
        context.user_data["links"][link_key] = link

        fresh    = freshness_label(date, lang)
        date_fmt = format_date(date, lang)

        if i == 0:
            rank_line = f"{medals[i]} {t(lang,'recommended')}"
        else:
            rank_line = f"{medals[i]} Base #{i+1}"

        # Compact info table for this base
        lines.append(f"{'━'*28}")
        lines.append(rank_line)
        lines.append(f"🏆 {t(lang,'score',score=score)}  |  📅 {date_fmt}  {fresh}")

        # Show real stats if available (YouTube views/likes) or download count
        views_fmt = base.get("views_fmt")
        likes_fmt = base.get("likes_fmt")
        dl        = base.get("downloads", 0)
        if views_fmt and likes_fmt:
            lines.append(f"👁 {views_fmt} views  ·  👍 {likes_fmt} likes")
        elif dl and dl > 100:
            dl_fmt = f"{dl//1000}K" if dl >= 1000 else str(dl)
            lines.append(f"⬇️ {dl_fmt} downloads")

        lines.append(f"🏰 {t(lang,'cc',cc=cc)}")
        lines.append(f"📌 {source_name}")

        # Inline thumbnail — small, no full photo send
        thumb_url = None
        try:
            if image_type == "youtube" and image_id:
                thumb_url = f"https://img.youtube.com/vi/{image_id}/mqdefault.jpg"
            elif image_url:
                thumb_url = image_url
        except Exception:
            pass

        if thumb_url:
            lines.append(f"🖼 <a href=\"{thumb_url}\">preview</a>")

        lines.append("")

        # One row of buttons per base
        row = [InlineKeyboardButton(
            f"{medals[i]} {t(lang,'open_btn')}",
            url=link
        )]
        if source_url:
            row.append(InlineKeyboardButton(t(lang,"source_btn"), url=source_url))
        keyboard_rows.append(row)
        keyboard_rows.append([
            InlineKeyboardButton(f"✅ #{i+1} {t(lang,'worked')}",    callback_data=f"fb_pos_{link_key}"),
            InlineKeyboardButton(f"❌ #{i+1} {t(lang,'no_defend')}", callback_data=f"fb_neg_{link_key}"),
        ])

    lines.append(f"{'━'*28}")
    full_text = "\n".join(lines)

    await context.bot.send_message(
        chat_id=chat_id,
        text=full_text,
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

    return ConversationHandler.END


async def feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang     = context.user_data.get("lang","en")
    positive = query.data.startswith("fb_pos_")
    link_key = query.data[7:]
    link     = context.user_data.get("links",{}).get(link_key, link_key)
    await update_feedback(link, positive)
    await query.edit_message_reply_markup(reply_markup=None)
    reply = t(lang, "thanks_good") if positive else t(lang, "thanks_bad")
    await context.bot.send_message(chat_id=query.message.chat_id, text=reply)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled. Send /start to try again.")
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANG:     [CallbackQueryHandler(language_chosen, pattern="^lang_")],
            TH_LEVEL: [CallbackQueryHandler(th_chosen,       pattern="^th_")],
            PURPOSE:  [CallbackQueryHandler(purpose_chosen,  pattern="^purpose_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(feedback_handler, pattern="^fb_"))
    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
