import os
import logging
import asyncio
import re
import json
import hashlib
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)
import google.generativeai as genai
import anthropic
from supabase import create_client, Client

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
    logger.warning(f"Supabase not connected: {e} — bot will run without database")

LANG, TH_LEVEL, PURPOSE = range(3)

T = {
    "en": {
        "welcome":    "Welcome! Choose your language:",
        "q_th":       "What is your Town Hall level?",
        "q_purpose":  "What is the purpose of your base?",
        "searching":  "Searching YouTube, Reddit and base sites... ~15 seconds",
        "recommended":"Recommended",
        "score":      "Score: {score}/100",
        "cc":         "CC troops: {cc}",
        "worked":     "It worked!",
        "no_defend":  "Did not defend",
        "thanks":     "Thanks! This helps improve rankings.",
        "rank":       "RANK",
        "war":        "WAR",
        "farm":       "FARM",
    },
    "ru": {
        "welcome":    "Привет! Выбери язык:",
        "q_th":       "Какой у тебя уровень ратуши?",
        "q_purpose":  "Какова цель базы?",
        "searching":  "Ищу на YouTube, Reddit и сайтах с базами... ~15 секунд",
        "recommended":"Рекомендуем",
        "score":      "Оценка: {score}/100",
        "cc":         "Замок клана: {cc}",
        "worked":     "Сработало!",
        "no_defend":  "Не устояла",
        "thanks":     "Спасибо! Это улучшает рейтинг.",
        "rank":       "РАНГ",
        "war":        "ВОЙНА",
        "farm":       "ФАРМ",
    },
    "he": {
        "welcome":    "שלום! בחר שפה:",
        "q_th":       "מה רמת עיירת המועצה שלך?",
        "q_purpose":  "מה מטרת הבסיס?",
        "searching":  "מחפש ב-YouTube, Reddit ואתרי בסיסים... ~15 שניות",
        "recommended":"מומלץ",
        "score":      "ציון: {score}/100",
        "cc":         "טירת קבוצה: {cc}",
        "worked":     "עבד!",
        "no_defend":  "לא החזיק",
        "thanks":     "תודה! זה עוזר לשפר את הדירוג.",
        "rank":       "דירוג",
        "war":        "מלחמה",
        "farm":       "חווה",
    },
}

def t(lang, key, **kwargs):
    text = T.get(lang, T["en"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def extract_cc(text):
    """Find troop names mentioned near 'cc' or 'clan castle' in text."""
    troops = [
        "inferno dragon", "super witch", "ice golem", "witch", "balloon",
        "minion", "dragon", "valkyrie", "golem", "hog rider", "bowler",
        "electro dragon", "lava hound", "super balloon", "head hunter",
        "super archer", "skeleton", "giant"
    ]
    low = text.lower()
    found = [tr for tr in troops if tr in low]
    if found:
        return " + ".join(found[:3]).title()
    m = re.search(r'cc[:\s]+([^\n.]{5,60})', low)
    if m:
        return m.group(1).strip().title()
    return "Check source for CC"


# ══════════════════════════════════════════════════════════════
# SEARCH ENGINE
# ══════════════════════════════════════════════════════════════

async def search_youtube(th, purpose):
    """Search YouTube Data API — extract CoC links with regex only, zero AI calls."""
    results = []
    try:
        query = f"TH{th} {purpose} base 2025 Clash of Clans"
        search_url = (
            f"https://www.googleapis.com/youtube/v3/search"
            f"?part=snippet&q={query}&type=video&maxResults=10"
            f"&order=viewCount&key={YOUTUBE_API_KEY}"
        )
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(search_url)
            data = r.json()

        if "error" in data:
            logger.warning(f"YouTube API error: {data['error'].get('message','?')}")
            return results

        items = data.get("items", [])
        logger.info(f"YouTube search returned {len(items)} videos")

        if not items:
            return results

        # Fetch full descriptions via videos endpoint
        vid_ids = ",".join(
            i["id"]["videoId"] for i in items if i["id"].get("videoId")
        )
        detail_url = (
            f"https://www.googleapis.com/youtube/v3/videos"
            f"?part=snippet&id={vid_ids}&key={YOUTUBE_API_KEY}"
        )
        async with httpx.AsyncClient(timeout=15) as c:
            dr = await c.get(detail_url)
            ddata = dr.json()

        for item in ddata.get("items", []):
            vid_id = item["id"]
            title  = item["snippet"]["title"]
            desc   = item["snippet"]["description"]
            links  = re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', desc)
            if links and f"TH{th}" in clean.upper() or (links and "TH" not in desc.upper()[:200]):
                clean = links[0].rstrip(".,)&")
                results.append({
                    "link":      clean,
                    "cc":        extract_cc(desc),
                    "source":    f"YouTube: {title[:55]}",
                    "downloads": 0,
                    "stars":     0,
                })
                logger.info(f"YouTube found link: {clean[:70]}")

    except Exception as e:
        logger.warning(f"YouTube error: {e}")

    logger.info(f"YouTube total: {len(results)}")
    return results


async def search_web(th, purpose):
    """Scrape base sites directly. Falls back to Claude knowledge."""
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # ── cocbases.com ─────────────────────────────────────────
    try:
        slug = {"RANK": "trophy", "WAR": "war", "FARM": "farming"}.get(purpose, "war")
        url  = f"https://cocbases.com/th{th}-{slug}-base/"
        async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as c:
            r = await c.get(url)
        html = r.text
        links = list(dict.fromkeys(
            re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', html)
        ))
        logger.info(f"cocbases.com: status={r.status_code} links={len(links)}")
        for lnk in links[:5]:
            results.append({
                "link":      lnk.rstrip(".,)&"),
                "cc":        extract_cc(html),
                "source":    "cocbases.com",
                "downloads": 15000,
                "stars":     4.7,
            })
    except Exception as e:
        logger.warning(f"cocbases error: {e}")

    # ── clashtrack.com ────────────────────────────────────────
    if len(results) < 3:
        try:
            slug2 = {"RANK": "trophy", "WAR": "war", "FARM": "farm"}.get(purpose, "war")
            url2  = f"https://www.clashtrack.com/th{th}/{slug2}-base"
            async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as c:
                r2 = await c.get(url2)
            html2 = r2.text
            links2 = list(dict.fromkeys(
                re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', html2)
            ))
            logger.info(f"clashtrack.com: status={r2.status_code} links={len(links2)}")
            for lnk in links2[:3]:
                results.append({
                    "link":      lnk.rstrip(".,)&"),
                    "cc":        extract_cc(html2),
                    "source":    "clashtrack.com",
                    "downloads": 8000,
                    "stars":     4.4,
                })
        except Exception as e:
            logger.warning(f"clashtrack error: {e}")

    # ── Claude knowledge fallback ─────────────────────────────
    if len(results) < 3:
        logger.info("Using Claude knowledge fallback...")
        try:
            msg = claude.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": (
                    f"Give me 3 real Clash of Clans TH{th} {purpose} base copy links.\n"
                    f"Links must start with: https://link.clashofclans.com/en?action=OpenLayout&id=\n"
                    f"Also provide the best Clan Castle troop setup for each base.\n\n"
                    f"Reply ONLY as a JSON array, no markdown, no extra text:\n"
                    f'[{{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=TH{th}-...","cc":"Dragon + Witch + Balloon","source":"community"}}]'
                )}]
            )
            raw = re.sub(r"```json|```", "", msg.content[0].text).strip()
            m = re.search(r'\[.*?\]', raw, re.DOTALL)
            if m:
                for item in json.loads(m.group()):
                    if item.get("link"):
                        item.setdefault("downloads", 5000)
                        item.setdefault("stars", 4.0)
                        results.append(item)
                        logger.info(f"Claude fallback: {item['link'][:70]}")
        except Exception as e:
            logger.warning(f"Claude fallback error: {e}")

    logger.info(f"Web search total: {len(results)}")
    return results


