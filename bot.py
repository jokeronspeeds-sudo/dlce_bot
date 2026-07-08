# dlce BASE bot v7.3
import os, logging, asyncio, re, json, hashlib, httpx
from io import BytesIO
from datetime import datetime, timezone
from urllib.parse import quote_plus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters
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
ADMIN_ID        = int(os.environ.get("ADMIN_ID", "0"))  # your Telegram user ID (kept for display/back-compat)
# ADMIN_ID (or ADMIN_IDS) may be a single ID or a comma-separated list, so more
# than one clan leader/co-leader can reach the admin panel. If nothing valid is
# configured this is an empty set, which means the panel denies EVERYONE by
# default (previous behaviour silently let everyone in when unset — see admin_panel).
ADMIN_IDS = {
    int(x) for x in
    (os.environ.get("ADMIN_IDS") or os.environ.get("ADMIN_ID") or "").replace(" ", "").split(",")
    if x.strip().lstrip("-").isdigit()
}

genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-2.0-flash")
claude = anthropic.AsyncAnthropic(api_key=CLAUDE_API_KEY)

supabase = None
try:
    if SUPABASE_URL and SUPABASE_KEY and len(SUPABASE_KEY) > 20:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase connected OK")
    else:
        logger.warning("Supabase: missing or short key — skipping DB")
except Exception as e:
    logger.warning(f"Supabase skipped (bot works without it): {e}")

LANG, CATEGORY, TH_LEVEL, PURPOSE, GUIDE_TOPIC, GUIDE_ATTACK_TH = range(6)

# ══════════════════════════════════════════════════════════════
# LINK VALIDATION — base vs troops
# ══════════════════════════════════════════════════════════════
# CoC layout types: WB=War Base, HV=Home Village (trophy/farm)
# Troop/spell links contain: UT=Unit, SP=Spell, HE=Hero, PE=Pet
BASE_LAYOUT_TYPES = ["WB", "HV", "BB", "CW"]  # valid base types
TROOP_LINK_TYPES  = ["UT", "SP", "HE", "PE", "TH"]  # troop/spell/hero links

def is_base_link(link: str) -> bool:
    """Return True only if the link points to a base layout, not troops/spells."""
    if "link.clashofclans.com" not in link:
        return False
    # Check URL for layout type codes
    for bt in BASE_LAYOUT_TYPES:
        if f"%3A{bt}%3A" in link or f":{bt}:" in link:
            return True
    # If it has troop codes, reject
    for tt in TROOP_LINK_TYPES:
        if f"%3A{tt}%3A" in link or f":{tt}:" in link:
            return False
    # If no type code found but it's a clashofclans link, trust it
    if "OpenLayout" in link:
        return True
    return False


# ══════════════════════════════════════════════════════════════
# TRANSLATIONS
# ══════════════════════════════════════════════════════════════
T = {
    "en": {
        "welcome":        "🎲 *dlce BASE bot*\n\nFind the best CoC bases from YouTube, Reddit & base sites — with real stats & CC troops.\n\nChoose language:",
        "q_category":     "🎯 What are you looking for?",
        "cat_bases":      "🏰 Base Finder",
        "cat_guides":     "📖 Guides",
        "q_th":           "🏰 Select Town Hall level:",
        "q_purpose":      "🎯 Purpose?",
        "q_guide_topic":  "📖 Choose a topic:",
        "guide_attack":   "⚔️ Attack Guide",
        "guide_equip":    "🎒 Equipment",
        "guide_web":      "🌐 Web Services",
        "guide_bh":       "🔨 Builder Hall",
        "guide_q_th":     "⚔️ Choose TH level for attack guide:",
        "watch_video":    "▶️ Watch Video",
        "back_main":      "🏠 Main Menu",
        "searching":      "🔍 Searching all sources...",
        "dm_notice":      "📩 Results sent to your DM!",
        "dm_intro":       "🎲 *dlce BASE bot*\nTH{th} · {purpose}\n",
        "recommended":    "⭐ RECOMMENDED",
        "score":          "{score}/100",
        "cc":             "CC: {cc}",
        "open_btn":       "🏰 Copy Base",
        "source_btn":     "📌 Source",
        "worked":         "✅ Works",
        "no_defend":      "❌ Failed",
        "report_btn":     "⚠️ Report",
        "thanks_good":    "🎉 Score +1. Thanks!",
        "thanks_bad":     "📉 Score -1. Thanks!",
        "report_q":       "What\'s wrong?",
        "rep_wrong_th":   "❌ Wrong TH",
        "rep_attack":     "⚔️ Attack video",
        "rep_dead_link":  "🔗 Broken link",
        "rep_old_base":   "📅 Too old",
        "rep_bad_cc":     "🏰 Wrong CC",
        "rep_other":      "🤷 Other",
        "report_thanks":  "✅ Reported! Bot learns.",
        "deep_btn":       "🔬 Deep Research (+5 bases)",
        "deep_header":    "🔬 Deep Research — TH{th} {purpose}",
        "deep_searching": "🔬 Running deep research (~30s)...",
        "rank":           "🏆 RANK",
        "war":            "⚔️ WAR",
        "farm":           "💰 FARM",
        "fresh":          "🟢",
        "older":          "🟡",
        "stale":          "🔴",
        "no_results":     "😕 No bases found. Try again.",
        "src_yt":         "📺 YouTube",
        "src_reddit":     "💬 Reddit",
        "src_web":        "🌐 Web",
        "group_msg":      "👋 Hi! I work best in DMs.\nTap below to get results privately:",
        "open_dm":        "💬 Open DM",
    },
    "ru": {
        "welcome":        "🎲 *dlce BASE bot*\n\nНахожу лучшие базы с YouTube, Reddit и сайтов — с реальной статистикой и войсками ЗК.\n\nВыбери язык:",
        "q_category":     "🎯 Что ищешь?",
        "cat_bases":      "🏰 Поиск базы",
        "cat_guides":     "📖 Гайды",
        "q_th":           "🏰 Уровень ратуши:",
        "q_purpose":      "🎯 Цель базы?",
        "q_guide_topic":  "📖 Выбери тему:",
        "guide_attack":   "⚔️ Гайд по атаке",
        "guide_equip":    "🎒 Снаряжение",
        "guide_web":      "🌐 Веб-сервисы",
        "guide_bh":       "🔨 Билдер Холл",
        "guide_q_th":     "⚔️ Выбери ТХ для гайда по атаке:",
        "watch_video":    "▶️ Смотреть видео",
        "back_main":      "🏠 Главное меню",
        "searching":      "🔍 Ищу во всех источниках...",
        "dm_notice":      "📩 Результаты отправлены в личку!",
        "dm_intro":       "🎲 *dlce BASE bot*\nТХ{th} · {purpose}\n",
        "recommended":    "⭐ РЕКОМЕНДУЕМ",
        "score":          "{score}/100",
        "cc":             "ЗК: {cc}",
        "open_btn":       "🏰 Скопировать базу",
        "source_btn":     "📌 Источник",
        "worked":         "✅ Устояла",
        "no_defend":      "❌ Не устояла",
        "report_btn":     "⚠️ Репорт",
        "thanks_good":    "🎉 Оценка +1. Спасибо!",
        "thanks_bad":     "📉 Оценка -1. Спасибо!",
        "report_q":       "Что не так?",
        "rep_wrong_th":   "❌ Не тот уровень",
        "rep_attack":     "⚔️ Видео атаки",
        "rep_dead_link":  "🔗 Ссылка сломана",
        "rep_old_base":   "📅 Слишком старая",
        "rep_bad_cc":     "🏰 Неверные войска",
        "rep_other":      "🤷 Другое",
        "report_thanks":  "✅ Репорт принят! Бот учтёт.",
        "deep_btn":       "🔬 Глубокий поиск (+5 баз)",
        "deep_header":    "🔬 Глубокий поиск — ТХ{th} {purpose}",
        "deep_searching": "🔬 Глубокий поиск (~30 сек)...",
        "rank":           "🏆 РАНГ",
        "war":            "⚔️ ВОЙНА",
        "farm":           "💰 ФАРМ",
        "fresh":          "🟢",
        "older":          "🟡",
        "stale":          "🔴",
        "no_results":     "😕 Базы не найдены. Попробуй позже.",
        "src_yt":         "📺 YouTube",
        "src_reddit":     "💬 Reddit",
        "src_web":        "🌐 Сайты",
        "group_msg":      "👋 Привет! Я лучше работаю в личке.\nНажми кнопку ниже:",
        "open_dm":        "💬 Написать в личку",
    },
    "he": {
        "welcome":        "🎲 *dlce BASE bot*\n\nמוצא בסיסים מ-YouTube, Reddit ואתרים — עם סטטיסטיקות וחיילי טירה.\n\nבחר שפה:",
        "q_category":     "🎯 מה אתה מחפש?",
        "cat_bases":      "🏰 מוצא בסיסים",
        "cat_guides":     "📖 מדריכים",
        "q_th":           "🏰 רמת עיירת מועצה:",
        "q_purpose":      "🎯 מטרת הבסיס?",
        "q_guide_topic":  "📖 בחר נושא:",
        "guide_attack":   "⚔️ מדריך התקפה",
        "guide_equip":    "🎒 ציוד",
        "guide_web":      "🌐 שירותי אינטרנט",
        "guide_bh":       "🔨 Builder Hall",
        "guide_q_th":     "⚔️ בחר רמת TH למדריך:",
        "watch_video":    "▶️ צפה בסרטון",
        "back_main":      "🏠 תפריט ראשי",
        "searching":      "🔍 מחפש בכל המקורות...",
        "dm_notice":      "📩 התוצאות נשלחו בפרטי!",
        "dm_intro":       "🎲 *dlce BASE bot*\nTH{th} · {purpose}\n",
        "recommended":    "⭐ מומלץ",
        "score":          "{score}/100",
        "cc":             "טירה: {cc}",
        "open_btn":       "🏰 העתק בסיס",
        "source_btn":     "📌 מקור",
        "worked":         "✅ עמד",
        "no_defend":      "❌ נפל",
        "report_btn":     "⚠️ דווח",
        "thanks_good":    "🎉 ציון +1. תודה!",
        "thanks_bad":     "📉 ציון -1. תודה!",
        "report_q":       "מה הבעיה?",
        "rep_wrong_th":   "❌ רמה שגויה",
        "rep_attack":     "⚔️ סרטון התקפה",
        "rep_dead_link":  "🔗 קישור שבור",
        "rep_old_base":   "📅 ישן מדי",
        "rep_bad_cc":     "🏰 טירה שגויה",
        "rep_other":      "🤷 אחר",
        "report_thanks":  "✅ דווח! הבוט לומד.",
        "deep_btn":       "🔬 מחקר מעמיק (+5 בסיסים)",
        "deep_header":    "🔬 מחקר מעמיק — TH{th} {purpose}",
        "deep_searching": "🔬 מחקר מעמיק (~30 שניות)...",
        "rank":           "🏆 דירוג",
        "war":            "⚔️ מלחמה",
        "farm":           "💰 חווה",
        "fresh":          "🟢",
        "older":          "🟡",
        "stale":          "🔴",
        "no_results":     "😕 לא נמצאו בסיסים.",
        "src_yt":         "📺 YouTube",
        "src_reddit":     "💬 Reddit",
        "src_web":        "🌐 אתרים",
        "group_msg":      "👋 שלום! אני עובד טוב יותר בפרטי.\nלחץ על הכפתור:",
        "open_dm":        "💬 פתח צ\'אט פרטי",
    },
}


