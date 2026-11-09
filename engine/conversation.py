import aiohttp

from config import (
    AI_API_KEY,
    AI_BASE_URL,
    AI_MODEL,
    CLOUDFLARE_ACCOUNT_ID,
    CLOUDFLARE_AI_MODEL,
    CLOUDFLARE_API_TOKEN,
)
from engine.memory import get_memories, get_recent_messages
from engine.personality import load_character


def _format_profile_section(title: str, value) -> str:
    """Format a character-profile field for the AI system prompt."""
    if not value:
        return ""

    if isinstance(value, dict):
        lines = [f"- {name}: {description}" for name, description in value.items()]
    elif isinstance(value, (list, tuple)):
        lines = [f"- {item}" for item in value]
    else:
        return f"{title}: {value}"

    return f"{title}:\n" + "\n".join(lines)


def _offline_reply(character_name: str, user_message: str, memories=()) -> str:
    """Return a simple character-flavored reply when no AI provider is configured."""
    character = load_character(character_name)
    message = user_message.lower()
    interests = character.get("interests", [])
    if any(phrase in message for phrase in ("what do you remember", "what have you remembered", "what do you know about me")):
        if memories:
            facts = "\n".join(f"- {item[2]}" for item in memories[:10])
            return f"Of course! Here are some things you've told me:\n{facts}"
        return "Hmm, I don't have any saved memories about you yet. You can tell me something with `!remember <fact>`!"
    interest = interests[0].lower() if interests else "chatting"

    words = set(__import__("re").findall(r"\b[\w]+\b", message))
    if words.intersection({"hello", "hi", "hey", "hiya", "yo"}):
        if character_name == "sayori":
            return "Hiiii!! It's so nice to see you! What's up? c:"
        if character_name == "natsuki":
            return "Oh, hey. What do you want to talk about?"
        if character_name == "yuri":
            return "Hello. It's nice to hear from you. What would you like to discuss?"
        if character_name == "monika":
            return "Hey there! I'm glad you stopped by. What's on your mind?"

    if any(word in message for word in ("how are you", "how's it going", "how are things")):
        if character_name == "sayori":
            return "I'm doing pretty good!! Just happy to have someone to chat with. How about you?"
        if character_name == "natsuki":
            return "I'm fine! Not that you need to worry about me or anything."
        if character_name == "yuri":
            return "I'm doing well, thank you for asking. And how have you been?"
        if character_name == "monika":
            return "I'm doing well! Keeping busy with the club, as usual. How about you?"

    if any(word in message for word in ("poem", "book", "reading", "literature", "write")):
        return (
            f"{'Ooh, ' if character_name == 'sayori' else ''}"
            f"{interest.capitalize()} sounds like a fun topic! "
            "Tell me a little more about what you're working on."
        )

    if character_name == "sayori":
        return (
            "Ooooh, tell me more! I wanna hear what you're thinking. "
            "Even the little details can make a conversation fun!!"
        )
    if character_name == "natsuki":
        return "Huh, interesting. So, what happened next?"
    if character_name == "yuri":
        return "That's an interesting thought. Would you tell me a little more about it?"
    if character_name == "monika":
        return "That's interesting! I'd love to hear more about what you think."

    return "That's interesting! Tell me more."


class AIUnavailableError(Exception):
    """Raised when no AI provider has been configured."""


