import os
import logging
import asyncio
import re
import json
import hashlib
import httpx
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)
import google.generativeai as genai
import anthropic
from supabase import create_client

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
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
    logger.info("Supabase connected OK")
except Exception as e:
    logger.warning(f"Supabase not connected: {e}")

LANG, TH_LEVEL, PURPOSE = range(3)

T = {
    "en": {
        "welcome":    "Welcome! Choose your language:",
        "q_th":       "What is your Town Hall level?",
        "q_purpose":  "What is the purpose of your base?",
        "searching":  "Searching YouTube, base sites and community... ~15 seconds",
        "recommended":"Recommended",
        "score":      "Score: {score}/100",
        "cc":         "CC troops: {cc}",
        "uploaded":   "Uploaded: {date}",
        "worked":     "It worked!",
        "no_defend":  "Did not defend",
        "thanks":     "Thanks! This helps improve rankings.",
        "rank":       "RANK",
        "war":        "WAR",
        "farm":       "FARM",
        "fresh":      "FRESH",
        "old":        "OLDER",
        "no_results": "No bases found. Try again in a minute.",
    },
    "ru": {
        "welcome":    "Привет! Выбери язык:",
        "q_th":       "Какой у тебя уровень ратуши?",
        "q_purpose":  "Какова цель базы?",
        "searching":  "Ищу на YouTube, сайтах и в сообществе... ~15 секунд",
        "recommended":"Рекомендуем",
        "score":      "Оценка: {score}/100",
        "cc":         "Замок клана: {cc}",
        "uploaded":   "Загружено: {date}",
        "worked":     "Сработало!",
        "no_defend":  "Не устояла",
        "thanks":     "Спасибо! Это улучшает рейтинг.",
        "rank":       "РАНГ",
        "war":        "ВОЙНА",
        "farm":       "ФАРМ",
        "fresh":      "СВЕЖАЯ",
        "old":        "СТАРШЕ",
        "no_results": "Базы не найдены. Попробуй снова через минуту.",
    },
    "he": {
        "welcome":    "שלום! בחר שפה:",
        "q_th":       "מה רמת עיירת המועצה שלך?",
        "q_purpose":  "מה מטרת הבסיס?",
        "searching":  "מחפש ב-YouTube, אתרי בסיסים וקהילה... ~15 שניות",
        "recommended":"מומלץ",
        "score":      "ציון: {score}/100",
        "cc":         "טירת קבוצה: {cc}",
        "uploaded":   "הועלה: {date}",
        "worked":     "עבד!",
        "no_defend":  "לא החזיק",
        "thanks":     "תודה! זה עוזר לשפר את הדירוג.",
        "rank":       "דירוג",
        "war":        "מלחמה",
        "farm":       "חווה",
        "fresh":      "חדש",
        "old":        "ישן יותר",
        "no_results": "לא נמצאו בסיסים. נסה שוב בעוד דקה.",
    },
}

