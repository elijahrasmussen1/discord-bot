# Texas Hold'em Poker Game Documentation

## Overview

This poker implementation provides a professional, fair, and secure Texas Hold'em poker game for the Discord gambling bot. The game uses cryptographically secure random number generation to ensure fairness and includes comprehensive features for multi-player gameplay.

## Features

### 🔒 Security & Fairness
- **Cryptographically Secure Shuffling**: Uses Python's `secrets` module (CSPRNG) for unpredictable deck shuffling
- **Shuffle Verification**: Generates and commits a SHA-256 hash before the game starts
- **Post-Game Verification**: Players can verify the shuffle was fair after the game completes
- **Tamper-Proof**: Shuffle order is determined before cards are dealt, preventing manipulation

### 🎮 Game Mechanics
- **Texas Hold'em**: Full implementation of the most popular poker variant
- **All Game Phases**: Pre-Flop, Flop, Turn, River, and Showdown
- **Multi-Player Support**: 2-10 players per table
- **Blind System**: Configurable small blind (default: 50$) and big blind (default: 100$)
- **Turn Timer**: 30-second timer per player action to keep the game moving
- **Pot Management**: Automatic pot tracking with support for side pots (all-in situations)

### 💰 Betting Actions
- **Check**: Continue without betting (when no bet to call)
- **Bet**: Place an initial wager in a round
- **Call**: Match the current bet
- **Raise**: Increase the current bet
- **Fold**: Drop out of the current hand
- **All-In**: Bet all remaining chips automatically when insufficient stack

### 🃏 Hand Evaluation
The hand evaluator automatically determines winners using standard poker hand rankings:
1. **Royal Flush**: A-K-Q-J-10 of the same suit
2. **Straight Flush**: Five consecutive cards of the same suit
3. **Four of a Kind**: Four cards of the same rank
4. **Full House**: Three of a kind plus a pair
5. **Flush**: Five cards of the same suit
6. **Straight**: Five consecutive cards
7. **Three of a Kind**: Three cards of the same rank
8. **Two Pair**: Two different pairs
9. **Pair**: Two cards of the same rank
10. **High Card**: Highest card when no other hand is made

**Tie-Breakers**: The evaluator handles kickers and multi-way ties automatically.

### 📊 Integration with Bot Economy
- **Balance Integration**: Buy-ins are deducted from player balances
- **Gamble Tracking**: All bets count toward the 30% gambling requirement
- **Winnings**: Pot winnings are added back to player balances
- **Chip Management**: Players can leave and cash out at any time (before game starts)

## Commands

### Setting Up a Game

#### `!pokerjoin <amount>`
Join or create a poker table with a buy-in.
- **Usage**: `!pokerjoin 1000` or `!pokerjoin 1k`
- **Example**: `!pokerjoin 5000` - Join with 5,000$ buy-in
- If no table exists, creates a new one with you as host
- Deducts buy-in from your balance

#### `!pokerstart`
Start the poker game (host only).
- Must have at least 2 players
- Deals hole cards to all players via DM
- Posts blinds automatically
- Shows the shuffle commitment hash

### During the Game

#### `!pokercheck`
Check (pass without betting).
- Only valid when there's no bet to call
- Allows the action to move to the next player

#### `!pokerbet <amount>`
Place a bet in the current round.
- **Usage**: `!pokerbet 200`
- Minimum bet is the big blind (100$)
- Only valid if no one has bet yet this round

#### `!pokercall`
Call the current bet.
- Matches the current bet amount
- If you don't have enough chips, you go all-in

#### `!pokerraise <amount>`
Raise the current bet.
- **Usage**: `!pokerraise 300`
- Must be at least the big blind more than current bet
- Amount is added on top of the call amount

#### `!pokerfold`
Fold your hand.
- Removes you from the current hand
- You cannot win the pot
- Remaining players continue

#### `!pokertable`
View the current table state.
- Shows community cards
- Displays pot and current bet
- Lists all players with their stacks and status
- Indicates whose turn it is

### Managing the Game

#### `!pokerleave`
Leave the table (only before game starts).
- Returns your buy-in to your balance
- Cannot leave during an active hand

#### `!pokerend`
End the game and return all chips (host only).
- Returns all remaining chips to players
- Counts all bets toward gamble requirements
- Closes the table

## Gameplay Flow

### 1. Lobby Phase
- Players join the table with `!pokerjoin <amount>`
- Host starts the game with `!pokerstart` when ready
- Minimum 2 players, maximum 10 players

### 2. Pre-Flop
- Each player receives 2 hole cards (dealt privately via DM)
- Small blind and big blind are posted automatically
- First betting round begins (left of big blind acts first)

### 3. Flop
- Three community cards are revealed
- Second betting round (left of dealer acts first)

### 4. Turn
- Fourth community card is revealed
- Third betting round

### 5. River
- Fifth community card is revealed
- Final betting round

### 6. Showdown
- Remaining players reveal their hands
- Best 5-card hand wins (from 7 cards: 2 hole + 5 community)
- Pot is distributed to winner(s)
- Shuffle verification data is shown

## Visual Display

The game uses Discord embeds to display:
- **Community Cards**: All revealed cards in the middle
- **Pot Amount**: Total chips in the pot
- **Current Bet**: Amount to call
- **Player List**: 
  - ✅ Active players
  - ❌ Folded players
  - 🔴 All-in players
  - 🎲 Dealer button
  - ⏰ Current turn indicator
