import aiohttp

from config import AI_API_KEY, AI_BASE_URL, AI_MODEL
from engine.memory import get_recent_messages
from engine.personality import load_character


class AIUnavailableError(Exception):
    """Raised when no AI provider has been configured."""


async def generate_reply(character_name: str, user_message: str) -> str:
    """Generate a reply through a configurable OpenAI-compatible API."""
    if not AI_BASE_URL or not AI_MODEL:
        raise AIUnavailableError("AI provider is not configured.")

    character = load_character(character_name)
    personality = "\n".join(f"- {item}" for item in character["personality"])
    interests = ", ".join(character.get("interests", []))
    style = character.get("chat_style", {}).get("tone", "natural")

    system_prompt = (
        f"You are {character['name']} from Doki Doki Literature Club. "
        "Stay in character, but do not claim to be a real person. "
        "Keep the conversation friendly and suitable for a general teen audience. "
        "Do not produce sexual content, graphic violence, or instructions for harm. "
        "Respond naturally and avoid narrating actions in every message.\n\n"
        f"Personality:\n{personality}\n"
        f"Interests: {interests}\n"
        f"Speaking style: {style}\n"
        "Keep replies concise unless the user asks for detail."
    )

    history = get_recent_messages(character_name, limit=12)
    messages = [{"role": "system", "content": system_prompt}]
    for speaker, content, _timestamp in history:
        role = "assistant" if speaker == character["name"] else "user"
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    headers = {"Content-Type": "application/json"}
    if AI_API_KEY:
        headers["Authorization"] = f"Bearer {AI_API_KEY}"

    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.85,
        "max_tokens": 220,
    }

    timeout = aiohttp.ClientTimeout(total=45)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            f"{AI_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
        ) as response:
            if response.status >= 400:
                detail = (await response.text())[:300]
                raise RuntimeError(
                    f"AI provider returned HTTP {response.status}: {detail}"
                )
            data = await response.json()

    try:
        reply = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        raise RuntimeError("The AI provider returned an unexpected response.")

    if not reply:
        raise RuntimeError("The AI provider returned an empty reply.")

    return reply[:1900]