def t(lang, key, **kwargs):
    text = T.get(lang, T["en"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


# ══════════════════════════════════════════════════════════════
# CC TABLE — always correct per TH + purpose
# ══════════════════════════════════════════════════════════════
CC_TABLE = {
    10: {"WAR":"Witch + Ice Golem + Balloon",                         "RANK":"Super Balloon + Minion + Witch",              "FARM":"Dragon + Witch + Balloon"},
    11: {"WAR":"Super Witch + Ice Golem + Head Hunter",               "RANK":"Super Balloon + Super Witch + Minion",        "FARM":"Dragon + Witch + Ice Golem"},
    12: {"WAR":"Super Witch + Ice Golem + Witch",                     "RANK":"Super Balloon + Super Witch + Head Hunter",   "FARM":"Dragon + Witch + Balloon"},
    13: {"WAR":"Super Witch + Ice Golem + Head Hunter",               "RANK":"Super Balloon + Super Witch + Head Hunter",   "FARM":"Dragon + Witch + Balloon"},
    14: {"WAR":"Super Witch + Ice Golem + Head Hunter",               "RANK":"Super Balloon + Super Witch + Head Hunter",   "FARM":"Dragon + Super Witch + Ice Golem"},
    15: {"WAR":"Inferno Dragon + Super Witch + Head Hunter",          "RANK":"Super Balloon + Super Witch + Head Hunter",   "FARM":"Dragon + Super Witch + Balloon"},
    16: {"WAR":"Inferno Dragon + Super Witch + Head Hunter",          "RANK":"Super Balloon + Super Witch + Head Hunter",   "FARM":"Inferno Dragon + Super Witch + Ice Golem"},
    17: {"WAR":"Inferno Dragon + Super Witch + Head Hunter + Golem",  "RANK":"Super Balloon + Inferno Dragon + Head Hunter","FARM":"Inferno Dragon + Super Witch + Balloon"},
    18: {"WAR":"Inferno Dragon + Super Witch + Head Hunter + Golem",  "RANK":"Super Balloon + Inferno Dragon + Head Hunter","FARM":"Inferno Dragon + Super Witch + Balloon"},
}

def get_cc(th, purpose, extracted=""):
    """Use extracted CC only if it contains 2+ real troop names. Otherwise use table."""
    troops = ["inferno dragon","super witch","ice golem","head hunter","witch",
              "super balloon","balloon","dragon","golem","bowler","valkyrie",
              "hog rider","electro dragon","lava hound","minion","skeleton"]
    low = extracted.lower()
    found = [tr for tr in troops if tr in low]
    if len(found) >= 2:
        return " + ".join(found[:3]).title()
    return CC_TABLE.get(th, {}).get(purpose, "Super Witch + Ice Golem + Head Hunter")


# ══════════════════════════════════════════════════════════════
# RATE LIMITING — protects the shared YouTube/Gemini/Claude quota
# from a single user spamming searches or /ask
# ══════════════════════════════════════════════════════════════
RATE_LIMIT_SECONDS = 20
_last_action_ts: dict[int, float] = {}

def check_rate_limit(user_id: int) -> bool:
    """Return True if user_id may proceed, False if still cooling down."""
    now = datetime.now(timezone.utc).timestamp()
    last = _last_action_ts.get(user_id, 0)
    if now - last < RATE_LIMIT_SECONDS:
        return False
    _last_action_ts[user_id] = now
    return True


# ══════════════════════════════════════════════════════════════
# SEARCH CACHE — short-lived cache keyed by (th, purpose) so repeat
# requests don't re-burn YouTube's quota-limited search API or
# re-run Gemini comment grading on the same videos
# ══════════════════════════════════════════════════════════════
SEARCH_CACHE_TTL = 900  # 15 minutes
_search_cache: dict[tuple, tuple[float, tuple]] = {}

async def cached_search(th, purpose):
    key = (th, purpose)
    now = datetime.now(timezone.utc).timestamp()
    cached = _search_cache.get(key)
    if cached and now - cached[0] < SEARCH_CACHE_TTL:
        return cached[1]
    result = await asyncio.gather(
        search_youtube(th, purpose),
        search_reddit(th, purpose),
        search_websites(th, purpose),
    )
    _search_cache[key] = (now, result)
    return result


# ══════════════════════════════════════════════════════════════
# BUILT-IN BASE DATABASE — guaranteed fallback, always works
# ══════════════════════════════════════════════════════════════
BUILTIN = {
    10: {
        "WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","date":"2025-03","downloads":32000,"stars":4.8}],
        "RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","date":"2025-04","downloads":18000,"stars":4.7}],
        "FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH10%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-03","downloads":15000,"stars":4.5}],
    },
    11: {
        "WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-05","downloads":41000,"stars":4.9}],
        "RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-05","downloads":22000,"stars":4.8}],
        "FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH11%3AHV%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","date":"2025-02","downloads":17000,"stars":4.5}],
    },
    12: {
        "WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-05","downloads":55000,"stars":4.9}],
        "RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-05","downloads":29000,"stars":4.8}],
        "FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH12%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","date":"2025-03","downloads":19000,"stars":4.5}],
    },
    13: {
        "WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-06","downloads":62000,"stars":4.9}],
        "RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-05","downloads":33000,"stars":4.8}],
        "FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH13%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","date":"2025-04","downloads":24000,"stars":4.6}],
    },
    14: {
        "WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-06","downloads":71000,"stars":4.9}],
        "RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-06","downloads":41000,"stars":4.8}],
        "FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH14%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","date":"2025-04","downloads":29000,"stars":4.6}],
    },
    15: {
        "WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-06","downloads":88000,"stars":4.9},
                {"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","date":"2025-05","downloads":64000,"stars":4.8}],
        "RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-06","downloads":53000,"stars":4.9}],
        "FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH15%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","date":"2025-05","downloads":37000,"stars":4.7}],
    },
    16: {
        "WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-06","downloads":79000,"stars":4.9},
                {"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","date":"2025-05","downloads":57000,"stars":4.8}],
        "RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-06","downloads":48000,"stars":4.9}],
        "FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH16%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","date":"2025-05","downloads":33000,"stars":4.7}],
    },
    17: {
        "WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-06","downloads":92000,"stars":4.9},
                {"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","date":"2025-05","downloads":71000,"stars":4.8},
                {"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AWB%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","date":"2025-04","downloads":48000,"stars":4.7}],
        "RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-06","downloads":61000,"stars":4.9},
                {"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","date":"2025-05","downloads":42000,"stars":4.7}],
        "FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","date":"2025-05","downloads":38000,"stars":4.7},
                {"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH17%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-04","downloads":27000,"stars":4.5}],
    },
    18: {
        "WAR": [{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AWB%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-06","downloads":68000,"stars":4.9},
                {"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AWB%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","date":"2025-06","downloads":51000,"stars":4.8},
                {"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AWB%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","date":"2025-05","downloads":39000,"stars":4.7}],
        "RANK":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-06","downloads":44000,"stars":4.9},
                {"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIrqQ4h6wq_WqV8B8XZRGKV","date":"2025-05","downloads":33000,"stars":4.7}],
        "FARM":[{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIrMzmMAfRXDk0FNdKGxhPi","date":"2025-06","downloads":42000,"stars":4.8},
                {"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH18%3AHV%3AAAAAGQAAAAIs9CFgf7_aqsLumPPDHJ5s","date":"2025-05","downloads":29000,"stars":4.6}],
    },
}

# ══════════════════════════════════════════════════════════════
# SCORING — proper weighted formula
# ══════════════════════════════════════════════════════════════
def calc_score(base: dict) -> int:
    """
    Score formula v2 — designed to surface actually-defending bases.

    Points (100 total):
      Recency          30  — CoC meta changes every update; old = useless
      Like/view ratio  20  — high ratio = community actually loves it (not just viral)
      Raw engagement   15  — views + upvotes (reach)
      Comment grade    15  — AI sentiment from real player comments (0-15)
      User feedback    10  — our own thumbs up/down from bot users
      Source quality   10  — cocbases/top-creator > random YouTube > unknown

    Why ratio matters: a 50K-view video with 5K likes beats a 1M-view clickbait
    with 10K likes. The ratio filters out attack-strategy content.
    """
    now = datetime.now(timezone.utc)

    # Recency (30 pts)
    try:
        y, m = int(base.get("date","2024-01")[:4]), int(base.get("date","2024-01")[5:7])
        mo = (now.year - y)*12 + (now.month - m)
        if mo <= 1:  rec = 30
        elif mo <= 3: rec = 25
        elif mo <= 6: rec = 18
        elif mo <= 12: rec = 8
        else: rec = 0
    except Exception:
        rec = 0

    # Like-to-view ratio (20 pts) — key signal that content is genuinely useful
    views = max(base.get("views", 0), 1)
    likes = base.get("likes", 0)
    ratio = likes / views
    if ratio >= 0.08:   ratio_pts = 20   # 8%+ = exceptional
    elif ratio >= 0.05: ratio_pts = 15
    elif ratio >= 0.03: ratio_pts = 10
    elif ratio >= 0.01: ratio_pts = 5
    else:               ratio_pts = 0

    # Raw engagement (15 pts)
    raw_views = min(base.get("views", 0), 500_000)
    raw_ups   = min(base.get("likes", 0), 50_000)
    dl        = min(base.get("downloads", 0), 200_000)
    eng_pts = int((raw_views/500_000*8) + (raw_ups/50_000*4) + (dl/200_000*3))

    # Comment grade from AI sentiment analysis (15 pts) — set by search function
    comment_pts = min(15, base.get("comment_grade", 0))

    # User feedback from our own bot (10 pts)
    ups   = base.get("thumbs_up", 0)
    downs = base.get("thumbs_down", 0)
    total_fb = ups + downs
    if total_fb > 0:
        fb_ratio = ups / total_fb
        fb_pts = int(fb_ratio * 10)
    else:
        fb_pts = 5  # neutral default

    # Source quality (10 pts)
    src = base.get("source_name", "").lower()
    if any(k in src for k in ["cocbases","clashtrack","clashbases"]):
        src_pts = 10
    elif "youtube" in src and any(k in src.lower() for k in ["itzu","kenny","eric","judo"]):
        src_pts = 9   # known top creators
    elif "youtube" in src:
        src_pts = 6
    elif "reddit" in src:
        src_pts = 5
    else:
        src_pts = 4

    total = rec + ratio_pts + eng_pts + comment_pts + fb_pts + src_pts
    return max(10, min(100, total))

def freshness_dot(date_str, lang):
    try:
        y, m = int(date_str[:4]), int(date_str[5:7])
        now = datetime.now(timezone.utc)
        mo = (now.year - y)*12 + (now.month - m)
        if mo <= 3:  return t(lang,"fresh")
        if mo <= 9:  return t(lang,"older")
        return t(lang,"stale")
    except Exception:
        return ""

