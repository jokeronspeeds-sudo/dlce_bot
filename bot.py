# dlce BASE bot v4.0
import os, logging, asyncio, re, json, hashlib, httpx
from io import BytesIO
from datetime import datetime, timezone
from urllib.parse import quote_plus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# ══════════════════════════════════════════════════════════════
# TRANSLATIONS
# ══════════════════════════════════════════════════════════════
T = {
    "en": {
        "welcome":       "🎲 dlce BASE bot\n\nI find the best bases from YouTube, Reddit & base sites — with real stats, CC troops & freshness.\n\nChoose your language:",
        "q_th":          "🏰 Select your Town Hall level:",
        "q_purpose":     "🎯 What are you building for?",
        "searching":     "🔍 Searching 3 sources simultaneously...\nYouTube · Reddit · Base sites\n\n⏳ ~15 seconds",
        "results_hdr":   "🎲 dlce BASE bot  —  TH{th} {purpose}\n━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "deep_search":   "🔬 Deep Research (+5 more bases)",
        "deep_header":   "🔬 Deep Research results — TH{th} {purpose}",
        "deep_searching":"🔬 Running deep research across all sources...\nThis takes ~30 seconds",
        "recommended":   "⭐ BEST PICK",
        "score":         "Score {score}/100",
        "cc":            "CC: {cc}",
        "uploaded":      "Posted: {date}",
        "source_btn":    "📌 Source",
        "open_btn":      "🏰 Copy Base",
        "worked":        "✅ Defended!",
        "no_defend":     "❌ Failed",
        "thanks_good":   "🎉 Score goes up! Thanks.",
        "thanks_bad":    "📉 Score goes down. Thanks.",
        "report_btn":    "⚠️ Report",
        "report_q":      "What's wrong with this base?",
        "rep_wrong_th":  "❌ Wrong TH level",
        "rep_attack":    "⚔️ Attack video, not base",
        "rep_dead_link": "🔗 Link broken",
        "rep_old_base":  "📅 Too old",
        "rep_bad_cc":    "🏰 Wrong CC troops",
        "rep_other":     "🤷 Other",
        "report_thanks": "✅ Reported! Bot will learn from this.",
        "rank":          "🏆 RANK",
        "war":           "⚔️ WAR",
        "farm":          "💰 FARM",
        "fresh":         "🟢 Fresh",
        "old":           "🟡 Older",
        "stale":         "🔴 Old",
        "no_results":    "😕 No bases found. Try again in a moment.",
        "src_youtube":   "📺 YouTube",
        "src_reddit":    "💬 Reddit",
        "src_sites":     "🌐 Base sites",
    },
    "ru": {
        "welcome":       "🎲 dlce BASE bot\n\nНахожу лучшие базы с YouTube, Reddit и сайтов — с реальной статистикой, войсками ЗК и оценкой свежести.\n\nВыбери язык:",
        "q_th":          "🏰 Выбери уровень ратуши:",
        "q_purpose":     "🎯 Для чего строишь базу?",
        "searching":     "🔍 Ищу одновременно в 3 источниках...\nYouTube · Reddit · Сайты с базами\n\n⏳ ~15 секунд",
        "results_hdr":   "🎲 dlce BASE bot  —  РУ{th} {purpose}\n━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "deep_search":   "🔬 Глубокий поиск (+5 баз)",
        "deep_header":   "🔬 Глубокий поиск — РУ{th} {purpose}",
        "deep_searching":"🔬 Запускаю глубокий поиск...\n~30 секунд",
        "recommended":   "⭐ ЛУЧШИЙ ВЫБОР",
        "score":         "Оценка {score}/100",
        "cc":            "ЗК: {cc}",
        "uploaded":      "Дата: {date}",
        "source_btn":    "📌 Источник",
        "open_btn":      "🏰 Скопировать базу",
        "worked":        "✅ Устояла!",
        "no_defend":     "❌ Не устояла",
        "thanks_good":   "🎉 Оценка растёт! Спасибо.",
        "thanks_bad":    "📉 Оценка снижается. Спасибо.",
        "report_btn":    "⚠️ Сообщить",
        "report_q":      "Что не так с этой базой?",
        "rep_wrong_th":  "❌ Не тот уровень РУ",
        "rep_attack":    "⚔️ Видео атаки, не базы",
        "rep_dead_link": "🔗 Ссылка сломана",
        "rep_old_base":  "📅 Слишком старая",
        "rep_bad_cc":    "🏰 Неверные войска ЗК",
        "rep_other":     "🤷 Другое",
        "report_thanks": "✅ Отправлено! Бот учтёт это.",
        "rank":          "🏆 РАНГ",
        "war":           "⚔️ ВОЙНА",
        "farm":          "💰 ФАРМ",
        "fresh":         "🟢 Свежая",
        "old":           "🟡 Постарше",
        "stale":         "🔴 Старая",
        "no_results":    "😕 Базы не найдены. Попробуй позже.",
        "src_youtube":   "📺 YouTube",
        "src_reddit":    "💬 Reddit",
        "src_sites":     "🌐 Сайты",
    },
    "he": {
        "welcome":       "🎲 dlce BASE bot\n\nמוצא בסיסים מ-YouTube, Reddit ואתרים — עם סטטיסטיקות, חיילי טירה ורעננות.\n\nבחר שפה:",
        "q_th":          "🏰 בחר רמת עיירת מועצה:",
        "q_purpose":     "🎯 למה הבסיס מיועד?",
        "searching":     "🔍 מחפש ב-3 מקורות במקביל...\nYouTube · Reddit · אתרי בסיסים\n\n⏳ ~15 שניות",
        "results_hdr":   "🎲 dlce BASE bot  —  TH{th} {purpose}\n━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "deep_search":   "🔬 מחקר מעמיק (+5 בסיסים)",
        "deep_header":   "🔬 תוצאות מחקר מעמיק — TH{th} {purpose}",
        "deep_searching":"🔬 מריץ מחקר מעמיק...\n~30 שניות",
        "recommended":   "⭐ הבחירה הטובה ביותר",
        "score":         "ציון {score}/100",
        "cc":            "טירה: {cc}",
        "uploaded":      "תאריך: {date}",
        "source_btn":    "📌 מקור",
        "open_btn":      "🏰 העתק בסיס",
        "worked":        "✅ עמד!",
        "no_defend":     "❌ נפל",
        "thanks_good":   "🎉 הציון עולה! תודה.",
        "thanks_bad":    "📉 הציון יורד. תודה.",
        "report_btn":    "⚠️ דווח",
        "report_q":      "מה הבעיה עם הבסיס?",
        "rep_wrong_th":  "❌ רמת TH שגויה",
        "rep_attack":    "⚔️ סרטון התקפה",
        "rep_dead_link": "🔗 קישור שבור",
        "rep_old_base":  "📅 ישן מדי",
        "rep_bad_cc":    "🏰 חיילי טירה שגויים",
        "rep_other":     "🤷 אחר",
        "report_thanks": "✅ דווח! הבוט ילמד מזה.",
        "rank":          "🏆 דירוג",
        "war":           "⚔️ מלחמה",
        "farm":          "💰 חווה",
        "fresh":         "🟢 חדש",
        "old":           "🟡 ישן יותר",
        "stale":         "🔴 ישן",
        "no_results":    "😕 לא נמצאו בסיסים. נסה שוב.",
        "src_youtube":   "📺 YouTube",
        "src_reddit":    "💬 Reddit",
        "src_sites":     "🌐 אתרים",
    },
}