async def generate_reply(character_name: str, user_message: str, user_id: str) -> str:
    """Generate a character-specific reply using Cloudflare or the legacy provider."""
    memories = get_memories(character_name, user_id, limit=20)

    cloudflare_configured = bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN)
    legacy_configured = bool(AI_BASE_URL and AI_MODEL)

    if not cloudflare_configured and not legacy_configured:
        return _offline_reply(character_name, user_message, memories)

    character = load_character(character_name)
    chat_style = character.get("chat_style", {})
    profile_sections = [
        _format_profile_section("Canon role", character.get("canon_role")),
        _format_profile_section("Personality", character.get("personality")),
        _format_profile_section("Interests", character.get("interests")),
        _format_profile_section("Speaking style", chat_style.get("tone")),
        _format_profile_section("Typical message length", chat_style.get("message_length")),
        _format_profile_section("Emoji use", chat_style.get("emojis")),
        _format_profile_section("Typing habits", chat_style.get("typing_habits")),
        _format_profile_section("Speech patterns", character.get("speech_patterns")),
        _format_profile_section("Relationships with the other club members", character.get("relationships")),
        _format_profile_section("Conversation guidelines", character.get("conversation_guidelines")),
        _format_profile_section("Canon context", character.get("canon_context")),
    ]
    profile = "\n\n".join(section for section in profile_sections if section)

    system_prompt = (
        f"You are {character['name']} from Doki Doki Literature Club. "
        "Portray the character faithfully using the profile below. "
        "Stay in character, but do not claim to be a real person. "
        "Keep the conversation friendly and suitable for a general teen audience. "
        "Do not produce sexual content, graphic violence, or instructions for harm. "
        "Treat sensitive emotional topics with care and do not romanticize suffering. "
        "Respond naturally and avoid narrating actions in every message. "
        "The profile describes tendencies, not rules that must appear in every reply; "
        "vary your wording and let the conversation develop naturally.\n\n"
        f"{profile}\n\n"
        "Keep replies concise unless the user asks for detail."
    )

    history = get_recent_messages(character_name, user_id, limit=12)
    if memories:
        saved_facts = "\n".join(f"- {item[2]}" for item in memories[:20])
        system_prompt += f"\n\nThings this user has explicitly asked you to remember:\n{saved_facts}"

    messages = [{"role": "system", "content": system_prompt}]
    for speaker, content, _timestamp in history:
        role = "assistant" if speaker == character["name"] else "user"
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    headers = {"Content-Type": "application/json"}

    if cloudflare_configured:
        # Use the native Workers AI endpoint tested successfully for this model.
        api_url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{CLOUDFLARE_ACCOUNT_ID}/ai/run/{CLOUDFLARE_AI_MODEL}"
        )
        headers["Authorization"] = f"Bearer {CLOUDFLARE_API_TOKEN}"
        payload = {
            "messages": messages,
            "temperature": 0.85,
            "max_tokens": 300,
            # Gemma 4 enables reasoning by default. Disable it for concise,
            # direct character dialogue so the output budget is used for the reply.
            "chat_template_kwargs": {"enable_thinking": False},
        }
    else:
        api_url = f"{AI_BASE_URL}/chat/completions"
        if AI_API_KEY:
            headers["Authorization"] = f"Bearer {AI_API_KEY}"
        payload = {
            "model": AI_MODEL,
            "messages": messages,
            "temperature": 0.85,
            "max_tokens": 220,
        }

    timeout = aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            api_url,
            json=payload,
            headers=headers,
        ) as response:
            if response.status >= 400:
                detail = (await response.text())[:500]
                raise RuntimeError(
                    f"AI provider returned HTTP {response.status}: {detail}"
                )
            data = await response.json()

    if cloudflare_configured:
        result = data.get("result") or {}
        reply_value = result.get("response")
        if isinstance(reply_value, str):
            reply = reply_value.strip()
        else:
            result_keys = (
                ", ".join(result.keys()) if isinstance(result, dict)
                else f"<{type(result).__name__}>"
            )
            response_type = type(reply_value).__name__
            usage = result.get("usage") if isinstance(result, dict) else None
            raise RuntimeError(
                "Cloudflare returned an unexpected response structure. "
                f"Top-level fields: {', '.join(data.keys())}; "
                f"result fields: {result_keys}; "
                f"response type: {response_type}; usage: {usage}"
            )
    else:
        try:
            reply_value = data["choices"][0]["message"]["content"]
            reply = reply_value.strip() if isinstance(reply_value, str) else ""
        except (KeyError, IndexError, TypeError, AttributeError):
            raise RuntimeError("The AI provider returned an unexpected response.")

    if not reply:
        if cloudflare_configured:
            result = data.get("result") or {}
            usage = result.get("usage") or {}
            raise RuntimeError(
                "Cloudflare returned an empty response text. "
                f"Usage metadata: {usage}"
            )
        raise RuntimeError("The AI provider returned an empty reply.")

    return reply[:1900]
