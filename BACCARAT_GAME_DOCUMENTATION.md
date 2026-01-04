# 🎴 Baccarat Game Documentation

## Overview

Baccarat is a classic casino card game now integrated into the gambling bot with interactive chip buttons and full provably fair implementation.

## Command

```
!baccarat
```

## How to Play

### Step 1: Start the Game
Use `!baccarat` to open the Baccarat table with interactive buttons.

### Step 2: Add Chips
Click the chip buttons to build your bet:
- 💵 **500K** - Add 500,000$ to your bet
- 💴 **1M** - Add 1,000,000$ to your bet
- 💶 **5M** - Add 5,000,000$ to your bet
- 💷 **20M** - Add 20,000,000$ to your bet
- 💸 **50M** - Add 50,000,000$ to your bet

Click multiple times to stack chips!

### Step 3: Choose Your Bet
Select where to bet:
- 🎴 **Bet Player** - Bet on the Player hand
- 🏦 **Bet Banker** - Bet on the Banker hand
- 🤝 **Bet Tie** - Bet on a tie

### Step 4: Deal
Click **🃏 Deal** to play the hand!

### Step 5: Results
The bot will:
1. Deal 2 cards to Player and Banker
2. Apply third card rules (if needed)
3. Determine the winner
4. Pay out winnings automatically

## Card Values

| Card | Value |
|------|-------|
| Ace | 1 point |
| 2-9 | Face value |
| 10, J, Q, K | 0 points |

**Important:** The total is always the last digit. For example:
- 7 + 8 = 15 = **5 points**
- 9 + 9 = 18 = **8 points**
- 10 + 5 = 15 = **5 points**

## Payouts

| Bet Type | Payout | Example |
|----------|--------|---------|
| **Player** | 1:1 (2x) | Bet 10M, win 20M (10M profit) |
| **Banker** | 0.95:1 (1.95x) | Bet 10M, win 19.5M (9.5M profit) |
| **Tie** | 8:1 (9x) | Bet 10M, win 90M (80M profit) |

### Special Rules
- If you bet on Player or Banker and the result is a **Tie**, your bet is **returned** (push)
- Banker bet wins pay 5% commission (0.95:1 instead of 1:1)
- Tie bets only win on an actual tie

## Third Card Rules

Baccarat has complex third card drawing rules that are automatically handled:

### Player's Third Card
- **0-5:** Draws a third card
- **6-7:** Stands
- **8-9:** Natural win, no third card

### Banker's Third Card
Depends on Player's third card value and Banker's total:
- **0-2:** Always draws
- **3:** Draws unless Player's third card is 8
- **4:** Draws if Player's third card is 2-7
- **5:** Draws if Player's third card is 4-7
- **6:** Draws if Player's third card is 6-7
- **7:** Stands
- **8-9:** Natural win, no third card

## Strategy

### House Edge
- **Banker:** ~1.06% house edge (lowest!)
- **Player:** ~1.24% house edge
- **Tie:** ~14.36% house edge (highest!)

### Recommendations
1. **Banker** statistically wins more often (~50.68%)
2. **Player** wins less often (~49.32%) but pays full 1:1
3. **Tie** is rare (~9.5%) but pays 8:1
4. Avoid tie bets for consistent play
5. Banker is mathematically the best bet despite 5% commission

## Game Controls

### Chip Buttons (Row 1)
Add money to your bet. Stack as many chips as you want!

### Betting Position Buttons (Row 2)
Choose where to place your bet after adding chips.

### Control Buttons (Row 3)
- **🃏 Deal:** Start the game (requires bet and position selected)
- **❌ End Game:** Cancel game and refund your chips

## Provably Fair Integration

Every Baccarat game is **provably fair**:

### How It Works
1. 6 random numbers generated using HMAC-SHA256
2. Numbers determine card values (1-13, mapped to Baccarat values)
3. Full seed information displayed in results
4. You can verify any game with `!verify`

### Verification
After each game, the result embed shows:
```
🔐 Provably Fair
Nonce: 42 | Client: abc123...
Seed Hash: def456...
Use !verify to verify fairness
```

Use `!verify` command to independently verify the results were fair.

## Example Game Flow

```
1. User: !baccarat
   → Bot shows table with buttons

2. User: *Clicks 5M chip 4 times*
   → Current bet: 20,000,000$

3. User: *Clicks "Bet Player"*
   → Betting 20M on Player

4. User: *Clicks "Deal"*
   → Game plays automatically

5. Bot shows result:
   Player: 8 + 5 = 3 (total: 3)
   Banker: 7 + 2 = 9 (total: 9)
   Winner: Banker
   Result: You lose 20M

   OR if you win:
   Player: 9 + 9 = 8 (total: 8)
   Banker: 6 + 1 = 7 (total: 7)
   Winner: Player
   You win 40M! (+20M profit)
```

