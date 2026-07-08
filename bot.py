--- /mnt/user-data/uploads/bot.py	2026-07-08 22:28:50.549314000 +0000
+++ bot.py	2026-07-08 22:47:35.603452304 +0000
@@ -1,4 +1,4 @@
-# dlce BASE bot v7.2
+# dlce BASE bot v7.3
 import os, logging, asyncio, re, json, hashlib, httpx
 from io import BytesIO
 from datetime import datetime, timezone
@@ -21,7 +21,16 @@
 YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
 SUPABASE_URL    = os.environ["SUPABASE_URL"]
 SUPABASE_KEY    = os.environ["SUPABASE_KEY"]
-ADMIN_ID        = int(os.environ.get("ADMIN_ID", "0"))  # your Telegram user ID
+ADMIN_ID        = int(os.environ.get("ADMIN_ID", "0"))  # your Telegram user ID (kept for display/back-compat)
+# ADMIN_ID (or ADMIN_IDS) may be a single ID or a comma-separated list, so more
+# than one clan leader/co-leader can reach the admin panel. If nothing valid is
+# configured this is an empty set, which means the panel denies EVERYONE by
+# default (previous behaviour silently let everyone in when unset — see admin_panel).
+ADMIN_IDS = {
+    int(x) for x in
+    (os.environ.get("ADMIN_IDS") or os.environ.get("ADMIN_ID") or "").replace(" ", "").split(",")
+    if x.strip().lstrip("-").isdigit()
+}
 
 genai.configure(api_key=GEMINI_API_KEY)
 gemini = genai.GenerativeModel("gemini-2.0-flash")
@@ -482,7 +491,8 @@
     results = []
     try:
         pkw = {"WAR":"war base layout anti 3star","RANK":"trophy base layout","FARM":"farming base layout"}
-        q   = f"TH{th} {pkw.get(purpose,'base layout')} 2025 Clash of Clans copy link"
+        this_year = datetime.now(timezone.utc).year
+        q   = f"TH{th} {pkw.get(purpose,'base layout')} {this_year} Clash of Clans copy link"
         url = (f"https://www.googleapis.com/youtube/v3/search"
                f"?part=snippet&q={quote_plus(q)}&type=video&maxResults={max_results}"
                f"&order={order}&key={YOUTUBE_API_KEY}")
@@ -734,9 +744,19 @@
 async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
     """Admin-only command — shows usage stats, feedback table, bad bases."""
     user_id = update.effective_user.id
-    logger.info(f"Admin command from user_id={user_id}, ADMIN_ID={ADMIN_ID}")
-    if ADMIN_ID and user_id != ADMIN_ID:
-        await update.message.reply_text(f"Access denied. Your ID: {user_id}")
+    logger.info(f"Admin command from user_id={user_id}, ADMIN_IDS={ADMIN_IDS or '(none configured)'}")
+    if user_id not in ADMIN_IDS:
+        if not ADMIN_IDS:
+            await update.message.reply_text(
+                "⚠️ Admin panel isn't configured yet.\n\n"
+                f"Your Telegram ID is: `{user_id}`\n"
+                "Add it as the ADMIN_ID (or ADMIN_IDS, comma-separated for "
+                "multiple admins) environment variable in Railway, then "
+                "redeploy.",
+                parse_mode="Markdown"
+            )
+        else:
+            await update.message.reply_text(f"Access denied. Your Telegram ID: {user_id}")
         return
 
     from collections import Counter
@@ -820,10 +840,10 @@
 
     # ── Bot status (always shown) ─────────────────────────────
     lines.append("🤖 *Bot Status*")
-    lines.append(f"  Version: v6.2")
+    lines.append(f"  Version: v7.3")
     lines.append(f"  Database: {'✅ Connected' if supabase else '❌ Not connected'}")
     lines.append(f"  YouTube API: configured")
-    lines.append(f"  Admin ID: {ADMIN_ID}")
+    lines.append(f"  Admin IDs: {', '.join(str(i) for i in ADMIN_IDS) or '(none configured)'}")
 
     msg = chr(10).join(lines)
     if len(msg) > 4000:
@@ -1439,6 +1459,64 @@
         )
         return GUIDE_TOPIC
 
