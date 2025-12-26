# Discord Bot

A Discord bot built with discord.py for managing deposits, withdrawals, gambling, tickets, and pet tracking.

## Features

- **Deposit & Withdrawal System**: Ticket-based deposit and withdrawal management
- **Gambling System**: Coinflip gambling with 30% requirement
- **Ticket System**: Automated ticket creation with transcripts
- **Pet Tracking**: Owner-only commands to track pets across accounts

## Installation

1. Install dependencies:
```bash
pip install discord.py
```

2. Configure your bot token in `bot.py`:
```python
bot.run("YOUR_BOT_TOKEN_HERE")
```

3. Run the bot:
```bash
python bot.py
```

## Configuration

Edit the following configuration values in `bot.py`:

- `OWNER_IDS`: List of Discord user IDs with owner permissions
- `TICKET_CATEGORY_ID`: Category ID for ticket channels
- `TRANSCRIPT_CHANNEL_ID`: Channel ID for ticket transcripts
- `WITHDRAWAL_LOG_CHANNEL`: Channel ID for withdrawal logs
- `PING_ROLES`: Role IDs to ping when tickets are opened
- `MIN_DEPOSIT`: Minimum deposit amount (default: 10,000,000)
- `GAMBLE_PERCENT`: Required gamble percentage (default: 0.30 = 30%)
- `GUILD_ID`: Your Discord server/guild ID

## Commands

### Member Commands
- `!amount` - View your balance and remaining required gamble
- `!withdraw` - Open a withdrawal ticket (if 30% gambled)
- `!coinflip [amount] [heads/tails]` - Gamble a coinflip

### Owner Commands
- `!ticketpanel` - Send deposit ticket panel
- `!withdrawalpanel` - Send withdrawal ticket panel
- `!deposit @user amount` - Add gambling amount to a user
- `!viewamount @user` - View a user's balance
- `!amountall [page]` - View all users balances
- `!wipeamount @user` - Wipe a user's balance
- `!trackpet <pet_id>` - Look up a pet by ID
- `!petids` - List all pets in stock

## Database

The bot uses SQLite to store:
- User balances and gambling requirements
- Ticket numbers
- Pet inventory (ID, name, account)

Database file: `bot.db` (created automatically on first run)

## Pet Tracking System

Owner-only commands for managing pet inventory:

### `!trackpet <pet_id>`
Look up a pet by its ID and retrieve the associated pet name and account.

**Example:**
```
!trackpet 4
```
**Output:** `🐾 Pet ID 4: Los Combinasionas is in gamb1ebank1`

### `!petids`
List all pets currently in stock with their IDs and associated accounts.

**Output:** Embedded list of all pets with pagination support for large inventories.

## License

This project is open source and available for use and modification.

