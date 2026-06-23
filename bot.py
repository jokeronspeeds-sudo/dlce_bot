# dlce BASE bot v5.0
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
ADMIN_ID        = int(os.environ.get("ADMIN_ID", "0"))  # your Telegram user ID

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
        "welcome":        "🎲 *dlce BASE bot*\n\nFinds the best CoC bases from YouTube, Reddit & 5 base sites — with real stats & CC troops.\n\nChoose language:",
        "q_th":           "🏰 Select Town Hall level:",
        "q_purpose":      "🎯 Purpose?",
        "searching":      "🔍 Searching all sources...",
        "dm_notice":      "📩 Results sent to your DM!",
        "dm_intro":       "🎲 *dlce BASE bot*\nTH{th} · {purpose}\n",
        "recommended":    "⭐ RECOMMENDED",
        "score":          "{score}/100",
        "cc":             "CC: {cc}",
        "date_label":     "{date}",
        "open_btn":       "🏰 Copy Base",
        "source_btn":     "📌 Source",
        "worked":         "✅ Works",
        "no_defend":      "❌ Failed",
        "report_btn":     "⚠️ Report",
        "thanks_good":    "🎉 Score +1. Thanks!",
        "thanks_bad":     "📉 Score -1. Thanks!",
        "report_q":       "What's wrong?",
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
        "group_msg":      "👋 Hi! I work best in DMs.\nTap the button below to get bases in private:",
        "open_dm":        "💬 Open DM",
    },
    "ru": {
        "welcome":        "🎲 *dlce BASE bot*\n\nНахожу лучшие базы с YouTube, Reddit и 5 сайтов — с реальной статистикой и войсками ЗК.\n\nВыбери язык:",
        "q_th":           "🏰 Уровень ратуши:",
        "q_purpose":      "🎯 Цель базы?",
        "searching":      "🔍 Ищу во всех источниках...",
        "dm_notice":      "📩 Результаты отправлены в личку!",
        "dm_intro":       "🎲 *dlce BASE bot*\nРУ{th} · {purpose}\n",
        "recommended":    "⭐ РЕКОМЕНДУЕМ",
        "score":          "{score}/100",
        "cc":             "ЗК: {cc}",
        "date_label":     "{date}",
        "open_btn":       "🏰 Скопировать",
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
        "report_thanks":  "✅ Репорт отправлен!",
        "deep_btn":       "🔬 Глубокий поиск (+5 баз)",
        "deep_header":    "🔬 Глубокий поиск — РУ{th} {purpose}",
        "deep_searching": "🔬 Глубокий поиск (~30с)...",
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
        "welcome":        "🎲 *dlce BASE bot*\n\nמוצא בסיסים מ-YouTube, Reddit ו-5 אתרים — עם סטטיסטיקות וחיילי טירה.\n\nבחר שפה:",
        "q_th":           "🏰 רמת עיירת מועצה:",
        "q_purpose":      "🎯 מטרת הבסיס?",
        "searching":      "🔍 מחפש בכל המקורות...",
        "dm_notice":      "📩 התוצאות נשלחו בפרטי!",
        "dm_intro":       "🎲 *dlce BASE bot*\nTH{th} · {purpose}\n",
        "recommended":    "⭐ מומלץ",
        "score":          "{score}/100",
        "cc":             "טירה: {cc}",
        "date_label":     "{date}",
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
        "report_thanks":  "✅ דווח!",
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
        "open_dm":        "💬 פתח צ'אט פרטי",
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
        q   = f"TH{th} {pkw.get(purpose,'base layout')} 2025 Clash of Clans copy link"
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
        url = (f"https://www.reddit.com/r/ClashOfClans/search.json"
               f"?q=TH{th}+{quote_plus(pkw.get(purpose,'base'))}&sort={sort}&limit={limit}&restrict_sr=1")
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent":"dlce-base-bot/1.0"}) as c:
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
    ("cocbases.com",    "https://cocbases.com/th{th}-{slug}-base/",         {"WAR":"war","RANK":"trophy","FARM":"farming"}),
    ("clashtrack.com",  "https://www.clashtrack.com/th{th}/{slug}-base",     {"WAR":"war","RANK":"trophy","FARM":"farm"}),
    ("cocbasebuilder.com","https://www.cocbasebuilder.com/th{th}-{slug}-base/",{"WAR":"war","RANK":"trophy","FARM":"farming"}),
    ("clashofclansbase.com","https://clashofclansbase.com/th{th}-{slug}-base/",{"WAR":"war","RANK":"trophy","FARM":"farming"}),
    ("clashbases.com",  "https://www.clashbases.de/th{th}-{slug}/",          {"WAR":"war","RANK":"trophy","FARM":"farming"}),
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
    """Admin-only command — shows usage stats, feedback table, bad bases."""
    user_id = update.effective_user.id
    if ADMIN_ID and user_id != ADMIN_ID:
        await update.message.reply_text("Access denied.")
        return

    if not supabase:
        await update.message.reply_text("No database connected.")
        return

    try:
        # Usage stats
        usage = supabase.table("usage").select("*").order("searched_at", desc=True).limit(200).execute()
        rows  = usage.data or []
        total_searches = len(rows)
        unique_users   = len(set(r["user_id"] for r in rows))

        # Most searched TH levels
        from collections import Counter
        th_counts      = Counter(r["th_level"] for r in rows)
        purpose_counts = Counter(r["purpose"]  for r in rows)
        top_th  = th_counts.most_common(3)
        top_pur = purpose_counts.most_common(3)

        # Bases with feedback
        fb_data  = supabase.table("bases").select("*").order("thumbs_up", desc=True).limit(10).execute()
        good_bases = fb_data.data or []

        # Bad bases (more thumbs down than up)
        bad_data  = supabase.table("reports").select("*").order("reported_at", desc=True).limit(10).execute()
        bad_bases = bad_data.data or []

        # Build message
        lines = ["🎲 *dlce BASE bot — Admin Panel*", ""]

        lines.append("📊 *Usage Stats*")
        lines.append(f"Total searches: {total_searches}")
        lines.append(f"Unique users: {unique_users}")
        lines.append("")

        lines.append("🏰 *Top TH Levels*")
        for th, cnt in top_th:
            lines.append(f"  TH{th}: {cnt} searches")
        lines.append("")

        lines.append("🎯 *Top Purposes*")
        for pur, cnt in top_pur:
            lines.append(f"  {pur}: {cnt} searches")
        lines.append("")

        lines.append("✅ *Top Rated Bases*")
        for b in good_bases[:5]:
            up   = b.get("thumbs_up",0)
            down = b.get("thumbs_down",0)
            if up + down == 0: continue
            pct  = int(up/(up+down)*100)
            lines.append(f"  TH{b.get('th_level')} {b.get('purpose')} — {pct}% defence rate ({up}✅ {down}❌)")
            lines.append(f"  {b.get('source','?')} | score {b.get('score','?')}")
        lines.append("")

        lines.append("⚠️ *Reported Bad Bases (last 10)*")
        for r in bad_bases[:5]:
            lines.append(f"  {r.get('reason','?')} — {r.get('source','?')} TH{r.get('th_level')} {r.get('purpose','?')}")
            lines.append(f"  {(r.get('link') or '')[:55]}")

        msg = chr(10).join(lines)
        # Split if too long
        if len(msg) > 4000:
            msg = msg[:4000] + "\n...(truncated)"

        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"Admin error: {e}")

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

    if not picked:
        await context.bot.send_message(
            chat_id=send_to,
            text=t(lang,"no_results")
        )
        return ConversationHandler.END

    # Deep Research button
    dk = f"{th}_{purpose}_{lang}"
    await context.bot.send_message(
        chat_id=send_to,
        text="─"*22,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(t(lang,"deep_btn"), callback_data=f"deep_{dk}")
        ]])
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
    from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats
    private_cmds = [
        BotCommand("start",    "🏰 Find a base"),
        BotCommand("language", "🌍 Change language"),
        BotCommand("help",     "❓ How to use"),
    ]
    group_cmds = [
        BotCommand("start",    "🏰 Find a base (results in DM)"),
        BotCommand("help",     "❓ How to use"),
    ]
    await app.bot.set_my_commands(private_cmds, scope=BotCommandScopeAllPrivateChats())
    await app.bot.set_my_commands(group_cmds,   scope=BotCommandScopeAllGroupChats())


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start",    group_start),
                      CommandHandler("language", language_cmd)],
        states={
            LANG:     [CallbackQueryHandler(language_chosen, pattern="^lang_")],
            TH_LEVEL: [CallbackQueryHandler(th_chosen,       pattern="^th_")],
            PURPOSE:  [CallbackQueryHandler(purpose_chosen,  pattern="^purpose_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("help",     help_cmd))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CommandHandler("admin",    admin_panel))
    app.add_handler(CallbackQueryHandler(feedback_handler, pattern="^fb_"))
    app.add_handler(CallbackQueryHandler(feedback_handler, pattern="^rp_"))
    app.add_handler(CallbackQueryHandler(deep_handler,     pattern="^deep_"))
    logger.info("dlce BASE bot v6.0 starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