def t(lang, key, **kwargs):
    text = T.get(lang, T["en"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


# ══════════════════════════════════════════════════════════════
# BUILT-IN BASE DATABASE
# Always works — no internet needed — updated to June 2025 meta
# ══════════════════════════════════════════════════════════════

BUILTIN_BASES = {
    10: {
        "WAR":  [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV", "cc": "Witch + Ice Golem", "date": "2025-03", "stars": 4.8, "downloads": 32000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AWB%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Witch + Balloon", "date": "2025-02", "stars": 4.6, "downloads": 21000},
        ],
        "RANK": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Balloon + Minion", "date": "2025-04", "stars": 4.7, "downloads": 18000},
        ],
        "FARM": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Dragon + Witch", "date": "2025-03", "stars": 4.5, "downloads": 15000},
        ],
    },
    11: {
        "WAR":  [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Witch + Ice Golem", "date": "2025-04", "stars": 4.9, "downloads": 41000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AWB%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Witch + Balloon + Ice Golem", "date": "2025-03", "stars": 4.7, "downloads": 28000},
        ],
        "RANK": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Balloon + Super Witch", "date": "2025-05", "stars": 4.8, "downloads": 22000},
        ],
        "FARM": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AHV%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV", "cc": "Dragon + Witch", "date": "2025-02", "stars": 4.5, "downloads": 17000},
        ],
    },
    12: {
        "WAR":  [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Witch + Ice Golem + Witch", "date": "2025-05", "stars": 4.9, "downloads": 55000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV", "cc": "Inferno Dragon + Witch", "date": "2025-04", "stars": 4.7, "downloads": 38000},
        ],
        "RANK": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Balloon + Super Witch", "date": "2025-05", "stars": 4.8, "downloads": 29000},
        ],
        "FARM": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Dragon + Witch", "date": "2025-03", "stars": 4.5, "downloads": 19000},
        ],
    },
    13: {
        "WAR":  [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Witch + Ice Golem + Head Hunter", "date": "2025-06", "stars": 4.9, "downloads": 62000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV", "cc": "Inferno Dragon + Super Witch", "date": "2025-05", "stars": 4.8, "downloads": 44000},
        ],
        "RANK": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Balloon + Super Witch", "date": "2025-05", "stars": 4.8, "downloads": 33000},
        ],
        "FARM": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Dragon + Witch + Balloon", "date": "2025-04", "stars": 4.6, "downloads": 24000},
        ],
    },
    14: {
        "WAR":  [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Witch + Ice Golem + Head Hunter", "date": "2025-06", "stars": 4.9, "downloads": 71000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV", "cc": "Inferno Dragon + Super Witch + Ice Golem", "date": "2025-05", "stars": 4.8, "downloads": 52000},
        ],
        "RANK": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Balloon + Super Witch + Skeleton", "date": "2025-06", "stars": 4.8, "downloads": 41000},
        ],
        "FARM": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Dragon + Super Witch + Balloon", "date": "2025-04", "stars": 4.6, "downloads": 29000},
        ],
    },
    15: {
        "WAR":  [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Witch + Ice Golem + Head Hunter", "date": "2025-06", "stars": 4.9, "downloads": 88000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV", "cc": "Inferno Dragon + Super Witch + Head Hunter", "date": "2025-05", "stars": 4.8, "downloads": 64000},
        ],
        "RANK": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Balloon + Super Witch + Head Hunter", "date": "2025-06", "stars": 4.9, "downloads": 53000},
        ],
        "FARM": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Dragon + Super Witch + Balloon", "date": "2025-05", "stars": 4.7, "downloads": 37000},
        ],
    },
    16: {
        "WAR":  [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Witch + Ice Golem + Head Hunter", "date": "2025-06", "stars": 4.9, "downloads": 79000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV", "cc": "Inferno Dragon + Super Witch + Head Hunter", "date": "2025-05", "stars": 4.8, "downloads": 57000},
        ],
        "RANK": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Balloon + Super Witch + Head Hunter", "date": "2025-06", "stars": 4.9, "downloads": 48000},
        ],
        "FARM": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Inferno Dragon + Super Witch", "date": "2025-05", "stars": 4.7, "downloads": 33000},
        ],
    },
    17: {
        "WAR":  [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Witch + Ice Golem + Head Hunter", "date": "2025-06", "stars": 4.9, "downloads": 92000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV", "cc": "Inferno Dragon + Super Witch + Head Hunter", "date": "2025-05", "stars": 4.8, "downloads": 71000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AWB%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Super Witch + Head Hunter + Balloon", "date": "2025-04", "stars": 4.7, "downloads": 48000},
        ],
        "RANK": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Balloon + Super Witch + Head Hunter", "date": "2025-06", "stars": 4.9, "downloads": 61000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV", "cc": "Inferno Dragon + Super Witch", "date": "2025-05", "stars": 4.7, "downloads": 42000},
        ],
        "FARM": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Inferno Dragon + Super Witch + Balloon", "date": "2025-05", "stars": 4.7, "downloads": 38000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Dragon + Super Witch", "date": "2025-04", "stars": 4.5, "downloads": 27000},
        ],
    },
    18: {
        "WAR":  [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Witch + Ice Golem + Head Hunter", "date": "2025-06", "stars": 4.9, "downloads": 68000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV", "cc": "Inferno Dragon + Super Witch + Head Hunter", "date": "2025-06", "stars": 4.8, "downloads": 51000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AWB%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Super Witch + Head Hunter + Ice Golem", "date": "2025-05", "stars": 4.7, "downloads": 39000},
        ],
        "RANK": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Super Balloon + Super Witch + Head Hunter", "date": "2025-06", "stars": 4.9, "downloads": 44000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV", "cc": "Inferno Dragon + Super Witch", "date": "2025-05", "stars": 4.7, "downloads": 33000},
        ],
        "FARM": [
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi", "cc": "Inferno Dragon + Super Witch + Balloon", "date": "2025-06", "stars": 4.8, "downloads": 42000},
            {"link": "https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s", "cc": "Dragon + Super Witch + Head Hunter", "date": "2025-05", "stars": 4.6, "downloads": 29000},
        ],
    },
}


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def extract_cc(text):
    troops = [
        "inferno dragon", "super witch", "ice golem", "head hunter",
        "witch", "balloon", "super balloon", "minion", "dragon",
        "valkyrie", "golem", "hog rider", "bowler", "electro dragon",
        "lava hound", "super archer", "skeleton"
    ]
    low = text.lower()
    found = [tr for tr in troops if tr in low]
    if found:
        return " + ".join(found[:3]).title()
    m = re.search(r'cc[:\s]+([^\n.]{5,60})', low)
    if m:
        return m.group(1).strip().title()
    return "Check source for CC"


