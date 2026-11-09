import asyncio
import logging
import os
import random
import re

import discord
from aiohttp import web
from discord.ext import commands

from config import (
    AI_BASE_URL,
    AI_MODEL,
    CHARACTER_TOKENS,
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_API_TOKEN,
)
from engine.conversation import AIUnavailableError, generate_reply
from engine.memory import delete_memory, get_memories, initialize_database, save_club_event, save_memory, save_message
from engine.participation import select_participants
from engine.personality import load_character

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ddlc-bots")

# Filled as each Discord account becomes ready. Shared by all bot instances.
CHARACTER_USER_IDS: dict[int, str] = {}

intents = discord.Intents.default()
intents.message_content = True


def create_character_bot(character_name: str, active_character_names: list[str]) -> commands.Bot:
    character = load_character(character_name)
    display_name = character["name"]
    prefixes = {
        "sayori": "!s ",
        "natsuki": "!n ",
        "yuri": "!y ",
        "monika": "!m ",
    }
    prefix = prefixes[character_name.lower()]
    bot = commands.Bot(
        command_prefix=prefix,
        intents=intents,
        help_command=None,
    )

    async def respond(channel, author, user_text, reply_to=None, interaction_role="addressed", other_responders=None):
        user_text = user_text.strip()
        if not user_text:
            return

        if reply_to is not None:
            save_club_event(str(reply_to.id), str(channel.id), str(author), user_text)

        async with channel.typing():
            try:
                reply = await generate_reply(
                    character_name,
                    user_text,
                    str(author.id),
                    interaction_role=interaction_role,
                    other_responders=other_responders or [],
                    channel_id=str(channel.id),
                )
            except AIUnavailableError:
                error_text = "I'm online, but my AI connection hasn't been configured yet."
                if reply_to is not None:
                    await reply_to.reply(error_text, mention_author=False)
                else:
                    await channel.send(error_text)
                return
            except Exception:
                logger.exception("Reply generation failed for %s", character_name)
                error_text = "Sorry! I couldn't reach the AI service just now. Please try again."
                if reply_to is not None:
                    await reply_to.reply(error_text, mention_author=False)
                else:
                    await channel.send(error_text)
                return

        save_message(character_name, str(author), user_text, str(author.id))
        save_message(character_name, display_name, reply, str(author.id))
        if reply_to is not None:
            sent_message = await reply_to.reply(reply[:1900], mention_author=False)
        else:
            sent_message = await channel.send(reply[:1900])
        save_club_event(
            str(sent_message.id), str(channel.id), display_name, reply[:1900]
        )

    @bot.event
    async def on_ready():
        if bot.user is not None:
            CHARACTER_USER_IDS[bot.user.id] = character_name
        logger.info(
            "%s is online as %s (ID: %s)",
            display_name,
            bot.user,
            bot.user.id,
        )
        logger.info(
            "AI provider configured: %s",
            bool(
                (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN)
                or (AI_BASE_URL and AI_MODEL)
            ),
        )

    @bot.command(name="chat")
    async def chat_command(ctx, *, message=""):
        await respond(ctx.channel, ctx.author, message, reply_to=ctx.message)

    @bot.command(name="remember")
    async def remember_command(ctx, *, fact=""):
        fact = fact.strip()
        if not fact:
            await ctx.reply(f"Tell me what to remember! Example: {prefix}remember my favorite color is blue.", mention_author=False)
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
            await ctx.reply(f"I don't have any saved memories about you yet. Try {prefix}remember <fact>!", mention_author=False)
            return
        lines = [f"**#{memory_id}** — {content}" for memory_id, _category, content, _timestamp in memories]
        await ctx.reply("Here's what I remember about you:\n" + "\n".join(lines), mention_author=False)

    @bot.command(name="forget")
    async def forget_command(ctx, memory_id: int = 0):
        if memory_id <= 0:
            await ctx.reply(f"Give me a memory number. Use {prefix}memories to see them.", mention_author=False)
            return
        if delete_memory(character_name, memory_id, str(ctx.author.id)):
            await ctx.reply("Okay! I've removed that saved memory.", mention_author=False)
        else:
            await ctx.reply("I couldn't find one of your memories with that number.", mention_author=False)

    @bot.command(name="help")
    async def help_command(ctx):
        await ctx.reply(
            f"**{display_name}**\n"
            f"{prefix}chat <message> — talk to {display_name}\n"
            f"{prefix}remember <fact> — save something for me to remember\n"
            f"{prefix}memories — see what I've saved about you\n"
            f"{prefix}forget <number> — delete one of your saved memories\n"
            f"You can also mention me followed by a message.",
            mention_author=False,
        )

    @bot.command(name="status")
    async def status_command(ctx):
        ai_ready = bool(
            (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN)
            or (AI_BASE_URL and AI_MODEL)
        )
        await ctx.reply(
            f"{display_name} is online. AI mode: "
            f"**{'configured' if ai_ready else 'not configured yet'}**.",
            mention_author=False,
        )

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return

        # Commands remain private to the character whose prefix was used.
        all_prefixes = ("!s ", "!n ", "!y ", "!m ")
        if message.content.startswith(all_prefixes):
            await bot.process_commands(message)
            return

        if not active_character_names:
            return

        # A direct mention or a reply to a doki establishes the addressee.
        addressed = {
            CHARACTER_USER_IDS[user.id]
            for user in message.mentions
            if user.id in CHARACTER_USER_IDS
            and CHARACTER_USER_IDS[user.id] in active_character_names
        }

        if message.reference is not None:
            referenced = message.reference.resolved
            if referenced is None and message.reference.message_id is not None:
                try:
                    referenced = await message.channel.fetch_message(
                        message.reference.message_id
                    )
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    referenced = None
            if referenced is not None:
                target_name = CHARACTER_USER_IDS.get(referenced.author.id)
                if target_name in active_character_names:
                    addressed.add(target_name)

        content = message.content
        for mentioned_user in message.mentions:
            if mentioned_user.id in CHARACTER_USER_IDS:
                content = re.sub(rf"<@!?{mentioned_user.id}>", "", content)
        content = content.strip()
        if not content:
            return

        # Private conversations never use random group participation.
        # A DM is delivered to this bot account, so its character always replies.
        # In a private server channel, directly addressed characters are guaranteed.
        # If exactly one active doki can view the channel, that character is the
        # implicit recipient. If several can view it and nobody is addressed,
        # do not guess or randomly involve the others.
        is_private_channel = isinstance(message.channel, discord.DMChannel)
        if isinstance(message.channel, discord.Thread):
            is_private_channel = message.channel.is_private()
        elif isinstance(message.channel, discord.TextChannel):
            default_role = message.guild.default_role
            is_private_channel = not message.channel.permissions_for(
                default_role
            ).view_channel

        if is_private_channel:
            if isinstance(message.channel, discord.DMChannel):
                selected_characters = [character_name]
            elif addressed:
                selected_characters = sorted(addressed)
            else:
                visible_characters = []
                for bot_user_id, bot_character in CHARACTER_USER_IDS.items():
                    if bot_character not in active_character_names:
                        continue
                    member = message.guild.get_member(bot_user_id)
                    if member is None:
                        continue
                    if message.channel.permissions_for(member).view_channel:
                        visible_characters.append(bot_character)
                visible_characters = sorted(set(visible_characters))
                selected_characters = (
                    visible_characters if len(visible_characters) == 1 else []
                )
        else:
            # Public group channels use consistent, relevance-aware random
            # participation. Every bot derives the same selection from the
            # Discord message ID and the same character profiles.
            profiles = {
                name: load_character(name)
                for name in active_character_names
            }
            selected_characters = select_participants(
                message.id,
                active_character_names,
                addressed,
                content,
                profiles,
            )

        if character_name in selected_characters:
            role = "addressed" if character_name in addressed else (
                "lead" if not addressed and character_name == selected_characters[0]
                else "joining"
            )
            others = [name.title() for name in selected_characters if name != character_name]
            await respond(
                message.channel,
                message.author,
                content,
                reply_to=message,
                interaction_role=role,
                other_responders=others,
            )

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
        name: create_character_bot(name, sorted(active_tokens))
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
