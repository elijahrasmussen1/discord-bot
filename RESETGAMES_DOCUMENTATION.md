# 🔄 Reset Games Command Documentation

## Overview

The `!resetgames` command allows members to safely cancel all their active games and receive appropriate refunds. This prevents users from getting stuck with broken or unresponsive games.

## Purpose

**Problem Solved:**
- Members sometimes don't click buttons/embeds in time
- Games become "stuck" or "broken"
- Users can't start new games because old ones are still active
- Frustration from locked-out games

**Solution:**
- One command cancels all active games
- Automatic refunds for pending bets
- No money glitches or exploits possible
- Clean slate for the user

---

## Command Usage

### Basic Command
```
!resetgames
```

**Parameters:** None required

**Who Can Use:** All members

**Cooldown:** None

---

## How It Works

### Games Covered

The command checks and cancels:

1. **Coinflip (!cf)**
   - Refunds: Pending bet amount
   
2. **Flip & Chase (!flipchase)**
   - Refunds: Original bet amount
   
3. **Blackjack (!blackjack)**
   - Refunds: Current bet amount
   
4. **Lucky Number (!luckynumber)**
   - Refunds: Pending bet amount
   
5. **Crash (!crash)**
   - Refunds: Active bet amount
   
6. **Limbo (!limbo)**
   - Refunds: Current bet amount
   
7. **Rock Paper Scissors (!rps)**
   - Auto-handled by button timeout (60s)
   - No persistent state to clean
   
8. **Poker (!pokerjoin)**
   - Refunds: Chips currently in pot
   - Removes you from the table
   - Game continues if 2+ players remain

### Games NOT Covered

**PvP Games** (no refunds possible):
- Gladiator Fights - requires opponent action
- Risky Lumberjack - requires opponent action

These games involve another player and cannot be unilaterally cancelled.

---

## Refund Logic

### When Refunds Are Given

✅ **You WILL get refunded:**
- Bet is placed but game not resolved
- Game is waiting for your action
- Chips are in an active pot (poker)
- Game is in progress state

❌ **You will NOT get refunded:**
- Game already completed
- Bet already won or lost
- Game doesn't exist in active state
- Already received payout

### Anti-Exploit Protection

**Built-in Safeguards:**
1. Only refunds active games (not completed ones)
2. Can't double-refund the same game
3. Removes game from active list immediately
4. Balance updates are atomic (no race conditions)
5. Can't use to escape losses (only refunds pending bets)

---

## Examples

### Example 1: Stuck Blackjack Game

**Scenario:** Started blackjack but buttons stopped working

```
User: !blackjack 5000
Bot: [Shows cards and buttons]
User: [Buttons don't respond]
User: !resetgames
```

**Result:**
```
🔄 Games Reset
Your active games have been cancelled.

Games Cancelled:
• Blackjack

💰 Total Refunded: 5,000$

Refund Breakdown:
• Blackjack: 5,000$

New Balance: 15,000$
```

### Example 2: Multiple Active Games

**Scenario:** Has coinflip, crash, and limbo all running

```
User: !resetgames
```

**Result:**
```
🔄 Games Reset
Your active games have been cancelled.

Games Cancelled:
• Coinflip
• Crash  
• Limbo

💰 Total Refunded: 23,500$

Refund Breakdown:
• Coinflip: 10,000$
• Crash: 8,500$
• Limbo: 5,000$

New Balance: 73,500$
```

### Example 3: No Active Games

**Scenario:** User has no games running

```
User: !resetgames
```

**Result:**
```
ℹ️ No Active Games
You don't have any active games to cancel.

Use this command when you have stuck or broken games
```

### Example 4: Poker Table

**Scenario:** Playing poker but need to leave

```
User: !resetgames
```

**Result:**
```
🔄 Games Reset
Your active games have been cancelled.

Games Cancelled:
• Poker (Channel 123456789)

💰 Total Refunded: 2,500$

Refund Breakdown:
• Poker (Channel 123456789): 2,500$

New Balance: 12,500$
```

---

## Technical Details

### Implementation

**Game State Tracking:**
- `active_coinflip` - Dictionary of user_id → game data
- `active_flip_chase` - Dictionary of user_id → game data
- `active_blackjack` - Dictionary of user_id → BlackjackGame object
- `lucky_number_games` - Dictionary of user_id → game data
- `crash_games` - Dictionary of user_id → game data
- `limbo_games` - Dictionary of user_id → game data
- `poker_manager.active_games` - Dictionary of channel_id → PokerGame object

**Refund Process:**
1. Check if user has active game
2. Extract bet amount from game state
3. Call `update_balance(user_id, bet_amount)`
4. Remove game from active dictionary
5. Track refund for response

**Safety Features:**
- Uses atomic balance updates
- Checks game existence before refund
- Removes from active list after refund
- No way to refund completed games
- Transaction logging via update_balance