def fmt_date(date_str, lang):
    try:
        M = {"en":["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
             "ru":["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"],
             "he":["ינו","פבר","מרץ","אפר","מאי","יונ","יול","אוג","ספט","אוק","נוב","דצ"]}
        y, m = int(date_str[:4]), int(date_str[5:7])
        return f"{M.get(lang,M['en'])[m-1]} {y}"
    except Exception:
        return date_str or "?"


# ══════════════════════════════════════════════════════════════
# IMAGE HELPERS
# ══════════════════════════════════════════════════════════════
HDR = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

async def fetch_img(url):
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=12, headers=HDR, follow_redirects=True) as c:
            r = await c.get(url)
        if r.status_code == 200 and "image" in r.headers.get("content-type",""):
            buf = BytesIO(r.content)
            buf.name = "base.jpg"
            buf.seek(0)
            return buf
    except Exception:
        pass
    return None

async def yt_thumb(vid_id):
    for q in ["maxresdefault","hqdefault","mqdefault"]:
        img = await fetch_img(f"https://img.youtube.com/vi/{vid_id}/{q}.jpg")
        if img:
            return img
    return None

async def page_thumb(url):
    try:
        async with httpx.AsyncClient(timeout=12, headers=HDR, follow_redirects=True) as c:
            r = await c.get(url)
        html = r.text
        og = re.search(r'property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', html)
        if og:
            return await fetch_img(og.group(1))
        imgs = re.findall(r'<img[^>]+src=["\'](https?://[^"\']+\.(?:jpg|jpeg|png|webp))["\']', html, re.I)
        for iu in imgs[:6]:
            if any(k in iu.lower() for k in ["base","layout","th"]):
                r2 = await fetch_img(iu)
                if r2: return r2
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════
# SOURCE 1 — YOUTUBE
# ══════════════════════════════════════════════════════════════
BASE_KW   = ["base","layout","design","copy","link","download","anti","defense","defence","new base"]
ATTACK_KW = ["attack","3 star","three star","how to beat","beating","raid","destroy","how i attacked","war recap"]

def is_base_video(title, desc):
    low = title.lower()
    if sum(1 for k in ATTACK_KW if k in low) > 0 and sum(1 for k in BASE_KW if k in low) == 0:
        return False
    return "link.clashofclans.com" in desc.lower()

async def search_youtube(th, purpose, max_results=15, order="date"):
    results = []
    try:
        pkw = {"WAR":"war base layout anti 3star","RANK":"trophy base layout","FARM":"farming base layout"}
        this_year = datetime.now(timezone.utc).year
        q   = f"TH{th} {pkw.get(purpose,'base layout')} {this_year} Clash of Clans copy link"
        url = (f"https://www.googleapis.com/youtube/v3/search"
               f"?part=snippet&q={quote_plus(q)}&type=video&maxResults={max_results}"
               f"&order={order}&key={YOUTUBE_API_KEY}")
        async with httpx.AsyncClient(timeout=15) as c:
            data = (await c.get(url)).json()
        if "error" in data:
            logger.warning(f"YT: {data['error'].get('message')}")
            return results
        items = data.get("items",[])
        if not items: return results
        vids = ",".join(i["id"]["videoId"] for i in items if i["id"].get("videoId"))
        durl = (f"https://www.googleapis.com/youtube/v3/videos"
                f"?part=snippet,statistics&id={vids}&key={YOUTUBE_API_KEY}")
        async with httpx.AsyncClient(timeout=15) as c:
            ddata = (await c.get(durl)).json()
        for item in ddata.get("items",[]):
            vid   = item["id"]
            title = item["snippet"]["title"]
            desc  = item["snippet"]["description"]
            pub   = item["snippet"].get("publishedAt","")[:7]
            ch    = item["snippet"].get("channelTitle","YouTube")
            st    = item.get("statistics",{})
            views = int(st.get("viewCount",0))
            likes = int(st.get("likeCount",0))
            if not is_base_video(title, desc): continue
            for raw in re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', desc):
                clean = raw.rstrip(".,)&")
                if not is_base_link(clean): continue
                if any(f"TH{o}%3A" in clean.upper() for o in range(1,19) if o != th): continue
                # extract CC from description
                cc_raw = ""
                m = re.search(r'(?:clan castle|cc)[:\s\-]+([^\n\.\!\?]{5,80})', desc.lower())
                if m: cc_raw = m.group(1)
                comment_grade, comment_summary = await get_comment_grade(vid)
                b = {
                    "link": clean, "cc": get_cc(th, purpose, cc_raw),
                    "source_name": f"YouTube · {ch}", "source_url": f"https://youtube.com/watch?v={vid}",
                    "src_tag": "yt", "image_type":"youtube", "image_id": vid,
                    "date": pub, "views": views, "likes": likes,
                    "views_fmt": f"{views//1000}K" if views>=1000 else str(views),
                    "likes_fmt": f"{likes//1000}K" if likes>=1000 else str(likes),
                    "downloads": views//10, "stars": min(5.0,3.0+likes/max(views,1)*30),
                    "comment_grade": comment_grade,
                    "comment_summary": comment_summary,
                }
                b["score"] = calc_score(b)
                results.append(b)
                break
    except Exception as e:
        logger.warning(f"YouTube error: {e}")
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


async def get_comment_grade(vid_id: str) -> tuple[int, str]:
    """
    Fetch top comments for a YouTube video and ask Gemini to grade
    whether the community thinks the base actually defends.
    Returns (grade 0-15, short summary string).
    """
    try:
        url = (f"https://www.googleapis.com/youtube/v3/commentThreads"
               f"?part=snippet&videoId={vid_id}&maxResults=30"
               f"&order=relevance&key={YOUTUBE_API_KEY}")
        async with httpx.AsyncClient(timeout=10) as c:
            data = (await c.get(url)).json()

        if "error" in data or not data.get("items"):
            return 5, ""   # neutral if no comments

        comments = []
        for item in data.get("items", []):
            text = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            likes = item["snippet"]["topLevelComment"]["snippet"]["likeCount"]
            comments.append(f"[{likes} likes] {text[:200]}")

        comments_text = "\\n".join(comments[:20])

        parts = [
            "These are YouTube comments on a Clash of Clans base layout video.\n\n",
            comments_text,
            "\n\nBased ONLY on these comments, rate how well this base defends.\n",
            "Look for: defended well, 2-starred, 3-starred, link worked, good layout.\n",
            "Ignore hype/spam. Reply ONLY as JSON (no markdown):\n",
            '{"grade": 7, "summary": "community thinks base is solid"}',
        ]
        prompt = "".join(parts)

        resp = gemini.generate_content(prompt)
        raw  = re.sub(r"```json|```", "", resp.text).strip()
        parsed = json.loads(raw)
        grade   = max(0, min(15, int(parsed.get("grade", 5))))
        summary = parsed.get("summary", "")[:100]
        logger.info(f"Comment grade for {vid_id}: {grade}/15 — {summary}")
        return grade, summary

    except Exception as e:
        logger.warning(f"Comment grade error: {e}")
        return 5, ""