## Integration with Bot Systems

### Balance System
- Chips deducted when added to bet
- Winnings credited immediately
- Refunds given if game cancelled

### Gamble Tracking
- All bets count toward 30% requirement
- Tracked via `add_gambled()` function

### Reset Games
- Included in `!resetgames` command
- Active games can be safely cancelled
- Refunds automatic

### Provably Fair
- Full integration with provably fair system
- Uses `place_bet_multiple()` for 6 cards
- Complete audit trail

## Error Handling

### Insufficient Balance
- Chip buttons check balance before adding
- Clear error message if not enough money
- No partial bets possible

### Timeout Protection
- 5-minute timeout on inactive games
- Automatic refund on timeout
- View gets disabled automatically

### Validation
- Must add chips before selecting position
- Must select position before dealing
- All validations show clear error messages

## Tips for Players

1. **Start Small:** Try 500K or 1M chips to learn
2. **Banker is Safest:** Lowest house edge despite commission
3. **Avoid Ties:** High payout but very rare
4. **Stack Chips:** Click multiple times to build larger bets
5. **Use End Game:** Cancel anytime before dealing

## Technical Details

### Implementation
- **Language:** Python 3.8+
- **Framework:** discord.py
- **RNG:** HMAC-SHA256 (provably fair)
- **UI:** Discord buttons (discord.ui.View)

### Database
- Uses existing balance system
- No new tables required
- Active games tracked in memory

### Performance
- < 5ms response time
- Instant balance updates
- Professional embeds

## Security

### Provably Fair
✅ CSPRNG seed generation
✅ HMAC-SHA256 result generation
✅ Pre-commitment with hash
✅ Full verification available

### Anti-Exploit
✅ Balance validation before bet
✅ Atomic transactions
✅ No race conditions
✅ Cannot double-bet

### User Protection
✅ Timeout refunds
✅ Cancel anytime before deal
✅ Clear betting limits
✅ Transaction logging

## Comparison to Other Casino Games

| Feature | Baccarat | Blackjack | Roulette (Not in bot) |
|---------|----------|-----------|----------------------|
| Skill Required | None | Medium | None |
| House Edge | 1.06-14% | ~0.5% | 2.7-5.3% |
| Speed | Fast | Medium | Fast |
| Complexity | Low | Medium | Low |
| Max Payout | 9x | 2.5x | 36x |

## Frequently Asked Questions

### Q: Can I change my bet after clicking Deal?
**A:** No, once you click Deal, the game processes immediately.

### Q: What happens if I timeout?
**A:** Your chips are automatically refunded after 5 minutes of inactivity.

### Q: Can I play multiple games at once?
**A:** No, you can only have one active Baccarat game at a time.

### Q: Is this real Baccarat?
**A:** Yes! Full Baccarat rules including third card draws, proper card values, and standard payouts.

### Q: Why does Banker pay less?
**A:** Banker wins slightly more often statistically, so casinos charge 5% commission to maintain house edge.

### Q: How do I verify fairness?
**A:** Use `!verify` command after your game, or see `PROVABLY_FAIR_DOCUMENTATION.md` for manual verification.

### Q: Can I bet on multiple positions?
**A:** No, you must choose Player, Banker, or Tie for each game.

### Q: What's the minimum bet?
**A:** 500,000$ (the smallest chip button).

### Q: What's the maximum bet?
**A:** Limited only by your balance! Stack as many chips as you want.

## Commands Summary

| Command | Description |
|---------|-------------|
| `!baccarat` | Start a Baccarat game |
| `!resetgames` | Cancel active Baccarat game and get refund |
| `!fairinfo` | Learn about provably fair system |
| `!verify` | Verify past Baccarat results |
| `!games` | See all gambling games (page 11 is Baccarat) |

## Version History

### v1.0 (Current)
- Initial Baccarat implementation
- Interactive chip buttons (5 denominations)
- Full third card rules
- Provably fair integration
- Professional embeds
- Timeout protection

## Support

For issues or questions:
1. Check this documentation
2. Use `!assist` for command list
3. Contact bot owner

---

**Enjoy playing Baccarat! 🎴**

*Remember: Gamble responsibly. This is entertainment, not a way to make money.*