---

## Use Cases

### When to Use

✅ **Good reasons to use:**
- Buttons/embeds not responding
- Game seems frozen or stuck
- Need to leave but game is active
- Want a clean slate
- Accidentally started wrong game
- Bot lagged and game is broken

❌ **Bad reasons to use:**
- Trying to escape a loss (won't work - game must be active)
- Game already resolved (won't refund)
- Want to cheat the system (protected against this)

---

## FAQ

### Q: Can I use this to undo losses?
**A:** No. The command only cancels active/pending games. If the game already resolved (you won or lost), no refund is given.

### Q: Will this work on completed games?
**A:** No. Only active games that are still waiting for your action can be cancelled.

### Q: Can I abuse this for money glitches?
**A:** No. The system only refunds bets that haven't been resolved. You can't get money you didn't have.

### Q: What happens to poker games?
**A:** You're removed from the table and refunded your chips in the pot. If less than 2 players remain, the game ends.

### Q: Does this affect other players?
**A:** Only in poker games. In poker, if your leave causes less than 2 players to remain, the game ends.

### Q: Is there a cooldown?
**A:** No cooldown. Use whenever you need to reset stuck games.

### Q: Can I reset someone else's games?
**A:** No. You can only reset your own active games.

### Q: What if I have no active games?
**A:** You'll get a message saying you have no active games to cancel.

---

## Error Messages

### No Active Games
```
ℹ️ No Active Games
You don't have any active games to cancel.
```
**Meaning:** You don't have any games in an active state.

---

## Integration

### With Provably Fair System

**Important Notes:**
- Cancelled games are NOT logged in provably fair bets
- Nonce does NOT increment for cancelled games
- Only completed games appear in !verify history
- Refunds don't count toward gambling requirement

### With Balance System

**Balance Updates:**
- Refunds use standard `update_balance()` function
- Atomic database transactions prevent glitches
- Balance immediately reflects refund
- No race conditions possible

---

## Security

### Anti-Exploit Measures

1. **State Validation**
   - Checks game exists before refund
   - Verifies game is actually active
   - Prevents double-refunds

2. **Balance Protection**
   - Uses atomic updates
   - Can't refund more than bet
   - Transaction logged

3. **Game Isolation**
   - Each game checked independently
   - Can't affect other users' games
   - Clean removal from active state

4. **No Completion Refunds**
   - Can't cancel resolved games
   - Can't undo actual losses
   - Only pending bets refunded

---

## Command Location

**File:** `bot.py`  
**Line Range:** ~8965-9130  
**Section:** Reset Games Command

**Dependencies:**
- `active_coinflip` - Coinflip game state
- `active_flip_chase` - Flip & Chase state
- `active_blackjack` - Blackjack game state
- `lucky_number_games` - Lucky number state
- `crash_games` - Crash game state
- `limbo_games` - Limbo game state
- `poker_manager` - Poker game manager
- `update_balance()` - Balance update function
- `format_money()` - Money formatting function

---

## Testing Recommendations

### Test Cases

1. **Cancel single active game**
   - Start coinflip
   - Use !resetgames
   - Verify refund received
   - Verify can start new game

2. **Cancel multiple games**
   - Start coinflip, crash, and limbo
   - Use !resetgames
   - Verify all refunded
   - Verify correct total

3. **No active games**
   - Use !resetgames with no games
   - Verify friendly message
   - Verify no balance change

4. **Poker game cancellation**
   - Join poker table
   - Place bet
   - Use !resetgames
   - Verify removed from table
   - Verify refund received

5. **Exploit attempts**
   - Complete game (win or lose)
   - Try !resetgames
   - Verify no refund given

---

## Best Practices

### For Members

**Do:**
- Use when games are genuinely stuck
- Use when buttons aren't working
- Use to clean up before starting new games

**Don't:**
- Use to try to undo losses
- Spam the command
- Expect refunds on completed games

### For Administrators

**Monitor:**
- Excessive use of command (abuse detection)
- Refund amounts (for anomalies)
- Game state integrity

**Support:**
- Help users understand when to use it
- Investigate if games frequently get stuck
- Fix underlying issues causing stuck games

---

## Version History

### v1.0.0 (Current)
- Initial implementation
- Covers 8 gambling games
- Poker integration
- Anti-exploit protection
- Comprehensive refund logic

---

## Summary

The `!resetgames` command provides a safe, user-friendly way to cancel stuck or broken games with appropriate refunds. It's designed with multiple safeguards to prevent money glitches while giving users control over their gaming experience.

**Key Points:**
✅ Cancels all active games  
✅ Refunds pending bets  
✅ No money glitches possible  
✅ Works with all 8 gambling games  
✅ Poker integration included  
✅ Safe and user-friendly  

Use it whenever you need a fresh start!
