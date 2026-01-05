# Discord Gambling Bot with Texas Hold'em Poker

A professional Discord bot featuring a comprehensive gambling system with ticket management, balance tracking, and a fully-featured Texas Hold'em Poker game.

## Features

### 💰 Economy System
- User balance tracking via SQLite database
- Deposit and withdrawal ticket system
- 30% gambling requirement before withdrawal
- Money parsing (supports k, m, b suffixes)
- Transaction logging

### 🎲 Games
- **Coinflip**: Simple heads/tails gambling
- **Texas Hold'em Poker**: Full-featured poker game (see below)

### 🎟️ Ticket System
- Automated deposit ticket creation
- Withdrawal verification system
- Ticket transcripts saved automatically
- Role-based permissions

### 🃏 Texas Hold'em Poker

#### Security & Fairness
- **Cryptographically Secure Shuffling**: Uses Python's `secrets` module (CSPRNG)
- **Shuffle Verification**: SHA-256 hash commitment shown before game
- **Post-Game Verification**: Full shuffle data revealed for transparency
- **Tamper-Proof**: Shuffle order locked before dealing begins

#### Game Features
- 2-10 players per table
- Configurable blinds (default: 50/100)
- All Texas Hold'em phases: Pre-Flop, Flop, Turn, River, Showdown
- Complete betting mechanics: Check, Bet, Call, Raise, Fold
- Automatic hand evaluation (all poker hand ranks)
- Turn timer (30 seconds per action)
- Integration with bot economy
- Discord embed displays for game state
- Hole cards sent via DM

#### Poker Commands
- `!pokerjoin <amount>` - Join/create a poker table with buy-in
- `!pokerstart` - Start the game (host only)
- `!pokercheck` - Check (no bet)
- `!pokerbet <amount>` - Place a bet
- `!pokerraise <amount>` - Raise the bet
- `!pokercall` - Call the current bet
- `!pokerfold` - Fold your hand
- `!pokertable` - View current table state
- `!pokerleave` - Leave the table (before start)
- `!pokerend` - End the game and return chips (host only)

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/elijahrasmussen1/discord-bot.git
   cd discord-bot
   ```

2. **Install dependencies**
   ```bash
   pip install discord.py
   ```

3. **Configure the bot**
   - Edit `README.md` (the main bot file)
   - Replace `YOUR_BOT_TOKEN_HERE` with your Discord bot token
   - Update `OWNER_IDS`, `TICKET_CATEGORY_ID`, and other config values

4. **Run the bot**
   ```bash
   python3 README.md
   ```

## Bot Commands

### General Commands
- `!assist` - Show all available commands
- `!amount` - View your balance and gambling requirement
- `!withdraw` - Open a withdrawal ticket (if requirements met)
- `!coinflip <amount> <heads/tails>` - Play coinflip

### Owner Commands
- `!ticketpanel` - Send deposit ticket panel
- `!withdrawalpanel` - Send withdrawal panel
- `!deposit @user <amount>` - Add funds to a user
- `!viewamount @user` - View a user's balance
- `!amountall [page]` - View all user balances
- `!wipeamount @user` - Reset a user's balance

## Architecture

### File Structure
```
discord-bot/
├── README.md                    # Main bot file (executable Python)
├── poker_deck.py                # Deck and card management with CSPRNG
├── poker_hand_evaluator.py     # Hand ranking and evaluation
├── poker_player.py              # Player state management
├── poker_game.py                # Core poker game logic
├── poker_commands.py            # Discord command handlers
├── test_poker.py                # Comprehensive test suite
├── demo_poker.py                # Standalone demo (no Discord)
├── POKER_DOCUMENTATION.md       # Detailed poker documentation
├── .gitignore                   # Git ignore file
└── bot.db                       # SQLite database (auto-created)
```

### Database Schema

#### users table
- `user_id` (INTEGER PRIMARY KEY): Discord user ID
- `balance` (INTEGER): Current balance in $
- `required_gamble` (INTEGER): Amount needed to gamble (30% of balance)
- `gambled` (INTEGER): Amount gambled since last deposit
- `total_gambled` (INTEGER): Lifetime gambling total
- `total_withdrawn` (INTEGER): Lifetime withdrawal total

#### tickets table
- `user_id` (INTEGER): Discord user ID
- `ticket_number` (INTEGER): Sequential ticket number

## Testing

Run the comprehensive test suite:
```bash
python3 test_poker.py
```

Run the poker demo (no Discord required):
```bash
python3 demo_poker.py
```

All tests (21 tests) verify:
- Deck creation and shuffling
- Cryptographic security
- Hand evaluation (all 10 poker hands)
- Player actions and state management
- Game flow and betting rounds
- Winner determination
- Shuffle verification

## Configuration

Edit these constants in `README.md`:

```python
OWNER_IDS = [...]                    # Discord user IDs with admin access
TICKET_CATEGORY_ID = ...             # Category for ticket channels
TRANSCRIPT_CHANNEL_ID = ...          # Channel for ticket transcripts
WITHDRAWAL_LOG_CHANNEL = ...         # Channel for withdrawal logs
PING_ROLES = [...]                   # Roles to ping for tickets
MIN_DEPOSIT = 10_000_000            # Minimum deposit amount
GAMBLE_PERCENT = 0.30               # 30% gambling requirement
USERS_PER_PAGE = 5                  # Users per page in !amountall
GUILD_ID = ...                      # Your Discord server ID
```

## Security Features

### Poker Security
1. **CSPRNG Shuffling**: Uses `secrets.randbelow()` for unpredictable shuffles
2. **Hash Commitment**: SHA-256 hash published before dealing
3. **Shuffle Verification**: Full audit trail provided post-game
4. **Balance Protection**: Buy-ins immediately deducted
5. **Turn Validation**: Only current player can act
6. **Action Validation**: Invalid actions rejected

### Bot Security
- Owner-only commands protected by ID check
- Database transactions committed immediately
- Input validation for all amounts
- SQL injection protection via parameterized queries

## Troubleshooting

### Bot won't start
- Check your bot token is correct
- Ensure all intents are enabled in Discord Developer Portal
- Verify `discord.py` is installed

### Poker game issues
- Check player has sufficient balance for buy-in
- Ensure at least 2 players before starting
- Wait for your turn (check `!pokertable`)
- Use correct command syntax

### Database errors
- Delete `bot.db` to reset (WARNING: loses all data)
- Check file permissions
- Ensure SQLite is available

## Future Enhancements

### Planned Features
- Multi-hand poker games
- Tournament support
- Additional poker variants (Omaha, Five-Card Draw)
- Leaderboards and statistics
- Hand history replay
- Mobile-friendly card display

### Scalability
The modular architecture supports:
- Multiple concurrent poker tables
- Different game variants
- Custom betting structures
- Advanced tournament formats

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Ensure all tests pass
5. Submit a pull request

## Documentation

See [`POKER_DOCUMENTATION.md`](POKER_DOCUMENTATION.md) for detailed poker implementation documentation, including:
- Complete API reference
- Game flow diagrams
- Security analysis
- Extension guidelines
- Example game session

## License

This project is provided as-is for educational and entertainment purposes.

## Support

For issues or questions:
- Check the documentation
- Run the test suite
- Try the demo script
- Review game logs

---

**Made with ❤️ for Discord poker enthusiasts**

**Version**: 1.0.0  
**Last Updated**: January 2026