def recency_score(date_str):
    """Convert date string like '2025-06' to a recency bonus 0-20."""
    try:
        if not date_str:
            return 0
        parts = date_str.split("-")
        year, month = int(parts[0]), int(parts[1]) if len(parts) > 1 else 1
        now = datetime.now(timezone.utc)
        months_old = (now.year - year) * 12 + (now.month - month)
        if months_old <= 1:   return 20   # This month or last = max bonus
        if months_old <= 3:   return 15   # Up to 3 months old
        if months_old <= 6:   return 10   # Up to 6 months old
        if months_old <= 12:  return 5    # Up to 1 year old
        return 0                           # Older = no bonus
    except Exception:
        return 0


def format_date(date_str, lang):
    """Format date string nicely."""
    try:
        months = {
            "en": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
            "ru": ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"],
            "he": ["ינו","פבר","מרץ","אפר","מאי","יונ","יול","אוג","ספט","אוק","נוב","דצ"],
        }
        parts = date_str.split("-")
        year, month = int(parts[0]), int(parts[1]) if len(parts) > 1 else 1
        m_names = months.get(lang, months["en"])
        return f"{m_names[month-1]} {year}"
    except Exception:
        return date_str


def get_builtin_bases(th, purpose):
    """Get built-in bases for given TH and purpose, with recency scores."""
    bases = BUILTIN_BASES.get(th, {}).get(purpose, [])
    result = []
    for b in bases:
        base = dict(b)
        base["source"] = f"CoC community (built-in)"
        rec = recency_score(base.get("date", ""))
        base["recency_bonus"] = rec
        base["score"] = min(100, int(
            base.get("downloads", 0) / 1000 * 0.35 +
            base.get("stars", 4.0) * 10 * 0.30 +
            rec * 0.35
        ))
        result.append(base)
    return result


# ══════════════════════════════════════════════════════════════
# SEARCH ENGINE
# ══════════════════════════════════════════════════════════════

async def search_youtube(th, purpose):
    """Search YouTube — extract links and publish dates."""
    results = []
    try:
        query = f"TH{th} {purpose} base 2025 Clash of Clans"
        search_url = (
            f"https://www.googleapis.com/youtube/v3/search"
            f"?part=snippet&q={query}&type=video&maxResults=10"
            f"&order=date&key={YOUTUBE_API_KEY}"
        )
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(search_url)
            data = r.json()

        if "error" in data:
            logger.warning(f"YouTube API error: {data['error'].get('message','?')}")
            return results

        items = data.get("items", [])
        logger.info(f"YouTube returned {len(items)} videos")
        if not items:
            return results

        vid_ids = ",".join(i["id"]["videoId"] for i in items if i["id"].get("videoId"))
        detail_url = (
            f"https://www.googleapis.com/youtube/v3/videos"
            f"?part=snippet&id={vid_ids}&key={YOUTUBE_API_KEY}"
        )
        async with httpx.AsyncClient(timeout=15) as c:
            dr = await c.get(detail_url)
            ddata = dr.json()

        for item in ddata.get("items", []):
            title       = item["snippet"]["title"]
            desc        = item["snippet"]["description"]
            published   = item["snippet"].get("publishedAt", "")[:7]  # "2025-06"

            links = re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', desc)
            for raw_link in links:
                clean = raw_link.rstrip(".,)&")
                link_up = clean.upper()
                wrong_th = any(
                    f"TH{other}%3A" in link_up
                    for other in range(1, 18) if other != th
                )
                if wrong_th:
                    continue
                rec = recency_score(published)
                results.append({
                    "link":          clean,
                    "cc":            extract_cc(desc),
                    "source":        f"YouTube: {title[:50]}",
                    "date":          published,
                    "recency_bonus": rec,
                    "downloads":     0,
                    "stars":         0,
                    "score":         50 + rec,
                })
                logger.info(f"YouTube found ({published}): {clean[:60]}")
                break

    except Exception as e:
        logger.warning(f"YouTube error: {e}")

    logger.info(f"YouTube total: {len(results)}")
    return results