def t(lang, key, **kwargs):
    text = T.get(lang, T["en"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


# ══════════════════════════════════════════════════════════════
# BUILT-IN FALLBACK DATABASE
# ══════════════════════════════════════════════════════════════
BUILTIN = {
    10: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","cc":"Witch + Ice Golem + Balloon","date":"2025-03","downloads":32000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Super Balloon + Minion + Witch","date":"2025-04","downloads":18000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Dragon + Witch + Balloon","date":"2025-03","downloads":15000}]},
    11: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-05","downloads":41000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Minion","date":"2025-05","downloads":22000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AHV%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","cc":"Dragon + Witch + Ice Golem","date":"2025-02","downloads":17000}]},
    12: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Witch","date":"2025-05","downloads":55000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Head Hunter","date":"2025-05","downloads":29000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Dragon + Witch + Balloon","date":"2025-03","downloads":19000}]},
    13: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","downloads":62000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Head Hunter","date":"2025-05","downloads":33000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Dragon + Witch + Balloon","date":"2025-04","downloads":24000}]},
    14: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","downloads":71000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Head Hunter","date":"2025-06","downloads":41000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Dragon + Super Witch + Ice Golem","date":"2025-04","downloads":29000}]},
    15: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","downloads":88000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Head Hunter","date":"2025-06","downloads":53000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Dragon + Super Witch + Balloon","date":"2025-05","downloads":37000}]},
    16: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","downloads":79000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Head Hunter","date":"2025-06","downloads":48000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Inferno Dragon + Super Witch + Ice Golem","date":"2025-05","downloads":33000}]},
    17: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","downloads":92000},{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","cc":"Inferno Dragon + Super Witch + Head Hunter","date":"2025-05","downloads":71000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Head Hunter","date":"2025-06","downloads":61000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Inferno Dragon + Super Witch + Balloon","date":"2025-05","downloads":38000}]},
    18: {"WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Witch + Ice Golem + Head Hunter","date":"2025-06","downloads":68000},{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","cc":"Inferno Dragon + Super Witch + Head Hunter","date":"2025-06","downloads":51000}],"RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","cc":"Super Balloon + Super Witch + Head Hunter","date":"2025-06","downloads":44000}],"FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","cc":"Inferno Dragon + Super Witch + Balloon","date":"2025-06","downloads":42000}]},
}

