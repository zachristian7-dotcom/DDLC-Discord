from engine.memory import (
    initialize_database,
    save_message,
    get_recent_messages,
    save_memory,
    get_memories
)

initialize_database()

# Give Sayori a memory
save_message(
    "sayori",
    "You",
    "I really like cupcakes!"
)

save_memory(
    "sayori",
    "user_preference",
    "The user likes cupcakes."
)

# Give Natsuki a different memory
save_memory(
    "natsuki",
    "club_interest",
    "Sayori enjoys talking about cupcakes."
)

# Check Sayori's memories
print("\n--- SAYORI'S MEMORIES ---")

for memory in get_memories("sayori"):
    print(memory[0], ":", memory[1])

# Check Natsuki's memories
print("\n--- NATSUKI'S MEMORIES ---")

for memory in get_memories("natsuki"):
    print(memory[0], ":", memory[1])

print("\nMemory test complete!")