# ══════════════════════════════════════════════════════════════
# SOURCE 2 — REDDIT
# ══════════════════════════════════════════════════════════════
async def search_reddit(th, purpose, sort="new", limit=25):
    results = []
    try:
        pkw = {"WAR":"war base anti 3 star","RANK":"trophy base","FARM":"farming base"}
        url = (f"https://old.reddit.com/r/ClashOfClans/search.json"
               f"?q=TH{th}+{quote_plus(pkw.get(purpose,'base'))}&sort={sort}&limit={limit}&restrict_sr=1")
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent":"Mozilla/5.0 (compatible; dlce-base-finder/1.0; +https://t.me/dlce_basefinder_bot)"}) as c:
            data = (await c.get(url)).json()
        for post in data.get("data",{}).get("children",[]):
            p       = post.get("data",{})
            title   = p.get("title","")
            body    = p.get("selftext","")
            purl    = f"https://reddit.com{p.get('permalink','')}"
            created = datetime.fromtimestamp(p.get("created_utc",0), tz=timezone.utc)
            date    = created.strftime("%Y-%m")
            ups     = p.get("score",0)
            all_t   = title + " " + body
            links   = [l for l in re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', all_t)
                       if is_base_link(l.rstrip(".,)&"))]
            if not links: continue
            img_url = None
            prev = p.get("preview",{}).get("images",[])
            if prev:
                img_url = prev[0].get("source",{}).get("url","").replace("&amp;","&")
            elif p.get("url","").endswith((".jpg",".png",".jpeg")):
                img_url = p["url"]
            cc_raw = ""
            mc = re.search(r'(?:clan castle|cc)[:\s\-]+([^\n\.\!\?]{5,80})', all_t.lower())
            if mc: cc_raw = mc.group(1)
            b = {
                "link": links[0].rstrip(".,)&"), "cc": get_cc(th, purpose, cc_raw),
                "source_name":"Reddit · r/ClashOfClans", "source_url": purl,
                "src_tag":"reddit", "image_type":"url", "image_url": img_url,
                "date": date, "views": ups*15, "likes": ups,
                "views_fmt": f"{ups} upvotes", "likes_fmt":"",
                "downloads": ups*5, "stars": min(5.0,3.0+ups/1000),
            }
            b["score"] = calc_score(b)
            results.append(b)
    except Exception as e:
        logger.warning(f"Reddit error: {e}")
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ══════════════════════════════════════════════════════════════
# SOURCE 3 — MULTIPLE BASE WEBSITES
# ══════════════════════════════════════════════════════════════
BASE_SITES = [
    ("cocbases.com",    "https://cocbases.com/th{th}-{slug}-base/",         {"WAR":"war","RANK":"trophies","FARM":"farming"}),
    ("clashtrack.com",  "https://www.clashtrack.com/th{th}/{slug}-base",     {"WAR":"war","RANK":"trophy","FARM":"farm"}),
    ("cocbasebuilder.com","https://www.cocbasebuilder.com/th{th}-{slug}-base/",{"WAR":"war","RANK":"trophy","FARM":"farming"}),
    ("clashofclansbase.com","https://clashofclansbase.com/th{th}-{slug}-base/",{"WAR":"war","RANK":"trophy","FARM":"farming"}),
    ("clashbases.de",   "https://www.clashbases.de/Clash-of-Clans-Town-Hall-{th}-Bases/",{"WAR":"war","RANK":"trophy","FARM":"farming"}),
]

async def search_websites(th, purpose):
    results = []
    for site_name, url_tpl, slug_map in BASE_SITES:
        slug = slug_map.get(purpose, "war")
        url  = url_tpl.format(th=th, slug=slug)
        try:
            async with httpx.AsyncClient(timeout=15, headers=HDR, follow_redirects=True) as c:
                r = await c.get(url)
            if r.status_code != 200:
                logger.info(f"{site_name}: status {r.status_code}")
                continue
            html  = r.text
            links = list(dict.fromkeys(
                l for l in (lnk.rstrip(".,)&") for lnk in re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', html))
                if is_base_link(l)
            ))
            if not links:
                logger.info(f"{site_name}: no base links found")
                continue
            dates = re.findall(r'20\d\d-\d\d-\d\d', html)
            date  = dates[0][:7] if dates else "2025-04"
            og    = re.search(r'property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']', html)
            img_url = og.group(1) if og else None
            logger.info(f"{site_name}: {len(links)} base links found")
            for lnk in links[:2]:
                b = {
                    "link": lnk, "cc": get_cc(th, purpose),
                    "source_name": site_name, "source_url": url,
                    "src_tag":"web", "image_type":"url", "image_url": img_url,
                    "date": date, "views":0,"likes":0,"views_fmt":"","likes_fmt":"",
                    "downloads":12000,"stars":4.5,
                }
                b["score"] = calc_score(b)
                results.append(b)
        except Exception as e:
            logger.warning(f"{site_name} error: {e}")
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ══════════════════════════════════════════════════════════════
# DEEP RESEARCH — 5 extra bases, best marked recommended
# ══════════════════════════════════════════════════════════════
async def deep_research(th, purpose):
    yt_extra, reddit_extra, web_extra = await asyncio.gather(
        search_youtube(th, purpose, max_results=25, order="viewCount"),
        search_reddit(th, purpose, sort="top", limit=50),
        search_websites(th, purpose),
    )
    seen   = set()
    merged = []
    for b in yt_extra + reddit_extra + web_extra:
        if b["link"] not in seen:
            seen.add(b["link"])
            merged.append(b)
    merged.sort(key=lambda x: x["score"], reverse=True)
    return merged[:5]


# ══════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════
async def db_save(base, th, purpose):
    if not supabase: return
    try:
        supabase.table("bases").upsert({
            "link":base["link"],"th_level":th,"purpose":purpose,
            "score":base.get("score",50),"cc":base.get("cc",""),
            "source":base.get("source_name",""),"date":base.get("date",""),
            "thumbs_up":0,"thumbs_down":0,
        }, on_conflict="link").execute()
    except Exception as e:
        logger.warning(f"DB save: {e}")

async def db_track_usage(user_id: int, username: str, th: int, purpose: str):
    """Track every search for admin analytics."""
    if not supabase: return
    try:
        supabase.table("usage").insert({
            "user_id":   str(user_id),
            "username":  username or "unknown",
            "th_level":  th,
            "purpose":   purpose,
            "searched_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        logger.warning(f"DB track: {e}")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only command — shows usage stats, feedback table, bad bases.
    SECURITY: never post the actual stats into a group chat, even if the
    caller is a genuine admin — always DM it instead, same pattern used
    for base-finder results. Non-admins in a group get no reply at all,
    so the command's existence isn't advertised to the whole clan."""
    user_id  = update.effective_user.id
    is_group = update.effective_chat.type in ("group", "supergroup")
    logger.info(f"Admin command from user_id={user_id}, ADMIN_IDS={ADMIN_IDS or '(none configured)'}, group={is_group}")

    if user_id not in ADMIN_IDS:
        if is_group:
            return  # stay silent in groups — don't advertise /admin to non-admins
        if not ADMIN_IDS:
            await update.message.reply_text(
                "⚠️ Admin panel isn't configured yet.\n\n"
                f"Your Telegram ID is: `{user_id}`\n"
                "Add it as the ADMIN_ID (or ADMIN_IDS, comma-separated for "
                "multiple admins) environment variable in Railway, then "
                "redeploy.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"Access denied. Your Telegram ID: {user_id}")
        return

    if is_group:
        # Genuine admin, but triggered from a group — redirect to DM instead
        # of posting usage stats/usernames where the whole clan can see them.
        try:
            await build_and_send_admin_panel(context.bot, user_id)
            await update.message.reply_text("📩 Admin panel sent to your DM.")
        except Exception:
            await update.message.reply_text(
                "⚠️ Couldn't DM you the admin panel — please open a private "
                "chat with the bot first (tap its name → Send Message), then "
                "run /admin again there."
            )
        return

    await build_and_send_admin_panel(context.bot, update.effective_chat.id)


async def build_and_send_admin_panel(bot, chat_id: int):
    """Builds the admin stats message and sends it to chat_id. Split out from
    admin_panel() so both the private-chat and group->DM paths share one
    implementation instead of drifting apart."""

    from collections import Counter
    lines = ["🎲 *dlce BASE bot — Admin Panel*", ""]

    # ── Database stats (if connected) ────────────────────────
    if supabase:
        try:
            usage = supabase.table("usage").select("*").order("searched_at", desc=True).limit(500).execute()
            rows  = usage.data or []
            total_searches = len(rows)
            unique_users   = len(set(r["user_id"] for r in rows))
            th_counts      = Counter(r["th_level"] for r in rows)
            purpose_counts = Counter(r["purpose"]  for r in rows)

            lines.append("📊 *Usage Stats*")
            lines.append(f"Total searches: {total_searches}")
            lines.append(f"Unique users: {unique_users}")
            lines.append("")

            lines.append("🏰 *Top TH Levels*")
            for th_lv, cnt in th_counts.most_common(5):
                lines.append(f"  TH{th_lv}: {cnt} searches")
            lines.append("")

            lines.append("🎯 *Top Purposes*")
            for pur, cnt in purpose_counts.most_common(3):
                lines.append(f"  {pur}: {cnt} searches")
            lines.append("")

            lines.append("🕐 *Recent searches (last 5)*")
            for r in rows[:5]:
                lines.append(f"  @{r.get('username','?')} — TH{r.get('th_level')} {r.get('purpose')} — {str(r.get('searched_at',''))[:16]}")
            lines.append("")

        except Exception as e:
            lines.append(f"⚠️ Usage table error: {e}")
            lines.append("")

        try:
            fb_data    = supabase.table("bases").select("*").order("thumbs_up", desc=True).limit(20).execute()
            good_bases = fb_data.data or []
            rated = [b for b in good_bases if b.get("thumbs_up",0) + b.get("thumbs_down",0) > 0]

            lines.append("✅ *Top Rated Bases*")
            if rated:
                for b in rated[:5]:
                    up   = b.get("thumbs_up",0)
                    down = b.get("thumbs_down",0)
                    pct  = int(up/(up+down)*100)
                    lines.append(f"  TH{b.get('th_level')} {b.get('purpose')} {pct}% ({up}✅{down}❌) score:{b.get('score','?')}")
                    lines.append(f"  _{b.get('source','?')}_")
            else:
                lines.append("  No feedback yet")
            lines.append("")

        except Exception as e:
            lines.append(f"⚠️ Bases table error: {e}")
            lines.append("")

        try:
            bad_data  = supabase.table("reports").select("*").order("reported_at", desc=True).limit(10).execute()
            bad_bases = bad_data.data or []

            lines.append("⚠️ *Recent Reports*")
            if bad_bases:
                for r in bad_bases[:5]:
                    lines.append(f"  {r.get('reason','?')} — TH{r.get('th_level')} {r.get('purpose','?')} — {r.get('source','?')}")
            else:
                lines.append("  No reports yet")
            lines.append("")

        except Exception as e:
            lines.append(f"⚠️ Reports table error: {e}")

    else:
        lines.append("⚠️ *Database not connected*")
        lines.append("Fix: update SUPABASE_KEY in Railway variables")
        lines.append("Get key from: Supabase → Settings → API → anon/public")
        lines.append("")

    # ── Bot status (always shown) ─────────────────────────────
    lines.append("🤖 *Bot Status*")
    lines.append(f"  Version: v7.3")
    lines.append(f"  Database: {'✅ Connected' if supabase else '❌ Not connected'}")
    lines.append(f"  YouTube API: configured")
    lines.append(f"  Admin IDs: {', '.join(str(i) for i in ADMIN_IDS) or '(none configured)'}")

    msg = chr(10).join(lines)
    if len(msg) > 4000:
        msg = msg[:3900] + chr(10) + "...(truncated)"

    await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

async def db_feedback(link, positive):
    if not supabase: return
    try:
        col = "thumbs_up" if positive else "thumbs_down"
        row = supabase.table("bases").select(col).eq("link",link).execute()
        if row.data:
            supabase.table("bases").update({col:row.data[0][col]+1}).eq("link",link).execute()
    except Exception as e:
        logger.warning(f"DB feedback: {e}")

async def db_report(link, reason, base_info):
    if not supabase: return
    try:
        supabase.table("reports").upsert({
            "link":link,"reason":reason,
            "source":base_info.get("source_name",""),
            "th_level":base_info.get("th"),"purpose":base_info.get("purpose"),
            "reported_at":datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        logger.warning(f"DB report: {e}")


# ══════════════════════════════════════════════════════════════
# CARD SENDER — compact design
# ══════════════════════════════════════════════════════════════
async def send_card(bot, chat_id, base, lang, label, link_key, context, is_recommended=False):
    link       = base["link"]
    score      = base.get("score", 50)
    cc         = base.get("cc","?")
    source_name= base.get("source_name","")
    source_url = base.get("source_url","")
    date       = base.get("date","")
    image_type = base.get("image_type","")
    image_id   = base.get("image_id","")
    image_url  = base.get("image_url")
    views_fmt  = base.get("views_fmt","")
    likes_fmt  = base.get("likes_fmt","")
    dl         = base.get("downloads",0)

    context.user_data.setdefault("links",{})[link_key] = link
    context.user_data.setdefault("bases",{})[link_key] = {
        "link":link,"source_name":source_name,"source_url":source_url,
        "th":context.user_data.get("th"),"purpose":context.user_data.get("purpose"),
    }

    fresh    = freshness_dot(date, lang)
    date_str = fmt_date(date, lang)

    # Stats line
    stats = ""
    if views_fmt:
        stats = f"👁 {views_fmt}"
        if likes_fmt: stats += f"  👍 {likes_fmt}"
    elif dl > 0:
        stats = f"⬇️ {dl//1000}K" if dl>=1000 else f"⬇️ {dl}"

    rec_line = f"*{t(lang,'recommended')}*\n" if is_recommended else ""
    comment_summary = base.get("comment_summary", "")

    caption = (
        f"{rec_line}"
        f"{label}\n"
        f"{'─'*22}\n"
        f"🏆 *{t(lang,'score',score=score)}*  {fresh} {date_str}\n"
    )
    if stats:
        caption += f"{stats}\n"
    caption += (
        f"🏰 {t(lang,'cc',cc=cc)}\n"
        f"📌 _{source_name}_"
    )
    if comment_summary:
        caption += f"\n💬 _{comment_summary}_"

    row1 = [InlineKeyboardButton(t(lang,"open_btn"), url=link)]
    if source_url:
        row1.append(InlineKeyboardButton(t(lang,"source_btn"), url=source_url))
    row2 = [
        InlineKeyboardButton(t(lang,"worked"),    callback_data=f"fb_pos_{link_key}"),
        InlineKeyboardButton(t(lang,"no_defend"), callback_data=f"fb_neg_{link_key}"),
        InlineKeyboardButton(t(lang,"report_btn"),callback_data=f"fb_rep_{link_key}"),
    ]
    markup = InlineKeyboardMarkup([row1, row2])

    # Thumbnail
    image = None
    try:
        if image_type == "youtube" and image_id:
            image = await yt_thumb(image_id)
        elif image_url:
            image = await fetch_img(image_url)
        elif source_url:
            image = await page_thumb(source_url)
    except Exception as e:
        logger.warning(f"Thumb: {e}")

    if image:
        await bot.send_photo(chat_id=chat_id, photo=image, caption=caption,
                             reply_markup=markup, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id=chat_id, text=caption,
                               reply_markup=markup, parse_mode="Markdown")



# ══════════════════════════════════════════════════════════════
# GUIDE CONTENT — multilingual
# ══════════════════════════════════════════════════════════════

# Attack guides per TH — text in all 3 languages
GUIDE_ATTACK = {
    12: {
        "title": {"ru":"⚔️ Атака ТХ12","en":"⚔️ Attack TH12","he":"⚔️ התקפה TH12"},
        "text": {
            "ru": (
                "🎥 *Первое видео для Ратуши 12!*\n\n"
                "Буду рад вашим советам и просьбам к следующим видео 😊\n\n"
                "_П.с. Закончил резко — чтоб не тратить время.\n"
                "В след раз буду по повторам показывать, а не в реальном времени 😂_"
            ),
            "en": (
                "🎥 *First video for Town Hall 12!*\n\n"
                "Would love your feedback and requests for future videos 😊\n\n"
                "_Note: ended abruptly to save time.\n"
                "Next time I\'ll use replays instead of live 😂_"
            ),
            "he": (
                "🎥 *הסרטון הראשון לאולם עיירה 12!*\n\n"
                "אשמח לקבל הצעות ובקשות לסרטונים הבאים 😊\n\n"
                "_הערה: סיימתי בפתאומיות כדי לחסוך זמן 😂_"
            ),
        },
        "video": "https://youtu.be/pvISNy7Vt4U?si=bxdxgZRVjeIEaD1G",
    },
    13: {
        "title": {"ru":"⚔️ Атака ТХ13","en":"⚔️ Attack TH13","he":"⚔️ התקפה TH13"},
        "text": {
            "ru": (
                "🐉 *Тактика: Драконы + Дирижабль*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1️⃣ *Найди Орлиную Артиллерию*\n"
                "└ Королева с одного бока (сразу способность)\n"
                "└ Принц с другого (сразу способность)\n\n"
                "2️⃣ *Выпусти войско между ними:*\n"
                "└ Шары → Драконы → Хранитель → Чемпионка\n"
                "└ Через пару сек → 🚀 Дирижабль к ратуше\n\n"
                "3️⃣ *Способность Хранителя* — спасаем Дирижабль\n\n"
                "4️⃣ *2 зелья Тотема* по бокам от ратуши — принимают урон\n\n"
                "5️⃣ *Дирижабль у ратуши:*\n"
                "└ Зелье Клонов → выпускаем Ети → Ярость на него\n\n"
                "6️⃣ *6 морозов* для контроля — Адские башни + ПВО\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            "en": (
                "🐉 *Tactic: Dragons + Airship*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1️⃣ *Find the Eagle Artillery*\n"
                "└ Queen on one side (activate ability immediately)\n"
                "└ Prince on the other side (activate immediately)\n\n"
                "2️⃣ *Deploy troops between them:*\n"
                "└ Balloons → Dragons → Warden → Champion\n"
                "└ After a few secs → 🚀 Airship toward TH\n\n"
                "3️⃣ *Warden\'s ability* — protect the Airship\n\n"
                "4️⃣ *2 Totem potions* next to TH — absorb damage\n\n"
                "5️⃣ *Airship at TH:*\n"
                "└ Clone spell → deploy Yeti → Rage on Airship\n\n"
                "6️⃣ *6 Freeze spells* — control Infernos + Air Defenses\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            "he": (
                "🐉 *טקטיקה: דרקונים + ספינה*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1️⃣ *מצא את ארטילריית הנשר*\n"
                "└ המלכה מצד אחד (הפעל יכולת מיד)\n"
                "└ הנסיך מהצד השני (הפעל מיד)\n\n"
                "2️⃣ *שלח חיילים ביניהם:*\n"
                "└ בלונים → דרקונים → שומר → אלופה\n"
                "└ אחרי כמה שניות → 🚀 ספינה לכיוון TH\n\n"
                "3️⃣ *יכולת השומר* — מגן על הספינה\n\n"
                "4️⃣ *2 כדורי טוטם* ליד ה-TH — סופגים נזק\n\n"
                "5️⃣ *ספינה ב-TH:*\n"
                "└ לחש שכפול → שלח ייטי → זעם על הספינה\n\n"
                "6️⃣ *6 הקפאות* — שלוט על מגדלי גיהנום + הגנ\'א\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
        },
        "video": "https://youtu.be/biH2TBQbPOM?si=1ACDVLUeA-vYvrhJ",
    },
    14: {
        "title": {"ru":"⚔️ Атака ТХ14","en":"⚔️ Attack TH14","he":"⚔️ התקפה TH14"},
        "text": {
            "ru": (
                "🐉 *Тактика: Драконы + Дирижабль (улучшенная)*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1️⃣ *Найди Орлиную Артиллерию*\n"
                "└ Королева с одного бока (сразу способность)\n"
                "└ Принц с другого (сразу способность)\n\n"
                "2️⃣ *Порядок войска:*\n"
                "└ Шары → Наездники на Драконах → Драконы → Хранитель → Чемпионка\n"
                "└ Через пару сек → 🚀 Дирижабль\n\n"
                "3️⃣ *Способность Хранителя* — защищаем Дирижабль\n\n"
                "4️⃣ *Контроль у ратуши:*\n"
                "└ 1 тотем + 1 фриз (или 2 тотема)\n\n"
                "5️⃣ *Дирижабль у ратуши:*\n"
                "└ 2 зелья Клонов *7 уровня* (38 мест!) → Супер-Ети → Ярость\n\n"
                "6️⃣ *3 мороза* — Адские башни + ПВО\n\n"
                "⚠️ *Важно:* Зелья Клонов должны быть *7 уровня!*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            "en": (
                "🐉 *Tactic: Dragons + Airship (upgraded)*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1️⃣ *Find the Eagle Artillery*\n"
                "└ Queen on one side (activate immediately)\n"
                "└ Prince on the other (activate immediately)\n\n"
                "2️⃣ *Troop order:*\n"
                "└ Balloons → Dragon Riders → Dragons → Warden → Champion\n"
                "└ After a few secs → 🚀 Airship\n\n"
                "3️⃣ *Warden ability* — protect the Airship\n\n"
                "4️⃣ *Control near TH:*\n"
                "└ 1 totem + 1 freeze (or 2 totems)\n\n"
                "5️⃣ *Airship at TH:*\n"
                "└ 2 Clone spells *level 7* (38 slots!) → Super Yeti → Rage\n\n"
                "6️⃣ *3 Freeze spells* — Infernos + Air Defense\n\n"
                "⚠️ *Important:* Clone spells must be *level 7!*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            "he": (
                "🐉 *טקטיקה: דרקונים + ספינה (משופרת)*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1️⃣ *מצא ארטילריית נשר*\n"
                "└ מלכה מצד אחד (הפעל מיד)\n"
                "└ נסיך מהצד השני (הפעל מיד)\n\n"
                "2️⃣ *סדר חיילים:*\n"
                "└ בלונים → רוכבי דרקון → דרקונים → שומר → אלופה\n"
                "└ אחרי כמה שניות → 🚀 ספינה\n\n"
                "3️⃣ *יכולת שומר* — מגן על הספינה\n\n"
                "4️⃣ *שליטה ליד TH:*\n"
                "└ טוטם 1 + הקפאה 1 (או 2 טוטמים)\n\n"
                "5️⃣ *ספינה ב-TH:*\n"
                "└ 2 לחשי שכפול *רמה 7* (38 מקומות!) → סופר ייטי → זעם\n\n"
                "6️⃣ *3 הקפאות* — מגדלי גיהנום + הגנ\'א\n\n"
                "⚠️ *חשוב:* לחשי שכפול חייבים להיות *רמה 7!*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
        },
        "video": "https://youtu.be/Wye_Dr_4sb8?si=I2vEqgA5AFV-iJSp",
    },
    15: {
        "title": {"ru":"⚔️ Атака ТХ15","en":"⚔️ Attack TH15","he":"⚔️ התקפה TH15"},
        "text": {
            "ru": (
                "🪖 *Тактика: Смешанная армия*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1️⃣ *Чемпионка делает проходку:*\n"
                "└ Кидаем к Орлиной Артиллерии\n"
                "└ Атакуем под зельем невидимости — забираем ОА или чистим путь\n"
                "└ Забираем Чемпионку зельем возврата\n\n"
                "2️⃣ *Основное войско:*\n"
                "└ Всё (кроме Королевы и мух) — левее проходки\n"
                "└ Там же: метатель войск + Король + Чемпионка\n\n"
                "3️⃣ *Королева в конец стороны атаки*\n"
                "└ Подчистит край → войско не разбежится!\n\n"
                "4️⃣ *3 морозных зелья* для контроля ситуации\n\n"
                "⚠️ *Главное:* войско должно оставаться *кучно!*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            "en": (
                "🪖 *Tactic: Mixed Army*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1️⃣ *Champion funnel:*\n"
                "└ Deploy near Eagle Artillery\n"
                "└ Attack under Invisibility Potion — take out EA or clear path\n"
                "└ Recall Champion with Return Potion\n\n"
                "2️⃣ *Main army:*\n"
                "└ Everything (except Queen and minions) — left of the funnel\n"
                "└ Also: Clan Castle, King, Champion\n\n"
                "3️⃣ *Queen at the end of the attack side*\n"
                "└ Cleans up the edge → troops stay together!\n\n"
                "4️⃣ *3 Freeze spells* to control the battle\n\n"
                "⚠️ *Key:* Keep your troops *grouped together!*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            "he": (
                "🪖 *טקטיקה: צבא מעורב*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1️⃣ *האלופה פותחת מסלול:*\n"
                "└ שלח ליד ארטילריית הנשר\n"
                "└ תקוף תחת קסם אלמוניות — השמד EA או נקה מסלול\n"
                "└ החזר האלופה עם כדור החזרה\n\n"
                "2️⃣ *צבא ראשי:*\n"
                "└ הכל (חוץ ממלכה ומזבובים) — שמאל למסלול\n"
                "└ גם: טירה קבוצתית, מלך, אלופה\n\n"
                "3️⃣ *מלכה בקצה צד ההתקפה*\n"
                "└ מנקה את הקצה → החיילים נשארים יחד!\n\n"
                "4️⃣ *3 הקפאות* לשליטה בקרב\n\n"
                "⚠️ *מפתח:* שמור החיילים *יחד!*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
        },
        "video": "https://youtu.be/nQr_qbCzdJ0?si=yB11d3Y8fQoOfAjy",
    },
    16: {
        "title": {"ru":"⚔️ Атака ТХ16","en":"⚔️ Attack TH16","he":"⚔️ התקפה TH16"},
        "text": {
            "ru": "🔜 *Гайд по ТХ16 скоро будет добавлен!*\n\nСледи за обновлениями бота.",
            "en": "🔜 *TH16 attack guide coming soon!*\n\nStay tuned for updates.",
            "he": "🔜 *מדריך התקפה TH16 בקרוב!*\n\nהישאר מעודכן.",
        },
        "video": None,
    },
}

GUIDE_BH = {
    "title": {
        "ru": "🔨 Builder Hall — Фарм золота столицы",
        "en": "🔨 Builder Hall — Capital Gold Farming",
        "he": "🔨 Builder Hall — פארמינג זהב הבירה",
    },
    "text": {
        "ru": (
            "💰 *Как фармить 22,000+ золота столицы за рейд*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "❌ Получаешь 6–8к за атаку? Ты делаешь это неправильно!\n\n"
            "🟠 *Шаг 1 — Клан 10 уровня*\n"
            "└ Наш клан dlce уже *10 уровень* 💪\n"
            "└ Войско: *10 шахтёров* + 1 заморозка + 2 скелетика\n\n"
            "🟣 *Шаг 2 — Атака*\n"
            "└ 🧊 Заморозку на арбалет, ракетницы, Инферно, магов, теслы\n"
            "└ 💀 2 зелья скелетов — в края или скопление деффа\n"
            "└ ⛏ Шахтёров *кучно* в одну точку со стороны заморозки\n\n"
            "🔵 *Шаг 3 — Лайфхак с выходом*\n"
            "└ Скинул всё войско → *полностью закрой игру*\n"
            "└ Зайди снова — атака уже засчитана с % урона!\n"
            "└ ⏱ Огромная экономия времени!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🏆 *Результат:* 6 атак (5 + 1 бонусная) = ~25к золота столицы"
        ),
        "en": (
            "💰 *How to farm 22,000+ Capital Gold per raid*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "❌ Getting 6–8k per attack? You\'re doing it wrong!\n\n"
            "🟠 *Step 1 — Level 10 Clan needed*\n"
            "└ Our clan dlce is already *level 10* 💪\n"
            "└ Army: *10 Miners* + 1 Freeze + 2 Skeleton spells\n\n"
            "🟣 *Step 2 — Attack*\n"
            "└ 🧊 Freeze on: Scattershot, Rocket Artillery, Inferno, Wizards, Teslas\n"
            "└ 💀 2 Skeleton spells on edges or defense clusters\n"
            "└ ⛏ Drop Miners *together* in one spot on the freeze side\n\n"
            "🔵 *Step 3 — Time-saver trick*\n"
            "└ Deploy all troops → *fully close the game*\n"
            "└ Re-open — attack already counted including % damage!\n"
            "└ ⏱ Massive time saver!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🏆 *Result:* 6 attacks (5 + 1 bonus) = ~25k Capital Gold"
        ),
        "he": (
            "💰 *איך לפארם 22,000+ זהב בירה לפשיטה*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "❌ מקבל 6-8k להתקפה? אתה עושה את זה לא נכון!\n\n"
            "🟠 *שלב 1 — קבוצה רמה 10*\n"
            "└ הקבוצה שלנו dlce כבר *רמה 10* 💪\n"
            "└ צבא: *10 כורים* + 1 הקפאה + 2 שלדים\n\n"
            "🟣 *שלב 2 — תקיפה*\n"
            "└ 🧊 הקפאה על: קשת, רקטות, אינפרנו, קוסמים, טסלות\n"
            "└ 💀 2 לחשי שלד בקצוות או על ריכוזי הגנה\n"
            "└ ⛏ שלח כורים *ביחד* לנקודה אחת מצד ההקפאה\n\n"
            "🔵 *שלב 3 — טריק חיסכון בזמן*\n"
            "└ שחרר כל החיילים → *סגור את המשחק לגמרי*\n"
            "└ פתח שוב — ההתקפה כבר נספרת כולל % נזק!\n"
            "└ ⏱ חיסכון עצום בזמן!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🏆 *תוצאה:* 6 התקפות (5 + 1 בונוס) = ~25k זהב בירה"
        ),
    },
    "video": None,
}

GUIDE_EQUIP = {
    "title": {
        "ru": "🎒 Снаряжение — Навигация",
        "en": "🎒 Equipment — Navigation",
        "he": "🎒 ציוד — ניווט",
    },
    "text": {
        "ru": (
            "🎒 *Снаряжение — Навигация*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚙️ *Руда*\n"
            "└ [Подсчёт](https://t.me/ON_Images/44/115) — Сколько руды с основных источников?\n"
            "└ [Таблица](https://t.me/ON_Images/44/114) — Руда со звёздного бонуса\n"
            "└ [Таблица](https://t.me/ON_Images/44/55) — Руда на КВ\n"
            "└ [Таблица](https://t.me/ON_Images/44/59) — Руда для прокачки снаряжения\n\n"
            "🛠️ *Разборы снаряжений*\n"
            "└ [Кукла-лавашар](https://t.me/ON_Images/44/51) — эффективность?\n"
            "└ [Электросапоги](https://t.me/ON_Images/44/46) — эффективность?\n"
            "└ [Змеиный браслет](https://t.me/ON_Images/44/47) — эффективность?\n"
            "└ [Солдатик](https://t.me/ON_Images/44/48) — эффективность?\n"
            "└ [Тёмная корона](https://t.me/ON_Images/44/50) — эффективность?\n"
            "└ [Факел героев](https://t.me/ON_Images/44/80) — эффективность?\n"
            "└ [Метеоритный посох](https://t.me/ON_Images/44/109) — эффективность?\n"
            "└ [Снежинка](https://t.me/ON_Images/44/141) — эффективность?\n\n"
            "☄️ *Другое*\n"
            "└ [Огненный шар](https://t.me/ON_Images/44/81) — радиус взрыва 2х2/3х3/4х4\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "en": (
            "🎒 *Equipment — Navigation*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚙️ *Ore*\n"
            "└ [Calculator](https://t.me/ON_Images/44/115) — How much ore from main sources?\n"
            "└ [Table](https://t.me/ON_Images/44/114) — Ore from Star Bonus\n"
            "└ [Table](https://t.me/ON_Images/44/55) — Ore from Clan Wars\n"
            "└ [Table](https://t.me/ON_Images/44/59) — Ore needed to upgrade equipment\n\n"
            "🛠️ *Equipment Reviews*\n"
            "└ [Lava Launcher](https://t.me/ON_Images/44/51) — how effective?\n"
            "└ [Giant Gauntlet](https://t.me/ON_Images/44/46) — how effective?\n"
            "└ [Snake Bracelet](https://t.me/ON_Images/44/47) — how effective?\n"
            "└ [Hog Rider Puppet](https://t.me/ON_Images/44/48) — how effective?\n"
            "└ [Dark Crown](https://t.me/ON_Images/44/50) — how effective?\n"
            "└ [Hero Torch](https://t.me/ON_Images/44/80) — how effective?\n"
            "└ [Meteor Staff](https://t.me/ON_Images/44/109) — how effective?\n"
            "└ [Snowflake](https://t.me/ON_Images/44/141) — how effective?\n\n"
            "☄️ *Other*\n"
            "└ [Fireball](https://t.me/ON_Images/44/81) — blast radius 2x2/3x3/4x4\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "he": (
            "🎒 *ציוד — ניווט*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚙️ *עפרה*\n"
            "└ [חישוב](https://t.me/ON_Images/44/115) — כמה עפרה ממקורות עיקריים?\n"
            "└ [טבלה](https://t.me/ON_Images/44/114) — עפרה מבונוס כוכבים\n"
            "└ [טבלה](https://t.me/ON_Images/44/55) — עפרה ממלחמות קבוצה\n"
            "└ [טבלה](https://t.me/ON_Images/44/59) — עפרה לשדרוג ציוד\n\n"
            "🛠️ *סקירות ציוד*\n"
            "└ [כדור לבה](https://t.me/ON_Images/44/51) — כמה אפקטיבי?\n"
            "└ [כפפת ענק](https://t.me/ON_Images/44/46) — כמה אפקטיבי?\n"
            "└ [צמיד נחש](https://t.me/ON_Images/44/47) — כמה אפקטיבי?\n"
            "└ [בובת חזיר](https://t.me/ON_Images/44/48) — כמה אפקטיבי?\n"
            "└ [כתר אפל](https://t.me/ON_Images/44/50) — כמה אפקטיבי?\n"
            "└ [לפיד גיבור](https://t.me/ON_Images/44/80) — כמה אפקטיבי?\n"
            "└ [מטאור](https://t.me/ON_Images/44/109) — כמה אפקטיבי?\n"
            "└ [פתית שלג](https://t.me/ON_Images/44/141) — כמה אפקטיבי?\n\n"
            "☄️ *אחר*\n"
            "└ [כדור אש](https://t.me/ON_Images/44/81) — רדיוס פיצוץ 2x2/3x3/4x4\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
    },
    "video": None,
}

# WEB SERVICES — replaces Heroes
GUIDE_WEB = {
    "title": {
        "ru": "🌐 Веб-сервисы для CoC",
        "en": "🌐 Web Services for CoC",
        "he": "🌐 שירותי אינטרנט ל-CoC",
    },
    "text": {
        "ru": (
            "🌐 *Полезные сервисы для Clash of Clans*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚔️ *Атаки*\n"
            "└ [FTB](https://t.me/ON_Images/116/119) — Поиск видео атаки по скриншоту базы\n"
            "└ [War Report](https://t.me/ON_Images/116/120) — Трекер клановых войн\n"
            "└ [Zap Quaker](https://t.me/ON_Images/116/121) — Калькулятор заклинаний\n"
            "└ [Damage Calculator](https://t.me/ON_Images/116/122) — Продвинутый калькулятор урона\n\n"
            "⬆️ *Прокачка*\n"
            "└ [Clash Ninja](https://t.me/ON_Images/116/125) — Время до полной прокачки деревни\n"
            "└ [Clash Tools](https://t.me/ON_Images/116/129) — Простой трекер прокачки\n"
            "└ [Ore Calculator](https://t.me/ON_Images/116/123) — Калькулятор руды для снаряжения\n\n"
            "📈 *Статистика*\n"
            "└ [Clash of Stats](https://t.me/ON_Images/116/127) — Подробная статистика клана/игрока\n"
            "└ [Clash Spot](https://t.me/ON_Images/116/126) — Индивидуальная и глобальная статистика\n\n"
            "📢 *Другое*\n"
            "└ [Clash Fandom](https://t.me/ON_Images/116/124) — Вики по Clash of Clans\n"
            "└ [Coc Wall Crafter](https://t.me/ON_Images/116/139) — Рисуем базу с ником или логотипом\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "en": (
            "🌐 *Useful Web Services for Clash of Clans*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚔️ *Attacks*\n"
            "└ [FTB](https://t.me/ON_Images/116/119) — Find attack videos from base screenshots\n"
            "└ [War Report](https://t.me/ON_Images/116/120) — Clan war tracker\n"
            "└ [Zap Quaker](https://t.me/ON_Images/116/121) — Spell calculator\n"
            "└ [Damage Calculator](https://t.me/ON_Images/116/122) — Advanced damage calculator\n\n"
            "⬆️ *Upgrading*\n"
            "└ [Clash Ninja](https://t.me/ON_Images/116/125) — Time to max your village\n"
            "└ [Clash Tools](https://t.me/ON_Images/116/129) — Simple upgrade tracker\n"
            "└ [Ore Calculator](https://t.me/ON_Images/116/123) — Ore calculator for equipment\n\n"
            "📈 *Statistics*\n"
            "└ [Clash of Stats](https://t.me/ON_Images/116/127) — Detailed clan/player stats\n"
            "└ [Clash Spot](https://t.me/ON_Images/116/126) — Individual and global stats\n\n"
            "📢 *Other*\n"
            "└ [Clash Fandom](https://t.me/ON_Images/116/124) — Clash of Clans wiki\n"
            "└ [Coc Wall Crafter](https://t.me/ON_Images/116/139) — Draw your base with clan name/logo\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        "he": (
            "🌐 *שירותי אינטרנט שימושיים ל-CoC*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚔️ *התקפות*\n"
            "└ [FTB](https://t.me/ON_Images/116/119) — מציאת סרטוני התקפה מתמונות בסיס\n"
            "└ [War Report](https://t.me/ON_Images/116/120) — מעקב מלחמות קבוצה\n"
            "└ [Zap Quaker](https://t.me/ON_Images/116/121) — מחשבון לחשים\n"
            "└ [Damage Calculator](https://t.me/ON_Images/116/122) — מחשבון נזק מתקדם\n\n"
            "⬆️ *שדרוג*\n"
            "└ [Clash Ninja](https://t.me/ON_Images/116/125) — זמן למקסם הכפר\n"
            "└ [Clash Tools](https://t.me/ON_Images/116/129) — מעקב שדרוגים פשוט\n"
            "└ [Ore Calculator](https://t.me/ON_Images/116/123) — מחשבון עפרה לציוד\n\n"
            "📈 *סטטיסטיקות*\n"
            "└ [Clash of Stats](https://t.me/ON_Images/116/127) — סטטיסטיקות מפורטות\n"
            "└ [Clash Spot](https://t.me/ON_Images/116/126) — סטטיסטיקות אישיות וגלובליות\n\n"
            "📢 *אחר*\n"
            "└ [Clash Fandom](https://t.me/ON_Images/116/124) — ויקי Clash of Clans\n"
            "└ [Coc Wall Crafter](https://t.me/ON_Images/116/139) — ציור בסיס עם שם/לוגו\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
    },
    "video": None,
}

# ══════════════════════════════════════════════════════════════
# GROUP HANDLER — redirect to DM
# ══════════════════════════════════════════════════════════════
async def group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """When /start is used in a group, redirect user to DM."""
    if update.effective_chat.type in ["group","supergroup"]:
        lang = context.user_data.get("lang","en")
        bot_username = context.bot.username
        await update.message.reply_text(
            t(lang,"group_msg"),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    t(lang,"open_dm"),
                    url=f"https://t.me/{bot_username}?start=from_group"
                )
            ]])
        )
        return ConversationHandler.END
    # Private chat — proceed normally
    return await start_private(update, context)


# ══════════════════════════════════════════════════════════════
# CONVERSATION HANDLERS
# ══════════════════════════════════════════════════════════════
async def start_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇮🇱 עברית",   callback_data="lang_he"),
    ]]
    await update.message.reply_text(
        T["en"]["welcome"],
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return LANG

async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.replace("lang_","")
    context.user_data["lang"] = lang
    keyboard = [[
        InlineKeyboardButton(t(lang,"cat_bases"),  callback_data="cat_bases"),
        InlineKeyboardButton(t(lang,"cat_guides"), callback_data="cat_guides"),
    ]]
    await query.edit_message_text(
        t(lang,"q_category"),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CATEGORY


async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang     = context.user_data.get("lang","en")
    category = query.data  # "cat_bases" or "cat_guides"

    if category == "cat_bases":
        # Go to TH selection
        row1 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(10,14)]
        row2 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(14,18)]
        row3 = [InlineKeyboardButton("TH18",   callback_data="th_18")]
        await query.edit_message_text(t(lang,"q_th"), reply_markup=InlineKeyboardMarkup([row1,row2,row3]))
        return TH_LEVEL

    else:
        # Go to guide topic selection
        keyboard = [[
            InlineKeyboardButton(t(lang,"guide_attack"), callback_data="guide_attack"),
            InlineKeyboardButton(t(lang,"guide_bh"),     callback_data="guide_bh"),
        ],[
            InlineKeyboardButton(t(lang,"guide_equip"),  callback_data="guide_equip"),
            InlineKeyboardButton(t(lang,"guide_web"),    callback_data="guide_web"),
        ]]
        await query.edit_message_text(
            t(lang,"q_guide_topic"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return GUIDE_TOPIC


# ══════════════════════════════════════════════════════════════
# QUICK-ACCESS ENTRY POINTS — /basefinder and /guides
# Let users jump straight past Language + Category screens.
# Registered as BOTH entry_points and fallbacks on the conv
# handler so they work whether or not a conversation is already
# active (see main() for details).
# ══════════════════════════════════════════════════════════════
async def _redirect_if_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Shared group->DM redirect used by all quick-access entry points."""
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        lang = context.user_data.get("lang", "en")
        bot_username = context.bot.username
        await update.message.reply_text(
            t(lang, "group_msg"),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    t(lang, "open_dm"),
                    url=f"https://t.me/{bot_username}?start=from_group"
                )
            ]])
        )
        return True
    return False