- **Time Remaining**: Countdown for current player's turn
- **Hand Results**: Winner's hand rank and hole cards

## Technical Architecture

### Modules

#### `poker_deck.py`
- Card and Deck classes
- Cryptographic shuffling using `secrets` module
- SHA-256 hash generation and verification
- Shuffle commitment system

#### `poker_hand_evaluator.py`
- Hand ranking constants
- Hand evaluation algorithm (supports 5-7 cards)
- Tie-breaker logic
- Hand comparison function

#### `poker_player.py`
- Player state management
- Stack tracking
- Action processing (bet, call, raise, fold, check)
- Hole card management

#### `poker_game.py`
- Core game loop and state machine
- Phase management (waiting, pre-flop, flop, turn, river, showdown)
- Betting round coordination
- Turn timer management
- Winner determination
- Game logging for replay

#### `poker_commands.py`
- Discord command handlers
- PokerManager for multi-table support
- Game state display using embeds
- Turn timeout monitoring
- Integration with bot economy

### Design Patterns

- **State Machine**: Game phases transition based on betting completion
- **Manager Pattern**: PokerManager handles multiple concurrent games
- **Observer Pattern**: Turn monitoring task watches for timeouts
- **Command Pattern**: Each Discord command maps to game actions

## Future Extensibility

The codebase is designed to support additional poker variants:

### Potential Additions
- **Omaha Hold'em**: Deal 4 hole cards instead of 2
- **Five-Card Draw**: Different dealing and betting structure
- **Tournaments**: Multi-table tournament support
- **Sit-and-Go**: Fixed player count with automated progression
- **Cash Game Tables**: Persistent tables with buy-in/cash-out

### Extension Points
- `GamePhase` can be extended for new game types
- `HandEvaluator` can be subclassed for variant-specific rules
- `PokerGame` can be subclassed to override dealing/betting logic
- Commands can be conditionally registered based on game variant

## Security Considerations

### What's Protected
- ✅ **Shuffle Fairness**: CSPRNG ensures unpredictable card order
- ✅ **Shuffle Verification**: Hash commitment prevents post-hoc manipulation
- ✅ **Balance Protection**: Buy-ins deducted immediately
- ✅ **Turn Enforcement**: Only current player can act
- ✅ **Action Validation**: Invalid actions are rejected

### What Users Should Be Aware Of
- Hole cards are sent via DM (users should protect their Discord account)
- Turn timer auto-folds inactive players
- Host can end the game at any time
- Game state is not persisted (bot restart ends all games)

## Example Game Session

```
User1: !pokerjoin 5000
Bot: 🃏 New Poker Table Created!
     @User1 is the host.
     Small Blind: 50$ | Big Blind: 100$

User2: !pokerjoin 5000
Bot: ✅ @User2 joined the table with 5,000$!

User1: !pokerstart
Bot: 🃏 Poker game started!
     Shuffle Hash: `a3f7c8d9...`
     Players have been dealt their hole cards via DM.
     
[Game State Embed]
Phase: Pre Flop
Pot: 150$
Current Bet: 100$

Players:
✅ User1 🎲: 4,950$ (bet: 50$) (small_blind)
✅ User2 ⏰: 4,900$ (bet: 100$) (big_blind)

Current Turn: User1 (30s remaining)

User1: !pokercall
Bot: User1 calls 50

[Updated Game State]

User2: !pokercheck
Bot: User2 checks

[Flop revealed - 3 cards]
[Continue betting rounds...]
[River revealed]
[Showdown]

Bot: 🏆 Hand Complete!
     Winner: User1
     Hand: Pair of Aces
     Hole Cards: A♠ A♥
     Won: 1,200$
     
     🔒 Shuffle Verification
     Hash: `a3f7c8d9...`
     Verified: ✅ Fair shuffle confirmed
```

## Logging and Debugging

The game maintains a detailed action log for:
- Join/leave events
- Shuffle hash generation
- Blind posting
- All player actions
- Community card reveals
- Winner determination

This log can be used for:
- Game replay functionality
- Debugging issues
- Dispute resolution
- Statistics tracking

## Performance Considerations

- **Memory**: Each game instance is lightweight (~1-2 KB)
- **CPU**: Hand evaluation is O(n choose 5) for n cards (negligible for 7 cards)
- **Concurrency**: Each channel can have one active game
- **Scalability**: Multiple tables across different channels work independently

## Known Limitations

1. **No Persistent Storage**: Games are lost on bot restart
2. **Single Hand**: Players must rejoin for additional hands
3. **No Side Pots (Multiple)**: Only single pot implementation (future enhancement)
4. **Fixed Blinds**: Blinds don't increase over time
5. **No Re-buys**: Players eliminated cannot re-enter mid-game

## Testing Recommendations

To test the poker implementation:

1. **Single Player Flow**: Try joining/leaving
2. **Two Player Game**: Complete a full hand
3. **Betting Actions**: Test each action type
4. **Turn Timer**: Wait for timeout to trigger
5. **Hand Evaluation**: Test various winning hands
6. **Edge Cases**: All-in scenarios, ties, single winner by fold
7. **Integration**: Verify balance changes and gamble tracking

## Support

For issues or questions:
- Check the `!assist` command for quick reference
- Review game logs for debugging
- Test in a private channel first
- Verify balance transactions

---

**Version**: 1.0  
**Last Updated**: January 2026  
**Maintainer**: Discord Bot Development Team
