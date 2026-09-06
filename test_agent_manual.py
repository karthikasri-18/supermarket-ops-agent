"""
test_agent_manual.py

Tests bot/agent.py (Gemini version) in isolation, no Telegram
involved. Run: python test_agent_manual.py

Watch for the grounding test: it should call get_stock_level and
report a real number, not guess.
"""

from bot.agent import new_chat_session


def ask(session, message):
    print(f"\n>>> Owner: {message}")
    response = session.send_message(message)
    print(f"Agent: {response.text}")


def main():
    session = new_chat_session()
    ask(session, "How much Maggi 70g do we have?")
    ask(session, "50 packets of Maggi came in, cost 12 rupees each")
    ask(session, "How much Maggi do we have now?")


if __name__ == "__main__":
    main()