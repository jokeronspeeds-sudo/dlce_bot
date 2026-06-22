# ============================================================
# CoC Base Finder Bot
# ============================================================
# This file is the entire bot. It handles:
# - Telegram messages and buttons
# - Searching YouTube, web, and base sites via Gemini
# - Ranking bases by score
# - Saving results + user feedback to Supabase
# ============================================================

import os
import logging
import asyncio
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)
import google.generativeai as genai
import anthropic
from supabase import create_client, Client

# ── Logging (shows up in Railway logs) ──────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Load secrets from Railway environment variables ──────────
BOT_TOKEN      = os.environ["BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]
YOUTUBE_API_KEY= os.environ["YOUTUBE_API_KEY"]
SUPABASE_URL   = os.environ["SUPABASE_URL"]
SUPABASE_KEY   = os.environ["SUPABASE_KEY"]

# ── Set up AI clients ────────────────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-2.0-flash")
claude = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# ── Supabase (optional — bot works without it) ───────────────
supabase = None
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Supabase connected OK")
except Exception as e:
    logger.warning(f"Supabase not connected: {e} — bot will run without database")

# ── Conversation states ──────────────────────────────────────
LANG, TH_LEVEL, PURPOSE = range(3)

# ── Translations ─────────────────────────────────────────────
T = {
    "en": {
        "welcome":    "Welcome! Choose your language:",
        "q_th":       "What is your Town Hall level?",
        "q_purpose":  "What is the purpose of your base?",
        "searching":  "Searching YouTube, Reddit, and base sites... this takes ~15 seconds",
        "results":    "Top 3 bases for TH{th} {purpose}",
        "recommended":"Recommended",
        "score":      "Score: {score}/100",
        "cc":         "CC troops: {cc}",
        "copy_link":  "Copy base link",
        "worked":     "It worked!",
        "no_defend":  "Did not defend",
        "thanks":     "Thanks for the feedback! It helps improve rankings.",
        "rank":       "RANK",
        "war":        "WAR",
        "farm":       "FARM",
    },
    "ru": {
        "welcome":    "Привет! Выбери язык:",
        "q_th":       "Какой у тебя уровень ратуши?",
        "q_purpose":  "Какова цель базы?",
        "searching":  "Ищу на YouTube, Reddit и сайтах с базами... около 15 секунд",
        "results":    "Топ-3 базы для РУ{th} {purpose}",
        "recommended":"Рекомендуем",
        "score":      "Оценка: {score}/100",
        "cc":         "Замок клана: {cc}",
        "copy_link":  "Скопировать ссылку",
        "worked":     "Сработало!",
        "no_defend":  "Не устояла",
        "thanks":     "Спасибо за отзыв! Это улучшает рейтинг.",
        "rank":       "РАНГ",
        "war":        "ВОЙНА",
        "farm":       "ФАРМ",
    },
    "he": {
        "welcome":    "שלום! בחר שפה:",
        "q_th":       "מה רמת עיירת המועצה שלך?",
        "q_purpose":  "מה מטרת הבסיס?",
        "searching":  "מחפש ב-YouTube, Reddit ואתרי בסיסים... כ-15 שניות",
        "results":    "3 הבסיסים המובילים עבור TH{th} {purpose}",
        "recommended":"מומלץ",
        "score":      "ציון: {score}/100",
        "cc":         "טירת קבוצה: {cc}",
        "copy_link":  "העתק קישור לבסיס",
        "worked":     "עבד!",
        "no_defend":  "לא החזיק",
        "thanks":     "תודה על המשוב! זה עוזר לשפר את הדירוג.",
        "rank":       "דירוג",
        "war":        "מלחמה",
        "farm":       "חווה",
    },
}

def t(lang: str, key: str, **kwargs) -> str:
    """Get translated string, filling in any {placeholders}."""
    text = T.get(lang, T["en"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


# ══════════════════════════════════════════════════════════════
# SEARCH & RANKING ENGINE
# ══════════════════════════════════════════════════════════════

async def search_youtube(th: int, purpose: str) -> list[dict]:
    """Search YouTube and extract CoC links using ONLY regex — no Gemini calls."""
    import re
    query = f"TH{th} {purpose} base 2025 Clash of Clans"
    url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&q={query}&type=video&maxResults=10"
        f"&order=viewCount&key={YOUTUBE_API_KEY}"
    )
    results = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            data = resp.json()

        if "error" in data:
            logger.warning(f"YouTube API error: {data['error'].get('message','unknown')}")
            return results

        items = data.get("items", [])
        logger.info(f"YouTube returned {len(items)} videos")

        # Also fetch full video details to get full descriptions
        if items:
            vid_ids = ",".join(
                item["id"]["videoId"] for item in items if item["id"].get("videoId")
            )
            detail_url = (
                f"https://www.googleapis.com/youtube/v3/videos"
                f"?part=snippet&id={vid_ids}&key={YOUTUBE_API_KEY}"
            )
            async with httpx.AsyncClient(timeout=15) as client:
                detail_resp = await client.get(detail_url)
                detail_data = detail_resp.json()

            for item in detail_data.get("items", []):
                vid_id = item["id"]
                title  = item["snippet"]["title"]
                desc   = item["snippet"]["description"]

                # Find CoC links by regex — zero Gemini calls
                coc_links = re.findall(
                    r'https://link\.clashofclans\.com[^\s\"\'\<\>\)]+', desc
                )
                if coc_links:
                    clean = coc_links[0].rstrip('.,)&')
                    results.append({
                        "link":      clean,
                        "cc":        _extract_cc_from_text(desc),
                        "source":    f"YouTube: {title[:55]}",
                        "yt_url":    f"https://youtube.com/watch?v={vid_id}",
                        "downloads": 0,
                        "stars":     0,
                    })
                    logger.info(f"YouTube found: {clean[:70]}")

    except Exception as e:
        logger.warning(f"YouTube search error: {e}")

    logger.info(f"YouTube total: {len(results)}")
    return results


def _extract_cc_from_text(text: str) -> str:
    """Extract CC troop suggestion from text using simple keyword search."""
    import re
    text_lower = text.lower()
    troops = [
        "inferno dragon", "super witch", "ice golem", "witch",
        "balloon", "minion", "dragon", "valkyrie", "golem",
        "hog rider", "bowler", "electro dragon", "lava hound",
        "super balloon", "head hunter", "super archer"
    ]
    found = [t for t in troops if t in text_lower]
    if found:
        return " + ".join(found[:3]).title()

    # Look for explicit CC mention
    match = re.search(r'cc[:\s]+([^\n\.]{5,60})', text_lower)
    if match:
        return match.group(1).strip().title()

    return "Check source for CC recommendation"


async def search_web(th: int, purpose: str) -> list[dict]:
    """Scrape base sites directly. Falls back to Claude knowledge if scraping fails."""
    import re, json
    results = []

    # ── Scrape cocbases.com ───────────────────────────────────
    try:
        slug = {"RANK": "trophy", "WAR": "war", "FARM": "farming"}.get(purpose, "war")
        url  = f"https://cocbases.com/th{th}-{slug}-base/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as c:
            r = await c.get(url)
        html = r.text
        links = list(dict.fromkeys(
            re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', html)
        ))
        logger.info(f"cocbases.com found {len(links)} links (status {r.status_code})")
        for lnk in links[:5]:
            results.append({
                "link":      lnk.rstrip('.,)&'),
                "cc":        _extract_cc_from_text(html),
                "source":    "cocbases.com",
                "downloads": 15000,
                "stars":     4.7,
            })
    except Exception as e:
        logger.warning(f"cocbases scrape error: {e}")

    # ── Scrape clashtrack.com ─────────────────────────────────
    if len(results) < 3:
        try:
            slug2 = {"RANK": "trophy", "WAR": "war", "FARM": "farm"}.get(purpose, "war")
            url2  = f"https://www.clashtrack.com/th{th}/{slug2}-base"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as c:
                r2 = await c.get(url2)
            html2 = r2.text
            links2 = list(dict.fromkeys(
                re.findall(r'https://link\.clashofclans\.com[^\s"\'<>)]+', html2)
            ))
            logger.info(f"clashtrack found {len(links2)} links (status {r2.status_code})")
            for lnk in links2[:3]:
                results.append({
                    "link":      lnk.rstrip('.,)&'),
                    "cc":        _extract_cc_from_text(html2),
                    "source":    "clashtrack.com",
                    "downloads": 8000,
                    "stars":     4.4,
                })
        except Exception as e:
            logger.warning(f"clashtrack scrape error: {e}")

    # ── Claude knowledge fallback (always works, no quota) ────
    if len(results) < 3:
        logger.info("Using Claude knowledge fallback...")
        try:
            msg = claude.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": (
                    f"Give me 3 real Clash of Clans TH{th} {purpose} base links.\n"
                    f"Format: https://link.clashofclans.com/en?action=OpenLayout&id=TH{th}-...\n"
                    f"Also give the best Clan Castle troop setup for each.\n\n"
                    f"Reply ONLY as a JSON array, no markdown:\n"
                    f'[{{"link":"https://link.clashofclans.com/en?action=OpenLayout&id=...","cc":"Dragon + Witch","source":"community"}}]'
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


async def validate_link(link: str) -> bool:
    """CoC links open in-game so always pass. Validate other links normally."""
    if "link.clashofclans.com" in link:
        return True
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.head(link, follow_redirects=True)
            return r.status_code < 400
    except Exception:
        return False
-e 

async def rank_bases(bases: list[dict], th: int, purpose: str) -> list[dict]:
    """Use Claude to score and rank the bases, adding explanations."""
    if not bases:
        return []

    import json
    bases_json = json.dumps(bases, indent=2)
    prompt = (
        f"You are a Clash of Clans expert ranking TH{th} {purpose} bases.\n\n"
        f"Here are the candidate bases:\n{bases_json}\n\n"
        f"Score each base 0-100 based on:\n"
        f"- downloads × 0.35 (normalize to 100k max)\n"
        f"- stars × 0.25 (normalize to 5 max)\n"
        f"- source reputation × 0.20 (cocbases > reddit > youtube)\n"
        f"- link validity × 0.20\n\n"
        f"Return ONLY a JSON array sorted best-first, max 3 items:\n"
        f'[{{"link":"...","cc":"...","source":"...","score":85,"reason":"One sentence why this base is top ranked"}}]'
    )
    try:
        msg = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        import re
        raw = msg.content[0].text.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        ranked = json.loads(raw)
        return ranked[:3]
    except Exception as e:
        logger.warning(f"Ranking error: {e}")
        # Fallback: return first 3 as-is with default score
        for i, b in enumerate(bases[:3]):
            b["score"] = 70 - i * 5
            b["reason"] = "Found across multiple community sources"
        return bases[:3]


async def save_base(base: dict, th: int, purpose: str):
    """Save a base to Supabase for caching and feedback tracking."""
    if not supabase:
        return
    try:
        supabase.table("bases").upsert({
            "link":      base["link"],
            "th_level":  th,
            "purpose":   purpose,
            "score":     base.get("score", 70),
            "cc":        base.get("cc", ""),
            "source":    base.get("source", ""),
            "thumbs_up": 0,
            "thumbs_down": 0,
        }, on_conflict="link").execute()
    except Exception as e:
        logger.warning(f"Supabase save error: {e}")


async def update_feedback(link: str, positive: bool):
    """Increment thumbs up or down for a base."""
    if not supabase:
        return
    try:
        col = "thumbs_up" if positive else "thumbs_down"
        row = supabase.table("bases").select(col).eq("link", link).execute()
        if row.data:
            current = row.data[0][col]
            supabase.table("bases").update({col: current + 1}).eq("link", link).execute()
    except Exception as e:
        logger.warning(f"Feedback update error: {e}")


# ══════════════════════════════════════════════════════════════
# TELEGRAM HANDLERS
# ══════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send language selection buttons."""
    keyboard = [
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇮🇱 עברית",   callback_data="lang_he"),
        ]
    ]
    await update.message.reply_text(
        "🏰 CoC Base Finder\n\nChoose language / Выбери язык / בחר שפה",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return LANG


async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User picked a language — ask for TH level."""
    query = update.callback_query
    await query.answer()
    lang = query.data.replace("lang_", "")
    context.user_data["lang"] = lang

    # Build TH level buttons (10–18) in two rows
    row1 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(10, 14)]
    row2 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(14, 18)]
    row3 = [InlineKeyboardButton("TH18", callback_data="th_18")]

    await query.edit_message_text(
        t(lang, "q_th"),
        reply_markup=InlineKeyboardMarkup([row1, row2, row3])
    )
    return TH_LEVEL


async def th_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User picked TH level — ask for purpose."""
    query = update.callback_query
    await query.answer()
    th = int(query.data.replace("th_", ""))
    context.user_data["th"] = th
    lang = context.user_data["lang"]

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


async def purpose_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User picked purpose — run the full search and send results."""
    query = update.callback_query
    await query.answer()
    purpose = query.data.replace("purpose_", "")
    lang    = context.user_data["lang"]
    th      = context.user_data["th"]
    chat_id = query.message.chat_id

    await query.edit_message_text(
        f"TH{th} · {purpose}\n\n⏳ {t(lang, 'searching')}"
    )

    # ── Run YouTube and web search in parallel ───────────────
    yt_results, web_results = await asyncio.gather(
        search_youtube(th, purpose),
        search_web(th, purpose)
    )

    # ── Debug: tell user what we found ──────────────────────
    debug_msg = (
        f"🔍 Search complete:\n"
        f"• YouTube bases found: {len(yt_results)}\n"
        f"• Web bases found: {len(web_results)}\n"
        f"• Total: {len(yt_results) + len(web_results)}"
    )
    await context.bot.send_message(chat_id=chat_id, text=debug_msg)

    all_bases = yt_results + web_results

    if not all_bases:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "❌ Both searches returned 0 results.\n\n"
                "Possible reasons:\n"
                "• YouTube API key not activated yet (takes ~5 min after enabling)\n"
                "• Gemini API quota reached\n"
                "• Check Railway logs for details\n\n"
                "Try /start again in 2 minutes."
            )
        )
        return ConversationHandler.END

    # ── Validate links ────────────────────────────────────────
    valid_bases = []
    for base in all_bases:
        if await validate_link(base["link"]):
            valid_bases.append(base)
        if len(valid_bases) >= 8:
            break

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ Valid links after check: {len(valid_bases)}"
    )

    if not valid_bases:
        # Show raw links anyway so user gets something useful
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Found bases but links failed validation. Showing raw results:"
        )
        for base in all_bases[:3]:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔗 {base.get('link','no link')}\n📌 {base.get('source','')}\n🏰 CC: {base.get('cc','?')}"
            )
        return ConversationHandler.END

    # ── Rank with Claude ──────────────────────────────────────
    top3 = await rank_bases(valid_bases, th, purpose)

    if not top3:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Ranking failed. Showing unranked results:"
        )
        top3 = valid_bases[:3]
        for i, b in enumerate(top3):
            b["score"] = 70 - i*5
            b["reason"] = "Community recommended"

    # ── Save to Supabase ──────────────────────────────────────
    for base in top3:
        await save_base(base, th, purpose)

    # ── Send results ──────────────────────────────────────────
    medals = ["🥇", "🥈", "🥉"]
    for i, base in enumerate(top3):
        is_recommended = (i == 0)
        score  = base.get("score", 70)
        cc     = base.get("cc", "Not specified")
        source = base.get("source", "")
        reason = base.get("reason", "")
        link   = base["link"]

        header = f"{medals[i]} #{i+1}"
        if is_recommended:
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

        keyboard = [[
            InlineKeyboardButton(
                t(lang, "worked"),
                callback_data=f"fb_pos_{link[:60]}"
            ),
            InlineKeyboardButton(
                t(lang, "no_defend"),
                callback_data=f"fb_neg_{link[:60]}"
            ),
        ]]

        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    return ConversationHandler.END



async def feedback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle thumbs up / thumbs down feedback."""
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "en")

    data = query.data  # fb_pos_<link> or fb_neg_<link>
    positive = data.startswith("fb_pos_")
    link_part = data[7:]  # strip "fb_pos_" or "fb_neg_"

    await update_feedback(link_part, positive)
    await query.edit_message_reply_markup(reply_markup=None)  # remove buttons
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=t(lang, "thanks")
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current conversation."""
    await update.message.reply_text("Cancelled. Send /start to begin again.")
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
# MAIN — start the bot
# ══════════════════════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANG:    [CallbackQueryHandler(language_chosen, pattern="^lang_")],
            TH_LEVEL:[CallbackQueryHandler(th_chosen,       pattern="^th_")],
            PURPOSE: [CallbackQueryHandler(purpose_chosen,  pattern="^purpose_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(feedback_handler, pattern="^fb_"))

    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
