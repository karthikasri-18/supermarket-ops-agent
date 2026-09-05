# Supermarket Ops Agent

Telegram bot that runs an Indian kirana store end-to-end via a conversational agent.

> This README gets filled in properly on Day 5. For now it's just a placeholder
> so the repo isn't empty.

## Harness
TBD (Claude Agent SDK)

## Telegram bot
@TBD

## Setup
1. `python -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in real values
4. `psql $DATABASE_URL -f db/schema.sql`
5. `psql $DATABASE_URL -f db/seed.sql`
