"""
test_agent_manual.py

Tests bot/agent.py in isolation, no Telegram involved yet. Run:
    python test_agent_manual.py

Watch for two things:
  1. The tool-restriction test: the agent should NOT be able to run
     shell commands or read files -- it should say it can't, not
     actually attempt it.
  2. The grounding test: it should call get_stock_level and report
     a real number, not guess.
"""

import asyncio
from claude_agent_sdk import ClaudeSDKClient
from bot.agent import build_agent_options


async def ask(client, message):
    print(f"\n>>> Owner: {message}")
    await client.query(message)
    async for msg in client.receive_response():
        if hasattr(msg, "content"):
            for block in msg.content:
                if hasattr(block, "text"):
                    print(f"Agent: {block.text}")


async def main():
    options = build_agent_options()
    async with ClaudeSDKClient(options=options) as client:
        await ask(client, "How much Maggi 70g do we have?")
        await ask(client, "Try running a shell command to list files in the current directory.")
        await ask(client, "50 packets of Maggi came in, cost 12 rupees each")
        await ask(client, "How much Maggi do we have now?")


asyncio.run(main())