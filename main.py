import asyncio
import logging
import os
import re

import discord
from aiohttp import web
from discord.ext import commands

from config import AI_BASE_URL, AI_MODEL, CHARACTER_TOKENS, COMMAND_PREFIX
from engine.conversation import AIUnavailableError, generate_reply
from engine.memory import delete_memory, get_memories, initialize_database, save_memory, save_message
from engine.personality import load_character

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ddlc-bots")

intents = discord.Intents.default()
intents.message_content = True


def create_character_bot(character_name: str) -> commands.Bot:
    character = load_character(character_name)
    display_name = character["name"]
    bot = commands.Bot(
        command_prefix=COMMAND_PREFIX,
        intents=intents,
        help_command=None,
    )

    async def respond(channel, author, user_text):
        user_text = user_text.strip()
        if not user_text:
            return

        async with channel.typing():
            try:
                reply = await generate_reply(character_name, user_text, str(author.id))
            except AIUnavailableError:
                await channel.send(
                    "I'm online, but my AI connection hasn't been configured yet."
                )
                return
            except Exception:
                logger.exception("Reply generation failed for %s", character_name)
                await channel.send(
                    "Sorry! I couldn't reach the AI service just now. Please try again."
                )
                return

        save_message(character_name, str(author), user_text, str(author.id))
        save_message(character_name, display_name, reply, str(author.id))
        await channel.send(reply[:1900])

    @bot.event
    async def on_ready():
        logger.info(
            "%s is online as %s (ID: %s)",
            display_name,
            bot.user,
            bot.user.id,
        )
        logger.info(
            "AI provider configured: %s",
            bool(AI_BASE_URL and AI_MODEL),
        )

    @bot.command(name="chat")
    async def chat_command(ctx, *, message=""):
        await respond(ctx.channel, ctx.author, message)

    @bot.command(name="remember")
    async def remember_command(ctx, *, fact=""):
        fact = fact.strip()
        if not fact:
            await ctx.reply(f"Tell me what to remember! Example: {COMMAND_PREFIX}remember my favorite color is blue.", mention_author=False)
            return
        if len(fact) > 300:
            await ctx.reply("Could you shorten that to 300 characters or fewer?", mention_author=False)
            return
        memory_id = save_memory(character_name, str(ctx.author.id), "user_fact", fact)
        await ctx.reply(f"Got it! I'll remember that. (Memory #{memory_id})", mention_author=False)

    @bot.command(name="memories")
    async def memories_command(ctx):
        memories = get_memories(character_name, str(ctx.author.id), limit=20)
        if not memories:
            await ctx.reply("I don't have any saved memories about you yet. Try !remember <fact>!", mention_author=False)
            return
        lines = [f"**#{memory_id}** — {content}" for memory_id, _category, content, _timestamp in memories]
        await ctx.reply("Here's what I remember about you:\\n" + "\\n".join(lines), mention_author=False)

    @bot.command(name="forget")
    async def forget_command(ctx, memory_id: int = 0):
        if memory_id <= 0:
            await ctx.reply(f"Give me a memory number. Use {COMMAND_PREFIX}memories to see them.", mention_author=False)
            return
        if delete_memory(memory_id, str(ctx.author.id)):
            await ctx.reply("Okay! I've removed that saved memory.", mention_author=False)
        else:
            await ctx.reply("I couldn't find one of your memories with that number.", mention_author=False)

    @bot.command(name="help")
    async def help_command(ctx):
        await ctx.reply(
            f"**{display_name}**\n"
            f"{COMMAND_PREFIX}chat <message> — talk to {display_name}\n"
            f"{COMMAND_PREFIX}remember <fact> — save something for me to remember\n"
            f"{COMMAND_PREFIX}memories — see what I've saved about you\n"
            f"{COMMAND_PREFIX}forget <number> — delete one of your saved memories\n"
            f"You can also mention me followed by a message.",
            mention_author=False,
        )

    @bot.command(name="status")
    async def status_command(ctx):
        ai_ready = bool(AI_BASE_URL and AI_MODEL)
        await ctx.reply(
            f"{display_name} is online. AI mode: "
            f"**{'configured' if ai_ready else 'not configured yet'}**.",
            mention_author=False,
        )

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return

        # Each account only answers when directly mentioned, avoiding four
        # characters replying to every ordinary message in the server.
        if bot.user and bot.user in message.mentions:
            content = message.content
            content = re.sub(rf"<@!?{bot.user.id}>", "", content).strip()
            if content:
                await respond(message.channel, message.author, content)
                return

        await bot.process_commands(message)

    return bot


async def health_check(request):
    return web.Response(text="DDLC Discord bot service is running.")


async def start_health_server():
    # Render Web Services must listen on the port supplied in the PORT variable.
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000")),
    )
    await site.start()
    logger.info("Health-check web server is listening.")
    return runner


async def main():
    active_tokens = {
        name: token
        for name, token in CHARACTER_TOKENS.items()
        if token
    }
    if not active_tokens:
        raise RuntimeError(
            "No Discord bot tokens configured. Add at least SAYORI_TOKEN "
            "as an environment variable in Render."
        )

    missing = [
        name.title() for name, token in CHARACTER_TOKENS.items()
        if not token
    ]
    if missing:
        logger.info(
            "Not starting these characters yet (tokens not configured): %s",
            ", ".join(missing),
        )

    initialize_database()
    health_runner = await start_health_server()
    bots = {
        name: create_character_bot(name)
        for name in active_tokens
    }

    try:
        await asyncio.gather(
            *(bots[name].start(token) for name, token in active_tokens.items())
        )
    finally:
        await health_runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