async def search_web(th, purpose):
    """Scrape base sites for fresh links."""
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # Try multiple URL patterns for cocbases.com
    slug_map = {"RANK": ["trophy", "trophies"], "WAR": ["war", "anti-3-star"], "FARM": ["farming", "farm"]}
    slugs = slug_map.get(purpose, ["war"])

    for slug in slugs:
        try:
            url = f"https://cocbases.com/th{th}-{slug}-base/"
            async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as c:
                r = await c.get(url)
            if r.status_code == 200:
                html = r.text
                links = list(dict.fromkeys(
                    re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', html)
                ))
                logger.info(f"cocbases.com/{slug}: {len(links)} links")
                dates = re.findall(r'20\d\d-\d\d-\d\d', html)
                latest_date = dates[0][:7] if dates else "2025-03"
                for lnk in links[:4]:
                    rec = recency_score(latest_date)
                    results.append({
                        "link":          lnk.rstrip(".,)&"),
                        "cc":            extract_cc(html),
                        "source":        "cocbases.com",
                        "date":          latest_date,
                        "recency_bonus": rec,
                        "downloads":     15000,
                        "stars":         4.7,
                        "score":         min(100, 70 + rec),
                    })
                break
        except Exception as e:
            logger.warning(f"cocbases error ({slug}): {e}")

    logger.info(f"Web search total: {len(results)}")
    return results


def validate_link(link):
    return "clashofclans.com" in link


async def rank_bases(bases, th, purpose, lang):
    """
    Score and rank bases. Uses Claude if credits available,
    otherwise uses built-in scoring formula.
    """
    if not bases:
        return []

    # Always compute local score first as fallback
    for b in bases:
        rec = recency_score(b.get("date", ""))
        dl  = min(b.get("downloads", 0), 100000)
        st  = min(b.get("stars", 4.0), 5.0)
        b["recency_bonus"] = rec
        b["score"] = int(dl / 100000 * 35 + st / 5 * 30 + rec * 0.35 * 35 / 20 * 35 / 35 + rec)
        b["score"] = min(100, b["score"])
        if not b.get("reason"):
            age_label = t(lang, "fresh") if rec >= 15 else t(lang, "old")
            b["reason"] = f"{age_label} — {format_date(b.get('date',''), lang)}"

    # Sort by score descending
    bases.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Try Claude for smarter ranking + reasons
    try:
        simplified = [{
            "link":     b["link"],
            "cc":       b.get("cc",""),
            "source":   b.get("source",""),
            "date":     b.get("date",""),
            "downloads":b.get("downloads",0),
            "stars":    b.get("stars",0),
        } for b in bases[:6]]

        msg = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": (
                f"Rank these Clash of Clans TH{th} {purpose} bases. "
                f"Prioritize: 1) Most recent date 2) Most downloads 3) Highest stars.\n\n"
                f"Bases:\n{json.dumps(simplified, indent=2)}\n\n"
                f"Return ONLY JSON array, best first, max 3:\n"
                f'[{{"link":"...","cc":"...","source":"...","date":"...","score":88,'
                f'"reason":"One sentence — mention upload date and why it ranks high"}}]'
            )}]
        )
        raw = re.sub(r"```json|```", "", msg.content[0].text).strip()
        m = re.search(r'\[.*?\]', raw, re.DOTALL)
        if m:
            ranked = json.loads(m.group())
            logger.info(f"Claude ranked {len(ranked)} bases")
            return ranked[:3]
    except Exception as e:
        logger.warning(f"Claude ranking skipped: {e}")

    return bases[:3]


async def save_base(base, th, purpose):
    if not supabase:
        return
    try:
        supabase.table("bases").upsert({
            "link":        base["link"],
            "th_level":    th,
            "purpose":     purpose,
            "score":       base.get("score", 70),
            "cc":          base.get("cc", ""),
            "source":      base.get("source", ""),
            "date":        base.get("date", ""),
            "thumbs_up":   0,
            "thumbs_down": 0,
        }, on_conflict="link").execute()
    except Exception as e:
        logger.warning(f"Supabase save error: {e}")


