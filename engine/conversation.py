import aiohttp

from config import AI_API_KEY, AI_BASE_URL, AI_MODEL
from engine.memory import get_memories, get_recent_messages
from engine.personality import load_character


def _offline_reply(character_name: str, user_message: str, memories=()) -> str:
    """Return a simple character-flavored reply when no AI provider is configured."""
    character = load_character(character_name)
    name = character["name"]
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

    return f"That's interesting! Tell me more."


class AIUnavailableError(Exception):
    """Raised when no AI provider has been configured."""


async def generate_reply(character_name: str, user_message: str, user_id: str) -> str:
    """Generate an AI reply, or a simple character-specific reply in offline mode."""
    memories = get_memories(character_name, user_id, limit=20)
    if not AI_BASE_URL or not AI_MODEL:
        return _offline_reply(character_name, user_message, memories)

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