def validate_link(link):
    """CoC links open in-game — always trust them."""
    return "clashofclans.com" in link


async def rank_bases(bases, th, purpose):
    """Use Claude to score and rank bases."""
    if not bases:
        return []
    try:
        msg = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": (
                f"You are a Clash of Clans expert. Rank these TH{th} {purpose} bases.\n\n"
                f"Bases:\n{json.dumps(bases, indent=2)}\n\n"
                f"Score each 0-100 based on downloads, stars, and source reputation.\n"
                f"cocbases.com and YouTube from known creators = higher score.\n\n"
                f"Return ONLY a JSON array, best first, max 3 items:\n"
                f'[{{"link":"...","cc":"...","source":"...","score":85,"reason":"Why this base is top ranked in one sentence"}}]'
            )}]
        )
        raw = re.sub(r"```json|```", "", msg.content[0].text).strip()
        m = re.search(r'\[.*?\]', raw, re.DOTALL)
        if m:
            ranked = json.loads(m.group())
            return ranked[:3]
    except Exception as e:
        logger.warning(f"Ranking error: {e}")

    # Fallback: return first 3 unranked
    for i, b in enumerate(bases[:3]):
        b["score"] = 75 - i * 5
        b["reason"] = "Community recommended base"
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

    # Run both searches in parallel
    yt_results, web_results = await asyncio.gather(
        search_youtube(th, purpose),
        search_web(th, purpose)
    )

    all_bases = yt_results + web_results
    logger.info(f"Total bases before validate: {len(all_bases)}")

    # Filter valid links
    valid = [b for b in all_bases if validate_link(b["link"])]
    logger.info(f"Valid bases: {len(valid)}")

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔍 Found: YouTube={len(yt_results)} Web={len(web_results)} Valid={len(valid)}"
    )

    if not valid:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ No bases found. Check Railway logs for details. Try /start again."
        )
        return ConversationHandler.END

    # Rank with Claude
    top3 = await rank_bases(valid, th, purpose)

    # Save to DB
    for base in top3:
        await save_base(base, th, purpose)

    # Send results
    medals = ["🥇", "🥈", "🥉"]
    for i, base in enumerate(top3):
        score  = base.get("score", 70)
        cc     = base.get("cc", "Not specified")
        source = base.get("source", "")
        reason = base.get("reason", "")
        link   = base["link"]

        header = f"{medals[i]} #{i+1}"
        if i == 0:
            header += f"  ⭐ {t(lang, 'recommended')}"

        text = (
            f"{header}\n"
            f"{t(lang, 'score', score=score)}\n"
            f"{t(lang, 'cc', cc=cc)}\n"
            f"📌 {source}\n"
        )
        if reason:
            text += f"💬 {reason}\n"
        text += f"\n🔗 {link}"

        # Store link in user_data, use short index in callback (Telegram 64 char limit)
        link_key = hashlib.md5(link.encode()).hexdigest()[:16]
        if "links" not in context.user_data:
            context.user_data["links"] = {}
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
    lang = context.user_data.get("lang", "en")
    positive = query.data.startswith("fb_pos_")
    link_key = query.data[7:]
    # Resolve short key back to full link
    link_part = context.user_data.get("links", {}).get(link_key, link_key)
    await update_feedback(link_part, positive)
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