+
+# ══════════════════════════════════════════════════════════════
+# QUICK-ACCESS ENTRY POINTS — /basefinder and /guides
+# Let users jump straight past Language + Category screens.
+# Registered as BOTH entry_points and fallbacks on the conv
+# handler so they work whether or not a conversation is already
+# active (see main() for details).
+# ══════════════════════════════════════════════════════════════
+async def _redirect_if_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
+    """Shared group->DM redirect used by all quick-access entry points."""
+    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
+        lang = context.user_data.get("lang", "en")
+        bot_username = context.bot.username
+        await update.message.reply_text(
+            t(lang, "group_msg"),
+            reply_markup=InlineKeyboardMarkup([[
+                InlineKeyboardButton(
+                    t(lang, "open_dm"),
+                    url=f"https://t.me/{bot_username}?start=from_group"
+                )
+            ]])
+        )
+        return True
+    return False
+
+
+async def quick_basefinder(update: Update, context: ContextTypes.DEFAULT_TYPE):
+    """/basefinder command — jump straight to TH level selection."""
+    if await _redirect_if_group(update, context):
+        return ConversationHandler.END
+
+    lang = context.user_data.get("lang", "en")
+    context.user_data.pop("th", None)
+    context.user_data.pop("purpose", None)
+    row1 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(10, 14)]
+    row2 = [InlineKeyboardButton(f"TH{i}", callback_data=f"th_{i}") for i in range(14, 18)]
+    row3 = [InlineKeyboardButton("TH18",   callback_data="th_18")]
+    await update.message.reply_text(t(lang, "q_th"), reply_markup=InlineKeyboardMarkup([row1, row2, row3]))
+    return TH_LEVEL
+
+
+async def quick_guides(update: Update, context: ContextTypes.DEFAULT_TYPE):
+    """/guides command — jump straight to guide topic selection."""
+    if await _redirect_if_group(update, context):
+        return ConversationHandler.END
+
+    lang = context.user_data.get("lang", "en")
+    keyboard = [[
+        InlineKeyboardButton(t(lang, "guide_attack"), callback_data="guide_attack"),
+        InlineKeyboardButton(t(lang, "guide_bh"),     callback_data="guide_bh"),
+    ], [
+        InlineKeyboardButton(t(lang, "guide_equip"),  callback_data="guide_equip"),
+        InlineKeyboardButton(t(lang, "guide_web"),    callback_data="guide_web"),
+    ]]
+    await update.message.reply_text(t(lang, "q_guide_topic"), reply_markup=InlineKeyboardMarkup(keyboard))
+    return GUIDE_TOPIC
+
+
 async def guide_topic_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
     """User chose a guide topic."""
     query = update.callback_query
@@ -1758,7 +1836,9 @@
 
 
 async def back_to_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
-    """Handle back to main menu — sends a fresh message so conversation resets."""
+    """Handle back to main menu — sends a fresh message and re-enters the
+    conversation at CATEGORY so the next tap (cat_bases/cat_guides) is
+    actually picked up by category_chosen instead of being dropped."""
     query = update.callback_query
     await query.answer()
     lang = context.user_data.get("lang","en")
@@ -1775,6 +1855,12 @@
     # Reset conversation state by clearing user data partially
     context.user_data.pop("th", None)
     context.user_data.pop("purpose", None)
+    # IMPORTANT: this handler is registered on the ConversationHandler
+    # itself (entry_points + fallbacks). Returning CATEGORY tells PTB's
+    # internal state tracker that this user is now "in" CATEGORY, so the
+    # cat_bases/cat_guides tap that follows is routed to category_chosen
+    # instead of falling through to nothing (the old freeze bug).
+    return CATEGORY
 
 
 async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