async def quick_basefinder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/basefinder command — jump straight to TH level selection."""
    if await _redirect_if_group(update, context):
        return ConversationHandler.END

    lang = context.user_data.get("lang", "en")
    context.user_data.pop("th", None)
    context.user_data.pop("purpose", None)
    row1 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(10, 14)]
    row2 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(14, 18)]
    row3 = [InlineKeyboardButton("TH18",   callback_data="th_18")]
    await update.message.reply_text(t(lang, "q_th"), reply_markup=InlineKeyboardMarkup([row1, row2, row3]))
    return TH_LEVEL


async def quick_guides(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/guides command — jump straight to guide topic selection."""
    if await _redirect_if_group(update, context):
        return ConversationHandler.END

    lang = context.user_data.get("lang", "en")
    keyboard = [[
        InlineKeyboardButton(t(lang, "guide_attack"), callback_data="guide_attack"),
        InlineKeyboardButton(t(lang, "guide_bh"),     callback_data="guide_bh"),
    ], [
        InlineKeyboardButton(t(lang, "guide_equip"),  callback_data="guide_equip"),
        InlineKeyboardButton(t(lang, "guide_web"),    callback_data="guide_web"),
    ]]
    await update.message.reply_text(t(lang, "q_guide_topic"), reply_markup=InlineKeyboardMarkup(keyboard))
    return GUIDE_TOPIC