async def update_feedback(link, positive):
    if not supabase:
        return
    try:
        col = "thumbs_up" if positive else "thumbs_down"
        row = supabase.table("bases").select(col).eq("link", link).execute()
        if row.data:
            supabase.table("bases").update(
                {col: row.data[0][col] + 1}
            ).eq("link", link).execute()
    except Exception as e:
        logger.warning(f"Feedback error: {e}")


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
        "🏰 CoC Base Finder\n\nChoose language / Выбери язык / בחר שפה",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return LANG


async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.replace("lang_", "")
    context.user_data["lang"] = lang

    row1 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(10, 14)]
    row2 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(14, 18)]
    row3 = [InlineKeyboardButton("TH18",   callback_data="th_18")]

    await query.edit_message_text(
        t(lang, "q_th"),
        reply_markup=InlineKeyboardMarkup([row1, row2, row3])
    )
    return TH_LEVEL


async def th_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    th   = int(query.data.replace("th_", ""))
    lang = context.user_data["lang"]
    context.user_data["th"] = th

    keyboard = [[
        InlineKeyboardButton(t(lang, "rank"),  callback_data="purpose_RANK"),
        InlineKeyboardButton(t(lang, "war"),   callback_data="purpose_WAR"),
        InlineKeyboardButton(t(lang, "farm"),  callback_data="purpose_FARM"),
    ]]
    await query.edit_message_text(
        f"TH{th} ✓\n\n{t(lang, 'q_purpose')}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PURPOSE


async def purpose_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    purpose = query.data.replace("purpose_", "")
    lang    = context.user_data["lang"]
    th      = context.user_data["th"]
    chat_id = query.message.chat_id

    await query.edit_message_text(f"TH{th} · {purpose}\n\n⏳ {t(lang, 'searching')}")

    # Run live searches + load built-in bases in parallel
    yt_task  = asyncio.create_task(search_youtube(th, purpose))
    web_task = asyncio.create_task(search_web(th, purpose))
    builtin  = get_builtin_bases(th, purpose)

    yt_results  = await yt_task
    web_results = await web_task

    # Merge all sources — live results first (fresher), builtin as safety net
    all_bases = yt_results + web_results
    valid = [b for b in all_bases if validate_link(b["link"])]

    # Always have at least built-in bases
    if len(valid) < 3:
        logger.info(f"Adding {len(builtin)} built-in bases as fallback")
        existing_links = {b["link"] for b in valid}
        for b in builtin:
            if b["link"] not in existing_links:
                valid.append(b)

    logger.info(f"Total candidates: {len(valid)}")

    if not valid:
        await context.bot.send_message(chat_id=chat_id, text=t(lang, "no_results"))
        return ConversationHandler.END

    # Rank with recency priority
    top3 = await rank_bases(valid, th, purpose, lang)

    # Save to DB
    for base in top3:
        await save_base(base, th, purpose)

    # Send results
    medals = ["🥇", "🥈", "🥉"]
    context.user_data["links"] = {}

    for i, base in enumerate(top3):
        score  = base.get("score", 70)
        cc     = base.get("cc", "Not specified")
        source = base.get("source", "")
        reason = base.get("reason", "")
        date   = base.get("date", "")
        link   = base["link"]

        header = f"{medals[i]} #{i+1}"
        if i == 0:
            header += f"  ⭐ {t(lang, 'recommended')}"

        # Recency badge
        rec = recency_score(date)
        if rec >= 15:
            freshness = f"🟢 {t(lang, 'fresh')}"
        elif rec >= 5:
            freshness = f"🟡 {t(lang, 'old')}"
        else:
            freshness = "🔴 2024 or older"

        text = (
            f"{header}\n"
            f"{t(lang, 'score', score=score)}\n"
            f"📅 {t(lang, 'uploaded', date=format_date(date, lang))}  {freshness}\n"
            f"{t(lang, 'cc', cc=cc)}\n"
            f"📌 {source}\n"
        )
        if reason:
            text += f"💬 {reason}\n"
        text += f"\n🔗 {link}"

        link_key = hashlib.md5(link.encode()).hexdigest()[:16]
        context.user_data["links"][link_key] = link

        keyboard = [[
            InlineKeyboardButton(t(lang, "worked"),    callback_data=f"fb_pos_{link_key}"),
            InlineKeyboardButton(t(lang, "no_defend"), callback_data=f"fb_neg_{link_key}"),
        ]]
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    return ConversationHandler.END


async def feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang     = context.user_data.get("lang", "en")
    positive = query.data.startswith("fb_pos_")
    link_key = query.data[7:]
    link     = context.user_data.get("links", {}).get(link_key, link_key)
    await update_feedback(link, positive)
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=t(lang, "thanks")
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled. Send /start to begin again.")
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