@@ -1868,14 +1954,18 @@
     """Set bot commands menu shown in Telegram UI."""
     from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats
     private_cmds = [
-        BotCommand("start",    "🎲 Base Finder + Guides"),
-        BotCommand("language", "🌍 Change language"),
-        BotCommand("help",     "❓ How the bot works"),
-        BotCommand("admin",    "🔐 Admin panel"),
+        BotCommand("start",      "🎲 Base Finder + Guides"),
+        BotCommand("basefinder", "🏰 Base Finder (skip straight to TH pick)"),
+        BotCommand("guides",     "📖 Guides (skip straight to topics)"),
+        BotCommand("language",   "🌍 Change language"),
+        BotCommand("help",       "❓ How the bot works"),
+        BotCommand("admin",      "🔐 Admin panel"),
     ]
     group_cmds = [
-        BotCommand("start",    "🎲 Base Finder + Guides (results in DM)"),
-        BotCommand("help",     "❓ How the bot works"),
+        BotCommand("start",      "🎲 Base Finder + Guides (results in DM)"),
+        BotCommand("basefinder", "🏰 Base Finder (results in DM)"),
+        BotCommand("guides",     "📖 Guides (results in DM)"),
+        BotCommand("help",       "❓ How the bot works"),
     ]
     await app.bot.set_my_commands(private_cmds, scope=BotCommandScopeAllPrivateChats())
     await app.bot.set_my_commands(group_cmds,   scope=BotCommandScopeAllGroupChats())
@@ -1886,9 +1976,35 @@
 # ══════════════════════════════════════════════════════════════
 def main():
     app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
+
+    # ── FIX NOTES (v7.3) ──────────────────────────────────────────
+    # Root cause of BOTH "freeze" bugs was the same pattern: a button/
+    # command that's meant to re-enter the conversation flow (🌍 change
+    # language mid-flow, 🏠 Main Menu, /basefinder, /guides) was wired
+    # up as a *separate* top-level handler outside the ConversationHandler.
+    # PTB tracks conversation state internally per user; a handler that
+    # lives outside `conv` can display a screen but can't update that
+    # internal state. The next tap then gets checked against the *real*
+    # (unchanged/cleared) state, matches nothing, and is silently
+    # dropped — which looks exactly like a freeze (button spinner never
+    # resolves, bot appears dead).
+    #
+    # Fix: every handler that needs to (re)start or jump around the flow
+    # is registered on `conv` itself, in BOTH `entry_points` (fires when
+    # no conversation is currently active — e.g. right after a guide or
+    # base results ended it) AND `fallbacks` (fires when a conversation
+    # IS active in some other state — e.g. user opens /language via the
+    # command menu mid-flow). That way PTB always keeps its internal
+    # state in sync with whatever screen the user is actually looking at.
+    restart_entries = [
+        CommandHandler("start",       group_start),
+        CommandHandler("language",    language_cmd),
+        CommandHandler("basefinder",  quick_basefinder),
+        CommandHandler("guides",      quick_guides),
+        CallbackQueryHandler(back_to_main_handler, pattern="^back_to_main"),
+    ]
     conv = ConversationHandler(
-        entry_points=[CommandHandler("start",    group_start),
-                      CommandHandler("language", language_cmd)],
+        entry_points=restart_entries,
         states={
             LANG:            [CallbackQueryHandler(language_chosen,        pattern="^lang_")],
             CATEGORY:        [CallbackQueryHandler(category_chosen,        pattern="^cat_")],
@@ -1897,17 +2013,19 @@
             GUIDE_TOPIC:     [CallbackQueryHandler(guide_topic_chosen,     pattern="^guide_")],
             GUIDE_ATTACK_TH: [CallbackQueryHandler(guide_attack_th_chosen, pattern="^atk_")],
         },
-        fallbacks=[CommandHandler("cancel", cancel)],
+        # Same handlers again as fallbacks: fallbacks are only checked
+        # while a conversation is ACTIVE (state != None), entry_points
+        # only when it's NOT (state == None) — we need both to cover
+        # every point where a user might hit one of these buttons/commands.
+        fallbacks=[CommandHandler("cancel", cancel)] + restart_entries,
     )
     app.add_handler(conv)
     app.add_handler(CommandHandler("help",     help_cmd))
-    app.add_handler(CommandHandler("language", language_cmd))
     app.add_handler(CommandHandler("admin",    admin_panel))
     app.add_handler(CallbackQueryHandler(feedback_handler,    pattern="^fb_"))
     app.add_handler(CallbackQueryHandler(feedback_handler,    pattern="^rp_"))
     app.add_handler(CallbackQueryHandler(deep_handler,        pattern="^deep_"))
-    app.add_handler(CallbackQueryHandler(back_to_main_handler,pattern="^back_to_main"))
-    logger.info("dlce BASE bot v7.2 starting...")
+    logger.info("dlce BASE bot v7.3 starting...")
     app.run_polling(allowed_updates=Update.ALL_TYPES)
 
 if __name__ == "__main__":
