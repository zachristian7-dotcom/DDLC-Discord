import logging

import discord
from discord.ext import commands

from config import AI_BASE_URL, AI_MODEL, CHARACTERS, COMMAND_PREFIX, DISCORD_TOKEN
from engine.conversation import AIUnavailableError, generate_reply
from engine.memory import initialize_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ddlc-bot")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)


@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    logger.info("AI provider configured: %s", bool(AI_BASE_URL and AI_MODEL))


@bot.command(name="help")
async def help_command(ctx):
    prefix = COMMAND_PREFIX
    await ctx.reply(
        "**Literature Club Bot**\n"
        f"{prefix}sayori <message> — talk to Sayori\n"
        f"{prefix}natsuki <message> — talk to Natsuki\n"
        f"{prefix}yuri <message> — talk to Yuri\n"
        f"{prefix}monika <message> — talk to Monika\n"
        f"{prefix}club <character> <message> — choose a character\n"
        f"{prefix}status — check the bot's setup",
        mention_author=False,
    )


@bot.command(name="status")
async def status_command(ctx):
    ai_ready = bool(AI_BASE_URL and AI_MODEL)
    await ctx.reply(
        f"Bot is online. AI mode: **{'configured' if ai_ready else 'not configured yet'}**.",
        mention_author=False,
    )


async def talk_to_character(ctx, character: str, message: str):
    if not message.strip():
        await ctx.reply(
            f"Tell {character.title()} what you want to talk about.",
            mention_author=False,
        )
        return

    async with ctx.typing():
        try:
            reply = await generate_reply(character, message.strip())
        except AIUnavailableError:
            await ctx.reply(
                "I'm online, but the AI connection hasn't been set up yet. "
                "The next step is choosing a genuinely free AI option; I won't "
                "pretend this is an AI reply when it isn't.",
                mention_author=False,
            )
            return
        except Exception:
            logger.exception("Reply generation failed for %s", character)
            await ctx.reply(
                "Sorry! I couldn't reach the AI service just now. Please try again in a bit.",
                mention_author=False,
            )
            return

    await ctx.reply(f"**{character.title()}:** {reply}", mention_author=False)


def make_character_command(character_name):
    async def character_command(ctx, *, message=""):
        await talk_to_character(ctx, character_name, message)

    character_command.__name__ = f"{character_name}_command"
    return commands.command(name=character_name)(character_command)


for character_name in CHARACTERS:
    bot.add_command(make_character_command(character_name))


@bot.command(name="club")
async def club_command(ctx, character: str = "", *, message=""):
    character = character.lower()
    if character not in CHARACTERS:
        await ctx.reply(
            "Choose one: sayori, natsuki, yuri, or monika.",
            mention_author=False,
        )
        return
    await talk_to_character(ctx, character, message)


def main():
    if not DISCORD_TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN is missing. Add it as an environment variable in Render."
        )

    initialize_database()
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
