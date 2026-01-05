# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-01-04

### Added - Texas Hold'em Poker Game 🃏

#### Core Features
- **Complete Texas Hold'em implementation** with all game phases
  - Pre-Flop: 2 hole cards per player
  - Flop: 3 community cards
  - Turn: 4th community card
  - River: 5th community card
  - Showdown: Automatic winner determination

#### Security & Fairness
- **Cryptographically secure shuffling** using Python's `secrets` module (CSPRNG)
- **SHA-256 hash commitment** shown before dealing for transparency
- **Post-game shuffle verification** allowing players to verify fairness
- **Tamper-proof design** with shuffle order locked before game starts

#### Game Mechanics
- **Multi-player support**: 2-10 players per table
- **Configurable blinds**: Default 50/100, customizable
- **Complete betting actions**:
  - Check (pass without betting)
  - Bet (initial wager)
  - Call (match current bet)
  - Raise (increase bet)
  - Fold (drop out)
- **All-in support**: Automatic when insufficient chips
- **Turn timer**: 30 seconds per action with auto-fold
- **Pot management**: Proper pot tracking with side pot support

#### Hand Evaluation
- **All 10 poker hand rankings** properly evaluated:
  1. Royal Flush
  2. Straight Flush
  3. Four of a Kind
  4. Full House
  5. Flush
  6. Straight
  7. Three of a Kind
  8. Two Pair
  9. Pair
  10. High Card
- **Tie-breaker logic** with kicker support
- **5-7 card evaluation** finds best 5-card hand

#### Discord Integration
- **10 new commands** for poker gameplay
- **Discord embeds** for beautiful game state display
- **Private hole cards** sent via DM
- **Visual indicators**: ✅ Active, ❌ Folded, 🔴 All-in, 🎲 Dealer, ⏰ Current turn
- **Real-time updates** after each action

#### Economy Integration
- **Balance system integration**: Buy-ins deducted from user balance
- **Gamble tracking**: All bets count toward 30% requirement
- **Automatic payouts**: Winnings added to balance
- **Chip refunds**: On game end or player leave

#### Commands Added
- `!pokerjoin <amount>` - Join or create poker table
- `!pokerstart` - Start game (host only)
- `!pokercheck` - Check action
- `!pokerbet <amount>` - Place a bet
- `!pokerraise <amount>` - Raise the bet
- `!pokercall` - Call current bet
- `!pokerfold` - Fold hand
- `!pokertable` - View table state
- `!pokerleave` - Leave table (before start)
- `!pokerend` - End game and return chips (host only)

#### Documentation
- **POKER_DOCUMENTATION.md**: Comprehensive technical documentation
  - API reference
  - Security analysis
  - Extension guidelines
  - Example game session
- **PROJECT_README.md**: Project overview and setup guide
  - Installation instructions
  - Configuration guide
  - Architecture overview
  - Troubleshooting section
- **QUICK_START.md**: User-friendly quick start guide
  - Command reference
  - Hand rankings
  - Example gameplay
  - Common issues

#### Testing
- **21 automated tests** covering:
  - Deck creation and shuffling
  - Cryptographic security
  - All 10 hand rankings
  - Player actions
  - Game flow
  - Betting rounds
  - Winner determination
  - Shuffle verification
- **Demo script** for standalone testing without Discord
- **All tests passing** with 100% success rate

#### Code Quality
- **5 modular files** for clean separation of concerns
  - `poker_deck.py` - Deck and card management
  - `poker_hand_evaluator.py` - Hand ranking system
  - `poker_player.py` - Player state management
  - `poker_game.py` - Core game logic
  - `poker_commands.py` - Discord command handlers
- **Code review completed** with all feedback addressed
- **CodeQL security scan** passed with 0 vulnerabilities
- **Inline documentation** for all major functions
- **.gitignore** added to exclude cache files

#### Logging & Debugging
- **Comprehensive game logging** for all actions
- **Replay capability** via game log
- **Action history tracking** for debugging
- **Shuffle verification data** stored for audit

### Updated
- **!assist command** now includes poker commands
- **README.md** integrated poker setup

### Technical Details
- **Language**: Python 3.x
- **Dependencies**: discord.py (existing)
- **Database**: Uses existing SQLite structure
- **Architecture**: Modular and extensible
- **Security**: CSPRNG-based, hash-committed
- **Testing**: 21 automated tests
- **Documentation**: 3 comprehensive guides

### Performance
- **Memory**: ~1-2 KB per game instance
- **CPU**: Negligible (hand evaluation is O(n choose 5))
- **Concurrency**: One game per Discord channel
- **Scalability**: Multiple concurrent games across channels

### Future Enhancements Planned
- Additional poker variants (Omaha, Five-Card Draw)
- Tournament support
- Multi-hand gameplay
- Leaderboards and statistics
- Hand history viewer

---

## [0.1.0] - Initial Release

### Features
- Basic gambling bot functionality
- Coinflip game
- Ticket system for deposits and withdrawals
- Balance tracking with 30% gambling requirement
- Owner commands for user management
- SQLite database for persistence

---

**Note**: This project follows [Semantic Versioning](https://semver.org/).