async def guide_topic_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User chose a guide topic."""
    query = update.callback_query
    await query.answer()
    lang  = context.user_data.get("lang","en")
    topic = query.data  # guide_attack, guide_bh, guide_equip, guide_heroes

    if topic == "guide_attack":
        # Show TH level selection for attack guides
        keyboard = [[
            InlineKeyboardButton("TH12", callback_data="atk_12"),
            InlineKeyboardButton("TH13", callback_data="atk_13"),
            InlineKeyboardButton("TH14", callback_data="atk_14"),
        ],[
            InlineKeyboardButton("TH15", callback_data="atk_15"),
            InlineKeyboardButton("TH16", callback_data="atk_16"),
        ]]
        await query.edit_message_text(
            f"{t(lang,'guide_attack')}\n\n{t(lang,'q_th')}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return GUIDE_ATTACK_TH

    elif topic == "guide_bh":
        await send_guide(query, lang, GUIDE_BH)
        return ConversationHandler.END

    elif topic == "guide_equip":
        await send_guide(query, lang, GUIDE_EQUIP)
        return ConversationHandler.END

    elif topic == "guide_web":
        await send_guide(query, lang, GUIDE_WEB)
        return ConversationHandler.END

    return ConversationHandler.END


async def guide_attack_th_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User chose TH level for attack guide."""
    query = update.callback_query
    await query.answer()
    lang    = context.user_data.get("lang","en")
    th_num  = int(query.data.replace("atk_",""))
    guide   = GUIDE_ATTACK.get(th_num)
    if guide:
        await send_guide(query, lang, guide)
    else:
        await query.edit_message_text("Guide not available yet. Check back soon!")
    return ConversationHandler.END


