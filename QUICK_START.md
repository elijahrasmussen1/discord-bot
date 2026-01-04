# Quick Start Guide - Texas Hold'em Poker

This guide will help you get started playing poker on the Discord bot quickly.

## For Players

### Joining a Poker Game

1. **Join or Create a Table**
   ```
   !pokerjoin 1000
   ```
   - This joins an existing table or creates a new one
   - The amount is your buy-in (deducted from your balance)
   - You can use k, m, b suffixes: `!pokerjoin 5k` for 5,000

2. **Wait for More Players**
   - Minimum 2 players required
   - Maximum 10 players per table
   - The first player to join becomes the host

3. **Start the Game** (host only)
   ```
   !pokerstart
   ```
   - You'll receive your hole cards via DM
   - The shuffle hash is shown for fairness verification

### During the Game

#### Your Turn Actions

When it's your turn, use these commands:

- **Check** (no bet to call)
  ```
  !pokercheck
  ```

- **Bet** (first bet in a round)
  ```
  !pokerbet 100
  ```

- **Call** (match current bet)
  ```
  !pokercall
  ```

- **Raise** (increase the bet)
  ```
  !pokerraise 200
  ```

- **Fold** (give up your hand)
  ```
  !pokerfold
  ```

#### Viewing the Table

```
!pokertable
```
Shows:
- Community cards
- Pot size
- Current bet
- All players and their stacks
- Whose turn it is

### Turn Timer

⏰ You have **30 seconds** to act when it's your turn
- If time runs out, you automatically fold
- Keep an eye on the timer shown in the table display

### Winning

At the end of the hand:
- Winner(s) are announced
- Their hand rank is shown
- Pot is distributed
- Shuffle verification is displayed for fairness
- Winnings are added to your balance

### Leaving the Game

**Before the game starts:**
```
!pokerleave
```
- Your buy-in is refunded

**After the game:**
- Wait for the hand to finish
- Your remaining chips are automatically returned
- Or use `!pokerend` (host only) to end immediately

## Quick Reference

### Command Summary

| Command | Usage | Description |
|---------|-------|-------------|
| `!pokerjoin` | `!pokerjoin 1000` | Join/create table |
| `!pokerstart` | `!pokerstart` | Start game (host) |
| `!pokercheck` | `!pokercheck` | Check |
| `!pokerbet` | `!pokerbet 100` | Bet amount |
| `!pokercall` | `!pokercall` | Call current bet |
| `!pokerraise` | `!pokerraise 200` | Raise by amount |
| `!pokerfold` | `!pokerfold` | Fold hand |
| `!pokertable` | `!pokertable` | View table state |
| `!pokerleave` | `!pokerleave` | Leave table |
| `!pokerend` | `!pokerend` | End game (host) |

### Poker Hand Rankings

From highest to lowest:

1. **Royal Flush** - A♠ K♠ Q♠ J♠ 10♠
2. **Straight Flush** - 9♥ 8♥ 7♥ 6♥ 5♥
3. **Four of a Kind** - K♠ K♥ K♦ K♣ 2♠
4. **Full House** - A♠ A♥ A♦ K♣ K♠
5. **Flush** - A♣ J♣ 8♣ 5♣ 2♣
6. **Straight** - 10♠ 9♥ 8♦ 7♣ 6♠
7. **Three of a Kind** - Q♠ Q♥ Q♦ 5♣ 2♠
8. **Two Pair** - J♠ J♥ 5♦ 5♣ 2♠
9. **Pair** - 10♠ 10♥ K♦ 5♣ 2♠
10. **High Card** - A♠ K♥ 8♦ 5♣ 2♠

## Example Game

```
Player1: !pokerjoin 1000
Bot: 🃏 New Poker Table Created!
     @Player1 is the host.

Player2: !pokerjoin 1000
Bot: ✅ @Player2 joined the table with 1,000$!

Player1: !pokerstart
Bot: 🃏 Poker game started!
     [Hole cards sent via DM]

[Game displays table state]
Phase: Pre Flop
Pot: 150$
Current Bet: 100$

Players:
✅ Player1 🎲: 950$ (bet: 50$) <- YOUR TURN
✅ Player2: 900$ (bet: 100$)

Player1: !pokercall
Bot: Player1 calls 50

Player2: !pokercheck
Bot: Player2 checks

[Flop revealed: 3♣ 6♠ Q♣]

Player2: !pokerbet 100
Bot: Player2 bets 100

Player1: !pokercall
Bot: Player1 calls 100

[Turn revealed: 9♠]

Player2: !pokercheck
Bot: Player2 checks

Player1: !pokercheck
Bot: Player1 checks

[River revealed: Q♠]

Player2: !pokerbet 200
Bot: Player2 bets 200

Player1: !pokerfold
Bot: Player1 folds

[Showdown]
🏆 Winner: Player2
Hand: Pair of Qs
Won: 800$
```

## Tips for New Players

1. **Start Small** - Use smaller buy-ins while learning
2. **Watch Your Balance** - Check with `!amount` before joining
3. **Read Your DMs** - Your hole cards are private
4. **Act Quickly** - You have 30 seconds per turn
5. **Use !pokertable** - Check the state anytime
6. **Ask Questions** - Use `!assist` for command help

## Common Issues

### "Insufficient balance"
- Use `!amount` to check your balance
- You need enough for the buy-in

### "Not your turn"
- Check `!pokertable` to see whose turn it is
- Wait for the ⏰ indicator next to your name

### "Cannot check"
- There's a bet to call
- Use `!pokercall` or `!pokerfold` instead

### Didn't receive hole cards
- Check your Discord DMs
- Make sure you allow DMs from server members

## Getting Help

- `!assist` - View all bot commands
- `!pokertable` - Check current game state
- Read POKER_DOCUMENTATION.md for detailed rules

---

**Have fun and play responsibly!** 🃏