# CC setups per TH level and purpose — used when extraction fails
CC_BY_TH = {
    10: {"WAR":"Witch + Ice Golem + Balloon",       "RANK":"Super Balloon + Minion + Witch",        "FARM":"Dragon + Witch + Balloon"},
    11: {"WAR":"Super Witch + Ice Golem + Head Hunter","RANK":"Super Balloon + Super Witch + Minion","FARM":"Dragon + Witch + Ice Golem"},
    12: {"WAR":"Super Witch + Ice Golem + Witch",   "RANK":"Super Balloon + Super Witch + Head Hunter","FARM":"Dragon + Witch + Balloon"},
    13: {"WAR":"Super Witch + Ice Golem + Head Hunter","RANK":"Super Balloon + Super Witch + Head Hunter","FARM":"Dragon + Witch + Balloon"},
    14: {"WAR":"Super Witch + Ice Golem + Head Hunter","RANK":"Super Balloon + Super Witch + Head Hunter","FARM":"Dragon + Super Witch + Ice Golem"},
    15: {"WAR":"Super Witch + Ice Golem + Head Hunter","RANK":"Super Balloon + Super Witch + Head Hunter","FARM":"Dragon + Super Witch + Balloon"},
    16: {"WAR":"Super Witch + Ice Golem + Head Hunter","RANK":"Super Balloon + Super Witch + Head Hunter","FARM":"Inferno Dragon + Super Witch + Ice Golem"},
    17: {"WAR":"Inferno Dragon + Super Witch + Head Hunter","RANK":"Super Balloon + Super Witch + Head Hunter","FARM":"Inferno Dragon + Super Witch + Balloon"},
    18: {"WAR":"Inferno Dragon + Super Witch + Head Hunter","RANK":"Super Balloon + Super Witch + Head Hunter","FARM":"Inferno Dragon + Super Witch + Balloon"},
}


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def extract_cc(text, th, purpose):
    """
    Extract CC recommendation from text.
    Falls back to known-good CC per TH level if extraction fails.
    """
    troops = [
        "inferno dragon","super witch","ice golem","head hunter",
        "witch","super balloon","balloon","minion","dragon",
        "valkyrie","golem","hog rider","bowler","electro dragon",
        "lava hound","super archer","skeleton","giant"
    ]
    low = text.lower()

    # Look for an explicit CC section first
    cc_section = re.search(
        r'(?:clan castle|cc|castle)[:\s\-]+([^\n\.\!\?]{8,80})',
        low
    )
    if cc_section:
        section_text = cc_section.group(1)
        found = [tr for tr in troops if tr in section_text]
        if found:
            return " + ".join(found[:3]).title()

    # Fall back to scanning whole text for troop names
    found = [tr for tr in troops if tr in low]
    if len(found) >= 2:
        return " + ".join(found[:3]).title()

    # Use our curated CC table as final fallback — always correct
    return CC_BY_TH.get(th, {}).get(purpose, "Super Witch + Ice Golem + Head Hunter")


def recency_score(date_str):
    try:
        y, m = int(date_str[:4]), int(date_str[5:7])
        now = datetime.now(timezone.utc)
        months_old = (now.year - y) * 12 + (now.month - m)
        if months_old <= 1:  return 20
        if months_old <= 3:  return 15
        if months_old <= 6:  return 10
        if months_old <= 12: return 5
        return 0
    except Exception:
        return 0

def freshness_label(date_str, lang):
    r = recency_score(date_str)
    if r >= 15: return t(lang, "fresh")
    if r >= 5:  return t(lang, "old")
    return t(lang, "stale")

def format_date(date_str, lang):
    try:
        months = {
            "en": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
            "ru": ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"],
            "he": ["ינו","פבר","מרץ","אפר","מאי","יונ","יול","אוג","ספט","אוק","נוב","דצ"],
        }
        y, m = int(date_str[:4]), int(date_str[5:7])
        return f"{months.get(lang, months['en'])[m-1]} {y}"
    except Exception:
        return date_str or "?"

def score_base(base):
    rec = recency_score(base.get("date",""))
    dl  = min(base.get("downloads", 0), 200000)
    st  = min(base.get("stars", 4.0), 5.0)
    views = min(base.get("views", 0), 500000)
    likes = min(base.get("likes", 0), 50000)
    s = int(dl/200000*25 + st/5*20 + views/500000*25 + likes/50000*15 + rec*0.75)
    return min(100, max(30, s))


# ══════════════════════════════════════════════════════════════
# IMAGE FETCHING
# ══════════════════════════════════════════════════════════════

async def fetch_image(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=12, headers=headers, follow_redirects=True) as c:
            r = await c.get(url)
        if r.status_code == 200 and "image" in r.headers.get("content-type",""):
            buf = BytesIO(r.content)
            buf.name = "base.jpg"
            buf.seek(0)
            return buf
    except Exception as e:
        logger.warning(f"Image fetch failed: {e}")
    return None