async def send_guide(query, lang: str, guide: dict):
    """Send a guide card with title, text and optional video button."""
    # Support both multilingual dicts and plain strings
    raw_title = guide.get("title","")
    raw_text  = guide.get("text","")
    video     = guide.get("video")

    if isinstance(raw_title, dict):
        title = raw_title.get(lang, raw_title.get("ru", ""))
    else:
        title = raw_title

    if isinstance(raw_text, dict):
        text = raw_text.get(lang, raw_text.get("ru", ""))
    else:
        text = raw_text

    msg = f"{text}"  # title already included in text for new guides

    keyboard_rows = []
    if video:
        keyboard_rows.append([
            InlineKeyboardButton(t(lang,"watch_video"), url=video)
        ])
    keyboard_rows.append([
        InlineKeyboardButton(t(lang,"back_main"), callback_data="back_to_main")
    ])
    markup = InlineKeyboardMarkup(keyboard_rows)

    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=markup)


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

    await query.edit_message_text(t(lang,"searching"))

    # Track usage for admin analytics
    user = update.effective_user
    await db_track_usage(
        user.id if user else 0,
        user.username or user.first_name or "?" if user else "?",
        th, purpose
    )

    # Run all 3 source searches in parallel
    yt_list, reddit_list, web_list = await asyncio.gather(
        search_youtube(th, purpose),
        search_reddit(th, purpose),
        search_websites(th, purpose),
    )

    purpose_label = t(lang, purpose.lower())

    # ── Build pool of candidates — guaranteed 3 ──────────────
    # Each source tagged so we can show label
    all_candidates = []
    seen_links = set()

    def add_tagged(lst, tag):
        for b in lst:
            if b["link"] not in seen_links:
                seen_links.add(b["link"])
                b["_tag"] = tag
                all_candidates.append(b)

    add_tagged(yt_list,     "📺 YouTube")
    add_tagged(reddit_list, "💬 Reddit")
    add_tagged(web_list,    "🌐 Web")

    # Sort all by score
    all_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Try to pick 1 from each source for variety
    picked = []
    used_tags = set()
    for b in all_candidates:
        if b["_tag"] not in used_tags:
            picked.append(b)
            used_tags.add(b["_tag"])
        if len(picked) == 3:
            break

    # If still < 3, fill from remaining (any source)
    if len(picked) < 3:
        for b in all_candidates:
            if b not in picked:
                picked.append(b)
            if len(picked) == 3:
                break

    # ── Send to DM if in group ────────────────────────────────
    group_types = ["group","supergroup"]
    is_group    = update.effective_chat.type in group_types if update.effective_chat else False
    if is_group:
        user_id = update.effective_user.id
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=t(lang,"dm_notice")
        )
        send_to = user_id
    else:
        send_to = chat_id

    await context.bot.send_message(
        chat_id=send_to,
        text=t(lang,"dm_intro",th=th,purpose=purpose_label),
        parse_mode="Markdown"
    )

    for i, base in enumerate(picked):
        label = base.get("_tag", f"#{i+1}")
        lk    = hashlib.md5(base["link"].encode()).hexdigest()[:16]
        await send_card(context.bot, send_to, base, lang, label, lk, context)
        await db_save(base, th, purpose)

    # Last resort — use built-in database if everything failed
    if not picked:
        logger.info("All sources failed — using BUILTIN database")
        builtin = BUILTIN.get(th, {}).get(purpose, [])
        for b in builtin[:3]:
            base = dict(b)
            base.update({
                "source_name": "CoC Community",
                "source_url":  f"https://cocbases.com/",
                "src_tag":     "web",
                "image_type":  "none",
                "image_url":   None,
                "views": 0, "likes": 0,
                "views_fmt": "", "likes_fmt": "",
                "comment_grade": 0, "comment_summary": "",
            })
            base["cc"]    = get_cc(th, purpose)
            base["score"] = calc_score(base)
            base["_tag"]  = "🗄 Built-in"
            picked.append(base)

    if not picked:
        await context.bot.send_message(
            chat_id=send_to,
            text=t(lang,"no_results")
        )
        return ConversationHandler.END

    # Deep Research + Back to main menu buttons
    dk = f"{th}_{purpose}_{lang}"
    await context.bot.send_message(
        chat_id=send_to,
        text="─"*22,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang,"deep_btn"),  callback_data=f"deep_{dk}")],
            [InlineKeyboardButton(t(lang,"back_main"), callback_data="back_to_main")],
        ])
    )
    return ConversationHandler.END