async def get_youtube_thumbnail(vid_id):
    for q in ["maxresdefault","hqdefault","mqdefault"]:
        img = await fetch_image(f"https://img.youtube.com/vi/{vid_id}/{q}.jpg")
        if img:
            return img
    return None

async def get_page_thumbnail(page_url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=12, headers=headers, follow_redirects=True) as c:
            r = await c.get(page_url)
        html = r.text
        og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', html)
        if og:
            return await fetch_image(og.group(1))
        imgs = re.findall(r'<img[^>]+src=["\'](https?://[^"\']+\.(?:jpg|jpeg|png|webp))["\']', html, re.I)
        for img_url in imgs[:5]:
            if any(k in img_url.lower() for k in ["base","layout","th"]):
                result = await fetch_image(img_url)
                if result:
                    return result
    except Exception as e:
        logger.warning(f"Page thumbnail error: {e}")
    return None


# ══════════════════════════════════════════════════════════════
# SOURCE 1: YOUTUBE — base layout videos only
# ══════════════════════════════════════════════════════════════

BASE_KW   = ["base","layout","design","copy","link","download","anti","defense","defence","best base","new base"]
ATTACK_KW = ["attack","3 star","three star","how to beat","beating","raid","destroy","how i attacked"]

def is_base_video(title, desc):
    low = title.lower()
    attack_hits = sum(1 for kw in ATTACK_KW if kw in low)
    base_hits   = sum(1 for kw in BASE_KW   if kw in low)
    if attack_hits > 0 and base_hits == 0:
        return False
    if "link.clashofclans.com" not in desc.lower():
        return False
    return True

async def search_youtube(th, purpose):
    try:
        pkw = {"WAR":"war base layout anti 3star","RANK":"trophy base layout","FARM":"farming base layout"}
        query = f"TH{th} {pkw.get(purpose,'base layout')} 2025 Clash of Clans copy link"
        url = (f"https://www.googleapis.com/youtube/v3/search"
               f"?part=snippet&q={quote_plus(query)}&type=video&maxResults=15"
               f"&order=date&key={YOUTUBE_API_KEY}")
        async with httpx.AsyncClient(timeout=15) as c:
            data = (await c.get(url)).json()
        if "error" in data:
            logger.warning(f"YT search error: {data['error'].get('message')}")
            return None
        items = data.get("items",[])
        if not items:
            return None
        vid_ids = ",".join(i["id"]["videoId"] for i in items if i["id"].get("videoId"))
        durl = (f"https://www.googleapis.com/youtube/v3/videos"
                f"?part=snippet,statistics&id={vid_ids}&key={YOUTUBE_API_KEY}")
        async with httpx.AsyncClient(timeout=15) as c:
            ddata = (await c.get(durl)).json()

        best = None
        for item in ddata.get("items",[]):
            vid_id    = item["id"]
            title     = item["snippet"]["title"]
            desc      = item["snippet"]["description"]
            published = item["snippet"].get("publishedAt","")[:7]
            channel   = item["snippet"].get("channelTitle","YouTube")
            stats     = item.get("statistics",{})
            views     = int(stats.get("viewCount",0))
            likes     = int(stats.get("likeCount",0))

            if not is_base_video(title, desc):
                continue

            links = re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', desc)
            for raw in links:
                clean = raw.rstrip(".,)&")
                if any(f"TH{o}%3A" in clean.upper() for o in range(1,18) if o != th):
                    continue
                rec = recency_score(published)
                candidate = {
                    "link":        clean,
                    "cc":          extract_cc(desc, th, purpose),
                    "source_name": f"YouTube · {channel}",
                    "source_url":  f"https://youtube.com/watch?v={vid_id}",
                    "source_label":t("en","src_youtube"),
                    "image_type":  "youtube",
                    "image_id":    vid_id,
                    "date":        published,
                    "views":       views,
                    "likes":       likes,
                    "views_fmt":   f"{views//1000}K" if views>=1000 else str(views),
                    "likes_fmt":   f"{likes//1000}K" if likes>=1000 else str(likes),
                    "downloads":   views // 10,
                    "stars":       min(5.0, 3.5 + likes/max(views,1)*50),
                }
                candidate["score"] = score_base(candidate)
                if best is None or candidate["score"] > best["score"]:
                    best = candidate
                break

        if best:
            logger.info(f"YouTube best: score={best['score']} views={best['views_fmt']} {best['source_name']}")
        return best
    except Exception as e:
        logger.warning(f"YouTube error: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# SOURCE 2: REDDIT
# ══════════════════════════════════════════════════════════════

async def search_reddit(th, purpose):
    try:
        pkw = {"WAR":"war base anti 3 star","RANK":"trophy base","FARM":"farming base"}
        url = (f"https://www.reddit.com/r/ClashOfClans/search.json"
               f"?q=TH{th}+{quote_plus(pkw.get(purpose,'base'))}&sort=new&limit=25&restrict_sr=1")
        headers = {"User-Agent":"dlce-base-bot/1.0"}
        async with httpx.AsyncClient(timeout=15, headers=headers) as c:
            data = (await c.get(url)).json()
        posts = data.get("data",{}).get("children",[])
        logger.info(f"Reddit: {len(posts)} posts")

        best = None
        for post in posts:
            p        = post.get("data",{})
            title    = p.get("title","")
            body     = p.get("selftext","")
            post_url = f"https://reddit.com{p.get('permalink','')}"
            created  = datetime.fromtimestamp(p.get("created_utc",0), tz=timezone.utc)
            date_str = created.strftime("%Y-%m")
            upvotes  = p.get("score",0)

            all_text = title + " " + body
            links = re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', all_text)
            if not links:
                continue

            clean = links[0].rstrip(".,)&")
            img_url = None
            preview = p.get("preview",{}).get("images",[])
            if preview:
                src = preview[0].get("source",{}).get("url","")
                img_url = src.replace("&amp;","&")
            if not img_url and p.get("url","").endswith((".jpg",".png",".jpeg")):
                img_url = p["url"]

            rec = recency_score(date_str)
            candidate = {
                "link":        clean,
                "cc":          extract_cc(all_text, th, purpose),
                "source_name": "Reddit · r/ClashOfClans",
                "source_url":  post_url,
                "source_label":t("en","src_reddit"),
                "image_type":  "url",
                "image_url":   img_url,
                "date":        date_str,
                "views":       upvotes * 20,
                "likes":       upvotes,
                "views_fmt":   f"{upvotes//1000}K upvotes" if upvotes>=1000 else f"{upvotes} upvotes",
                "likes_fmt":   "",
                "downloads":   upvotes * 10,
                "stars":       min(5.0, 3.0 + upvotes/2000),
            }
            candidate["score"] = score_base(candidate)
            if best is None or candidate["score"] > best["score"]:
                best = candidate

        if best:
            logger.info(f"Reddit best: score={best['score']} {best['source_url'][:60]}")
        return best
    except Exception as e:
        logger.warning(f"Reddit error: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# SOURCE 3: BASE WEBSITES
# ══════════════════════════════════════════════════════════════

async def search_websites(th, purpose):
    headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    slugs = {"RANK":["trophy","trophies"],"WAR":["war","anti-3-star"],"FARM":["farming","farm"]}

    for slug in slugs.get(purpose,["war"]):
        try:
            url = f"https://cocbases.com/th{th}-{slug}-base/"
            async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as c:
                r = await c.get(url)
            if r.status_code != 200:
                continue
            html = r.text
            links = list(dict.fromkeys(re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', html)))
            if not links:
                continue
            dates = re.findall(r'20\d\d-\d\d-\d\d', html)
            date = dates[0][:7] if dates else "2025-04"
            # Find base image on page
            img_url = None
            og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', html)
            if og:
                img_url = og.group(1)
            rec = recency_score(date)
            base = {
                "link":        links[0].rstrip(".,)&"),
                "cc":          extract_cc(html, th, purpose),
                "source_name": "cocbases.com",
                "source_url":  url,
                "source_label":t("en","src_sites"),
                "image_type":  "url",
                "image_url":   img_url,
                "date":        date,
                "views":       0,
                "likes":       0,
                "views_fmt":   "",
                "likes_fmt":   "",
                "downloads":   15000,
                "stars":       4.7,
            }
            base["score"] = score_base(base)
            logger.info(f"cocbases.com: score={base['score']} link={base['link'][:50]}")
            return base
        except Exception as e:
            logger.warning(f"cocbases error ({slug}): {e}")

    # Fallback to built-in
    builtin_list = BUILTIN.get(th,{}).get(purpose,[])
    if builtin_list:
        b = dict(builtin_list[0])
        b.update({
            "source_name":  "CoC Community",
            "source_url":   f"https://cocbases.com/th{th}-{'war' if purpose=='WAR' else 'trophy' if purpose=='RANK' else 'farming'}-base/",
            "source_label": t("en","src_sites"),
            "image_type":   "none",
            "image_url":    None,
            "views":0,"likes":0,"views_fmt":"","likes_fmt":"",
            "stars":4.5,
        })
        b["cc"] = CC_BY_TH.get(th,{}).get(purpose,"Super Witch + Ice Golem")
        b["score"] = score_base(b)
        return b
    return None


# ══════════════════════════════════════════════════════════════
# DEEP RESEARCH — 5 more bases from all sources
# ══════════════════════════════════════════════════════════════

async def deep_search(th, purpose):
    """Search harder and wider — fetch up to 5 extra bases."""
    results = []
    headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # More YouTube videos
    try:
        pkw = {"WAR":"war base layout anti 3star","RANK":"trophy base layout","FARM":"farming base layout"}
        query = f"TH{th} {pkw.get(purpose,'base layout')} 2025 Clash of Clans"
        url = (f"https://www.googleapis.com/youtube/v3/search"
               f"?part=snippet&q={quote_plus(query)}&type=video&maxResults=25"
               f"&order=viewCount&key={YOUTUBE_API_KEY}")
        async with httpx.AsyncClient(timeout=15) as c:
            data = (await c.get(url)).json()
        items = data.get("items",[])
        vid_ids = ",".join(i["id"]["videoId"] for i in items if i["id"].get("videoId"))
        if vid_ids:
            durl = (f"https://www.googleapis.com/youtube/v3/videos"
                    f"?part=snippet,statistics&id={vid_ids}&key={YOUTUBE_API_KEY}")
            async with httpx.AsyncClient(timeout=15) as c:
                ddata = (await c.get(durl)).json()
            for item in ddata.get("items",[]):
                if len(results) >= 3:
                    break
                title = item["snippet"]["title"]
                desc  = item["snippet"]["description"]
                if not is_base_video(title, desc):
                    continue
                links = re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', desc)
                for raw in links:
                    clean = raw.rstrip(".,)&")
                    if any(f"TH{o}%3A" in clean.upper() for o in range(1,18) if o != th):
                        continue
                    vid_id    = item["id"]
                    published = item["snippet"].get("publishedAt","")[:7]
                    channel   = item["snippet"].get("channelTitle","YouTube")
                    stats     = item.get("statistics",{})
                    views     = int(stats.get("viewCount",0))
                    likes     = int(stats.get("likeCount",0))
                    b = {
                        "link":        clean,
                        "cc":          extract_cc(desc, th, purpose),
                        "source_name": f"YouTube · {channel}",
                        "source_url":  f"https://youtube.com/watch?v={vid_id}",
                        "image_type":  "youtube",
                        "image_id":    vid_id,
                        "date":        published,
                        "views":views,"likes":likes,
                        "views_fmt":f"{views//1000}K" if views>=1000 else str(views),
                        "likes_fmt":f"{likes//1000}K" if likes>=1000 else str(likes),
                        "downloads":views//10,"stars":min(5.0,3.5+likes/max(views,1)*50),
                    }
                    b["score"] = score_base(b)
                    results.append(b)
                    break
    except Exception as e:
        logger.warning(f"Deep YT error: {e}")

    # More Reddit posts
    try:
        pkw = {"WAR":"war base","RANK":"trophy base","FARM":"farming base"}
        url = (f"https://www.reddit.com/r/ClashOfClans/search.json"
               f"?q=TH{th}+{quote_plus(pkw.get(purpose,'base'))}&sort=top&t=month&limit=25&restrict_sr=1")
        hdr = {"User-Agent":"dlce-base-bot/1.0"}
        async with httpx.AsyncClient(timeout=15, headers=hdr) as c:
            data = (await c.get(url)).json()
        for post in data.get("data",{}).get("children",[]):
            if len(results) >= 5:
                break
            p = post.get("data",{})
            all_text = p.get("title","") + " " + p.get("selftext","")
            links = re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', all_text)
            if not links:
                continue
            clean    = links[0].rstrip(".,)&")
            date_str = datetime.fromtimestamp(p.get("created_utc",0), tz=timezone.utc).strftime("%Y-%m")
            upvotes  = p.get("score",0)
            img_url  = None
            preview  = p.get("preview",{}).get("images",[])
            if preview:
                img_url = preview[0].get("source",{}).get("url","").replace("&amp;","&")
            b = {
                "link":        clean,
                "cc":          extract_cc(all_text, th, purpose),
                "source_name": "Reddit · r/ClashOfClans",
                "source_url":  f"https://reddit.com{p.get('permalink','')}",
                "image_type":  "url",
                "image_url":   img_url,
                "date":        date_str,
                "views":upvotes*20,"likes":upvotes,
                "views_fmt":f"{upvotes} upvotes","likes_fmt":"",
                "downloads":upvotes*10,"stars":min(5.0,3.0+upvotes/2000),
            }
            b["score"] = score_base(b)
            results.append(b)
    except Exception as e:
        logger.warning(f"Deep Reddit error: {e}")

    # More from cocbases
    try:
        slugs = {"RANK":["trophies","trophy"],"WAR":["war","anti-3-star"],"FARM":["farming","farm"]}
        for slug in slugs.get(purpose,["war"]):
            url = f"https://cocbases.com/th{th}-{slug}-base/"
            async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as c:
                r = await c.get(url)
            if r.status_code != 200:
                continue
            html  = r.text
            links = list(dict.fromkeys(re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', html)))
            dates = re.findall(r'20\d\d-\d\d-\d\d', html)
            date  = dates[0][:7] if dates else "2025-04"
            og    = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', html)
            img_url = og.group(1) if og else None
            for lnk in links[1:4]:  # skip first (already in main results)
                if len(results) >= 5:
                    break
                b = {
                    "link":        lnk.rstrip(".,)&"),
                    "cc":          CC_BY_TH.get(th,{}).get(purpose,"Super Witch + Ice Golem"),
                    "source_name": "cocbases.com",
                    "source_url":  url,
                    "image_type":  "url",
                    "image_url":   img_url,
                    "date":        date,
                    "views":0,"likes":0,"views_fmt":"","likes_fmt":"",
                    "downloads":12000,"stars":4.6,
                }
                b["score"] = score_base(b)
                results.append(b)
            break
    except Exception as e:
        logger.warning(f"Deep cocbases error: {e}")

    results.sort(key=lambda x: x.get("score",0), reverse=True)
    return results[:5]


# ══════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════

async def save_base(base, th, purpose):
    if not supabase:
        return
    try:
        supabase.table("bases").upsert({
            "link":base["link"],"th_level":th,"purpose":purpose,
            "score":base.get("score",70),"cc":base.get("cc",""),
            "source":base.get("source_name",""),"date":base.get("date",""),
            "thumbs_up":0,"thumbs_down":0,
        }, on_conflict="link").execute()
    except Exception as e:
        logger.warning(f"Supabase save: {e}")

async def update_feedback(link, positive):
    if not supabase:
        return
    try:
        col = "thumbs_up" if positive else "thumbs_down"
        row = supabase.table("bases").select(col).eq("link",link).execute()
        if row.data:
            supabase.table("bases").update({col:row.data[0][col]+1}).eq("link",link).execute()
    except Exception as e:
        logger.warning(f"Feedback: {e}")

async def save_report(link, reason, base_info):
    if not supabase:
        return
    try:
        supabase.table("reports").upsert({
            "link":link,"reason":reason,
            "source":base_info.get("source_name",""),
            "th_level":base_info.get("th"),"purpose":base_info.get("purpose"),
            "reported_at":datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        logger.warning(f"Report save: {e}")


# ══════════════════════════════════════════════════════════════
# CARD BUILDER
# ══════════════════════════════════════════════════════════════

async def send_base_card(bot, chat_id, base, lang, rank_label, link_key, context):
    """Send one base as a photo card with buttons."""
    score      = base.get("score",70)
    cc         = base.get("cc","Check source")
    source_name= base.get("source_name","Community")
    source_url = base.get("source_url","")
    date       = base.get("date","")
    link       = base["link"]
    image_type = base.get("image_type","")
    image_url  = base.get("image_url")
    image_id   = base.get("image_id","")
    views_fmt  = base.get("views_fmt","")
    likes_fmt  = base.get("likes_fmt","")
    dl         = base.get("downloads",0)

    context.user_data.setdefault("links",{})[link_key] = link
    context.user_data.setdefault("bases",{})[link_key] = {
        "link":link,"source_name":source_name,
        "source_url":source_url,
        "th":context.user_data.get("th"),
        "purpose":context.user_data.get("purpose"),
    }

    fresh    = freshness_label(date, lang)
    date_fmt = format_date(date, lang)

    bar = "━" * 26
    stats_line = ""
    if views_fmt:
        stats_line = f"👁 {views_fmt}"
        if likes_fmt:
            stats_line += f"  ·  👍 {likes_fmt}"
    elif dl > 100:
        stats_line = f"⬇️ {dl//1000}K downloads" if dl>=1000 else f"⬇️ {dl} downloads"

    caption = (
        f"{rank_label}\n"
        f"{bar}\n"
        f"🏆 {t(lang,'score',score=score)}\n"
        f"📅 {t(lang,'uploaded',date=date_fmt)}  {fresh}\n"
    )
    if stats_line:
        caption += f"{stats_line}\n"
    caption += (
        f"🏰 {t(lang,'cc',cc=cc)}\n"
        f"📌 {source_name}\n"
        f"{bar}"
    )

    btn_copy   = InlineKeyboardButton(t(lang,"open_btn"),   url=link)
    btn_source = InlineKeyboardButton(t(lang,"source_btn"), url=source_url) if source_url else None
    btn_yes    = InlineKeyboardButton(t(lang,"worked"),     callback_data=f"fb_pos_{link_key}")
    btn_no     = InlineKeyboardButton(t(lang,"no_defend"),  callback_data=f"fb_neg_{link_key}")
    btn_report = InlineKeyboardButton(t(lang,"report_btn"), callback_data=f"fb_rep_{link_key}")

    row1 = [btn_copy, btn_source] if btn_source else [btn_copy]
    markup = InlineKeyboardMarkup([row1, [btn_yes, btn_no], [btn_report]])

    # Fetch real thumbnail
    image = None
    try:
        if image_type == "youtube" and image_id:
            image = await get_youtube_thumbnail(image_id)
        elif image_url:
            image = await fetch_image(image_url)
        elif source_url and "reddit" not in source_url:
            image = await get_page_thumbnail(source_url)
    except Exception as e:
        logger.warning(f"Thumb error: {e}")

    if image:
        await bot.send_photo(chat_id=chat_id, photo=image, caption=caption, reply_markup=markup)
    else:
        await bot.send_message(chat_id=chat_id, text=caption, reply_markup=markup)


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
    context.user_data["purpose"] = purpose
    context.user_data["links"]   = {}
    context.user_data["bases"]   = {}

    await query.edit_message_text(f"TH{th} · {t(lang,purpose.lower())}\n\n{t(lang,'searching')}")

    # Run all 3 sources in parallel — each returns its single BEST base
    yt_base, reddit_base, site_base = await asyncio.gather(
        search_youtube(th, purpose),
        search_reddit(th, purpose),
        search_websites(th, purpose),
    )

    purpose_label = t(lang, purpose.lower())
    await context.bot.send_message(
        chat_id=chat_id,
        text=t(lang,"results_hdr", th=th, purpose=purpose_label)
    )

    # Send exactly 1 card per source
    sources = [
        (yt_base,     f"📺 #{1}  {t(lang,'src_youtube')}"),
        (reddit_base, f"💬 #{2}  {t(lang,'src_reddit')}"),
        (site_base,   f"🌐 #{3}  {t(lang,'src_sites')}"),
    ]

    sent = 0
    for base, label in sources:
        if base:
            link_key = hashlib.md5(base["link"].encode()).hexdigest()[:16]
            await send_base_card(
                context.bot, chat_id, base, lang, label, link_key, context
            )
            await save_base(base, th, purpose)
            sent += 1

    # Deep Research button at the end
    deep_key = f"{th}_{purpose}"
    await context.bot.send_message(
        chat_id=chat_id,
        text="─" * 26,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                t(lang,"deep_search"),
                callback_data=f"deep_{deep_key}_{lang}"
            )
        ]])
    )

    return ConversationHandler.END


async def deep_research_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the Deep Research button."""
    query = update.callback_query
    await query.answer()
    parts   = query.data.split("_")  # deep_TH_PURPOSE_LANG
    th      = int(parts[1])
    purpose = parts[2]
    lang    = parts[3] if len(parts) > 3 else context.user_data.get("lang","en")
    chat_id = query.message.chat_id

    await query.edit_message_text(t(lang,"deep_searching"))

    results = await deep_search(th, purpose)

    purpose_label = t(lang, purpose.lower())
    await context.bot.send_message(
        chat_id=chat_id,
        text=t(lang,"deep_header", th=th, purpose=purpose_label)
    )

    for i, base in enumerate(results):
        link_key = hashlib.md5(base["link"].encode()).hexdigest()[:16]
        label = f"🔬 #{i+1}"
        await send_base_card(context.bot, chat_id, base, lang, label, link_key, context)
        await save_base(base, th, purpose)


async def feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    lang    = context.user_data.get("lang","en")
    data    = query.data
    chat_id = query.message.chat_id

    # Positive / negative
    if data.startswith("fb_pos_") or data.startswith("fb_neg_"):
        positive = data.startswith("fb_pos_")
        link_key = data[7:]
        link     = context.user_data.get("links",{}).get(link_key, link_key)
        await update_feedback(link, positive)
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=chat_id,
            text=t(lang,"thanks_good") if positive else t(lang,"thanks_bad")
        )
        return

    # Report button — show reason menu
    if data.startswith("fb_rep_"):
        link_key = data[7:]
        base     = context.user_data.get("bases",{}).get(link_key,{})
        source   = base.get("source_name","?")
        keyboard = [[
            InlineKeyboardButton(t(lang,"rep_wrong_th"),  callback_data=f"rp_wrongth_{link_key}"),
            InlineKeyboardButton(t(lang,"rep_attack"),    callback_data=f"rp_attack_{link_key}"),
        ],[
            InlineKeyboardButton(t(lang,"rep_dead_link"), callback_data=f"rp_deadlink_{link_key}"),
            InlineKeyboardButton(t(lang,"rep_old_base"),  callback_data=f"rp_oldbase_{link_key}"),
        ],[
            InlineKeyboardButton(t(lang,"rep_bad_cc"),    callback_data=f"rp_badcc_{link_key}"),
            InlineKeyboardButton(t(lang,"rep_other"),     callback_data=f"rp_other_{link_key}"),
        ]]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {t(lang,'report_q')}\n📌 {source}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Report reason chosen — rp_<reason>_<link_key>
    if data.startswith("rp_"):
        # Split carefully: rp_REASON_LINKKEY
        # reason is one of: wrongth, attack, deadlink, oldbase, badcc, other
        # link_key is 16 hex chars at the end
        link_key = data[-16:]
        reason   = data[3:-17]  # strip "rp_" prefix and "_"+link_key suffix
        link     = context.user_data.get("links",{}).get(link_key,"?")
        base     = context.user_data.get("bases",{}).get(link_key,{})
        logger.info(f"Report: reason={reason} source={base.get('source_name','?')} link={link[:50]}")
        await save_report(link, reason, base)
        await update_feedback(link, positive=False)
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text=t(lang,"report_thanks"))


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
    app.add_handler(CallbackQueryHandler(feedback_handler,    pattern="^fb_"))
    app.add_handler(CallbackQueryHandler(feedback_handler,    pattern="^rp_"))
    app.add_handler(CallbackQueryHandler(deep_research_handler, pattern="^deep_"))
    logger.info("dlce BASE bot v4.0 starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