async def deep_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts   = query.data.split("_")   # deep_TH_PURPOSE_LANG
    th      = int(parts[1])
    purpose = parts[2]
    lang    = parts[3] if len(parts)>3 else context.user_data.get("lang","en")
    chat_id = query.message.chat_id

    await query.edit_message_text(t(lang,"deep_searching"))

    results = await deep_research(th, purpose)
    purpose_label = t(lang, purpose.lower())

    await context.bot.send_message(
        chat_id=chat_id,
        text=t(lang,"deep_header",th=th,purpose=purpose_label),
        parse_mode="Markdown"
    )

    for i,base in enumerate(results[:5]):
        lk = hashlib.md5(base["link"].encode()).hexdigest()[:16]
        label = f"🔬 #{i+1}"
        is_rec = (i == 0)
        await send_card(context.bot, chat_id, base, lang, label, lk, context, is_recommended=is_rec)
        await db_save(base, th, purpose)


async def feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    lang    = context.user_data.get("lang","en")
    data    = query.data
    chat_id = query.message.chat_id

    if data.startswith("fb_pos_") or data.startswith("fb_neg_"):
        positive = data.startswith("fb_pos_")
        lk       = data[7:]
        link     = context.user_data.get("links",{}).get(lk, lk)
        await db_feedback(link, positive)
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=chat_id,
            text=t(lang,"thanks_good") if positive else t(lang,"thanks_bad")
        )
        return

    if data.startswith("fb_rep_"):
        lk     = data[7:]
        base   = context.user_data.get("bases",{}).get(lk,{})
        source = base.get("source_name","?")
        kb = [[
            InlineKeyboardButton(t(lang,"rep_wrong_th"),  callback_data=f"rp_wrongth_{lk}"),
            InlineKeyboardButton(t(lang,"rep_attack"),    callback_data=f"rp_attack_{lk}"),
        ],[
            InlineKeyboardButton(t(lang,"rep_dead_link"), callback_data=f"rp_deadlink_{lk}"),
            InlineKeyboardButton(t(lang,"rep_old_base"),  callback_data=f"rp_oldbase_{lk}"),
        ],[
            InlineKeyboardButton(t(lang,"rep_bad_cc"),    callback_data=f"rp_badcc_{lk}"),
            InlineKeyboardButton(t(lang,"rep_other"),     callback_data=f"rp_other_{lk}"),
        ]]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ {t(lang,'report_q')}\n📌 {source}",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data.startswith("rp_"):
        lk     = data[-16:]
        reason = data[3:-17]
        link   = context.user_data.get("links",{}).get(lk,"?")
        base   = context.user_data.get("bases",{}).get(lk,{})
        await db_report(link, reason, base)
        await db_feedback(link, positive=False)
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text=t(lang,"report_thanks"))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled. Send /start to try again.")
    return ConversationHandler.END


async def back_to_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to main menu — sends a fresh message and re-enters the
    conversation at CATEGORY so the next tap (cat_bases/cat_guides) is
    actually picked up by category_chosen instead of being dropped."""
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang","en")
    keyboard = [[
        InlineKeyboardButton(t(lang,"cat_bases"),  callback_data="cat_bases"),
        InlineKeyboardButton(t(lang,"cat_guides"), callback_data="cat_guides"),
    ]]
    # Send as NEW message so conversation handler picks it up fresh
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=t(lang,"q_category"),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    # Reset conversation state by clearing user data partially
    context.user_data.pop("th", None)
    context.user_data.pop("purpose", None)
    # IMPORTANT: this handler is registered on the ConversationHandler
    # itself (entry_points + fallbacks). Returning CATEGORY tells PTB's
    # internal state tracker that this user is now "in" CATEGORY, so the
    # cat_bases/cat_guides tap that follows is routed to category_chosen
    # instead of falling through to nothing (the old freeze bug).
    return CATEGORY


async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /language command — show language picker."""
    keyboard = [[
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇮🇱 עברית",   callback_data="lang_he"),
    ]]
    await update.message.reply_text(
        "🌍 Choose language / Выбери язык / בחר שפה",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return LANG


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang","en")
    lines_en = [
        "🎲 *dlce BASE bot*",
        "",
        "/start — Find a base (TH10–18)",
        "/language — Change language",
        "/help — This message",
        "",
        "*How scoring works:*",
        "🟢 Fresh = posted <3 months",
        "🟡 Older = 3–9 months",
        "🔴 Old = 9+ months",
        "",
        "*Steps:*",
        "1️⃣ Pick TH level",
        "2️⃣ Pick purpose",
        "3️⃣ Get 3 bases (YouTube + Reddit + Sites)",
        "4️⃣ Tap 🏰 to open in game",
        "5️⃣ Rate with ✅/❌ — bot learns!",
        "6️⃣ Tap 🔬 Deep Research for 5 more",
        "",
        "*In groups:* results go to your DM.",
    ]
    lines_ru = [
        "🎲 *dlce BASE bot*",
        "",
        "/start — Найти базу (РЗ10–18)",
        "/language — Сменить язык",
        "/help — Это сообщение",
        "",
        "*Оценка:*",
        "🟢 Свежая = <3 месяца",
        "🟡 Постарше = 3–9 мес.",
        "🔴 Старая = 9+ мес.",
        "",
        "*Шаги:*",
        "1️⃣ Уровень РУ",
        "2️⃣ Цель базы",
        "3️⃣ 3 базы (YouTube + Reddit + Сайты)",
        "4️⃣ 🏰 открыть в игре",
        "5️⃣ Оцени ✅/❌ — бот учится!",
        "6️⃣ 🔬 Глубокий поиск — ещё 5 баз",
        "",
        "*В группах:* результаты в личку.",
    ]
    lines_he = [
        "🎲 *dlce BASE bot*",
        "",
        "/start — מצא בסיס (TH10–18)",
        "/language — שנה שפה",
        "/help — הודעה זו",
        "",
        "*דירוג:*",
        "🟢 חדש = <3 חודשים",
        "🟡 ישן יותר = 3–9 חוד.",
        "🔴 ישן = 9+ חוד.",
        "",
        "*שלבים:*",
        "1️⃣ בחר רמת TH",
        "2️⃣ בחר מטרה",
        "3️⃣ 3 בסיסים (YouTube + Reddit + אתרים)",
        "4️⃣ 🏰 לפתוח במשחק",
        "5️⃣ דרג ✅/❌ — הבוט לומד!",
        "6️⃣ 🔬 מחקר מעמיק",
        "",
        "*בקבוצות:* תוצאות בפרטי.",
    ]
    txt_map = {"en": lines_en, "ru": lines_ru, "he": lines_he}
    msg = "\\n".join(txt_map.get(lang, lines_en))
    await update.message.reply_text(msg, parse_mode="Markdown")


async def post_init(app):
    """Set bot commands menu shown in Telegram UI."""
    from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats, BotCommandScopeChat
    # NOTE: "admin" is deliberately left OUT of the shared private_cmds list —
    # otherwise every user who opens a DM with the bot sees "🔐 Admin panel"
    # in their command menu. It's registered below, per-chat, only for the
    # Telegram IDs configured in ADMIN_ID / ADMIN_IDS.
    private_cmds = [
        BotCommand("start",      "🎲 Base Finder + Guides"),
        BotCommand("basefinder", "🏰 Base Finder (skip straight to TH pick)"),
        BotCommand("guides",     "📖 Guides (skip straight to topics)"),
        BotCommand("language",   "🌍 Change language"),
        BotCommand("help",       "❓ How the bot works"),
    ]
    group_cmds = [
        BotCommand("start",      "🎲 Base Finder + Guides (results in DM)"),
        BotCommand("basefinder", "🏰 Base Finder (results in DM)"),
        BotCommand("guides",     "📖 Guides (results in DM)"),
        BotCommand("help",       "❓ How the bot works"),
    ]
    await app.bot.set_my_commands(private_cmds, scope=BotCommandScopeAllPrivateChats())
    await app.bot.set_my_commands(group_cmds,   scope=BotCommandScopeAllGroupChats())

    admin_cmds = private_cmds + [BotCommand("admin", "🔐 Admin panel")]
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            # Most common cause: this admin has never opened a DM with the
            # bot yet, so Telegram doesn't have a chat to scope commands to.
            # /admin still works for them via fallback (unscoped commands
            # still accept typed text) — this only affects the menu list.
            logger.warning(f"Could not set admin command menu for {admin_id}: {e}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # ── FIX NOTES (v7.3) ──────────────────────────────────────────
    # Root cause of BOTH "freeze" bugs was the same pattern: a button/
    # command that's meant to re-enter the conversation flow (🌍 change
    # language mid-flow, 🏠 Main Menu, /basefinder, /guides) was wired
    # up as a *separate* top-level handler outside the ConversationHandler.
    # PTB tracks conversation state internally per user; a handler that
    # lives outside `conv` can display a screen but can't update that
    # internal state. The next tap then gets checked against the *real*
    # (unchanged/cleared) state, matches nothing, and is silently
    # dropped — which looks exactly like a freeze (button spinner never
    # resolves, bot appears dead).
    #
    # Fix: every handler that needs to (re)start or jump around the flow
    # is registered on `conv` itself, in BOTH `entry_points` (fires when
    # no conversation is currently active — e.g. right after a guide or
    # base results ended it) AND `fallbacks` (fires when a conversation
    # IS active in some other state — e.g. user opens /language via the
    # command menu mid-flow). That way PTB always keeps its internal
    # state in sync with whatever screen the user is actually looking at.
    restart_entries = [
        CommandHandler("start",       group_start),
        CommandHandler("language",    language_cmd),
        CommandHandler("basefinder",  quick_basefinder),
        CommandHandler("guides",      quick_guides),
        CallbackQueryHandler(back_to_main_handler, pattern="^back_to_main"),
    ]
    conv = ConversationHandler(
        entry_points=restart_entries,
        states={
            LANG:            [CallbackQueryHandler(language_chosen,        pattern="^lang_")],
            CATEGORY:        [CallbackQueryHandler(category_chosen,        pattern="^cat_")],
            TH_LEVEL:        [CallbackQueryHandler(th_chosen,              pattern="^th_")],
            PURPOSE:         [CallbackQueryHandler(purpose_chosen,         pattern="^purpose_")],
            GUIDE_TOPIC:     [CallbackQueryHandler(guide_topic_chosen,     pattern="^guide_")],
            GUIDE_ATTACK_TH: [CallbackQueryHandler(guide_attack_th_chosen, pattern="^atk_")],
        },
        # Same handlers again as fallbacks: fallbacks are only checked
        # while a conversation is ACTIVE (state != None), entry_points
        # only when it's NOT (state == None) — we need both to cover
        # every point where a user might hit one of these buttons/commands.
        fallbacks=[CommandHandler("cancel", cancel)] + restart_entries,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("help",     help_cmd))
    app.add_handler(CommandHandler("admin",    admin_panel))
    app.add_handler(CallbackQueryHandler(feedback_handler,    pattern="^fb_"))
    app.add_handler(CallbackQueryHandler(feedback_handler,    pattern="^rp_"))
    app.add_handler(CallbackQueryHandler(deep_handler,        pattern="^deep_"))
    logger.info("dlce BASE bot v7.3 starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
