# Rock Paper Scissors Game Documentation

## Overview

The Rock Paper Scissors (RPS) game is a fun, interactive gambling game that uses **provably fair** technology and Discord's button interface to provide a professional gaming experience.

---

## Features

### ✅ Provably Fair Integration
- Uses HMAC-SHA256 cryptographic system
- Modulo 3 results: 0 = Rock, 1 = Paper, 2 = Scissors
- Every game is fully verifiable with `!verify` command
- Seed information displayed in all results

### ✅ Interactive Discord Buttons
- 3 professional emoji buttons:
  - 🪨 Rock
  - 📄 Paper
  - ✂️ Scissors
- Styled with Discord's primary blue button style
- 60-second timeout for player selection
- Buttons automatically disable after selection

### ✅ Game Mechanics
- **Win**: 2x payout (100% profit)
- **Tie**: Get your bet back (0% loss)
- **Loss**: Lose your bet

---

## How to Play

### Starting a Game

```
!rps <amount>
```

**Examples:**
- `!rps 100` - Bet 100$
- `!rps 10k` - Bet 10,000$
- `!rps 5m` - Bet 5,000,000$

**Requirements:**
- Minimum bet: 100$
- Must have sufficient balance
- One game per player at a time

### Making Your Choice

After starting the game, you'll see an embed with 3 buttons below it:
1. Click **🪨 Rock** to choose Rock
2. Click **📄 Paper** to choose Paper
3. Click **✂️ Scissors** to choose Scissors

You have 60 seconds to make your selection.

### Game Rules

Classic Rock Paper Scissors rules:
- **🪨 Rock beats ✂️ Scissors**
- **📄 Paper beats 🪨 Rock**
- **✂️ Scissors beats 📄 Paper**

---

## Payouts

### Win (2x payout)
Your choice beats the house choice:
- Bet: 1,000$
- Payout: 2,000$
- Net Profit: +1,000$

### Tie (1x payout)
Both make the same choice:
- Bet: 1,000$
- Payout: 1,000$
- Net Profit: 0$

### Loss (0x payout)
House choice beats your choice:
- Bet: 1,000$
- Payout: 0$
- Net Profit: -1,000$

---

## Visual Example

### Initial Embed
```
🎮 Rock Paper Scissors
Place your bet: 1,000$

Choose your move below! (60 seconds)
House will reveal their choice after you pick

🪨 Rock vs 📄 Paper
Paper wins

📄 Paper vs ✂️ Scissors
Scissors wins

✂️ Scissors vs 🪨 Rock
Rock wins

Win: 2x payout (2,000$)
Tie: Get bet back (1,000$)
Lose: Lose bet (1,000$)

🔐 Provably Fair
Nonce: 42 | Client: abc123...
Seed Hash: def456...
Use !verify to verify fairness
```

**Below the embed:**
- [ 🪨 Rock ] [ 📄 Paper ] [ ✂️ Scissors ]

### Result Embed (Example: You Win)
```
🎮 Rock Paper Scissors - Result
🎉 You Win!

Your Choice: 📄 Paper
House Choice: 🪨 Rock

Bet Amount: 1,000$
Payout: 2,000$
Net Profit: +1,000$

New Balance: 15,000$

🔐 Provably Fair
Nonce: 42 | Client: abc123...
Seed Hash: def456...
Use !verify to verify fairness
```

---

## Provably Fair Verification

### How It Works

1. **Pre-Commitment**: Server seed hash is shown before your choice
2. **Deterministic Result**: House choice is generated using HMAC-SHA256
3. **Post-Verification**: You can verify the result was fair

### Algorithm

```
Message = "{client_seed}:{nonce}"
HMAC-SHA256(server_seed, message) → hash
result = int(hash[:8], 16) % 3

0 = Rock
1 = Paper
2 = Scissors
```

### Verification Commands

**Check seed info before playing:**
```
!fairinfo
```
Shows current server seed hash and system info.

**Check your seeds after playing:**
```
!myseeds
```
Shows your client seed and current nonce.

**Verify a specific game:**
```
!verify 123
```
Verifies bet #123 using the revealed seeds.

**See revealed seeds:**
```
!revealedseed
```
Shows all previously revealed server seeds.

### Manual Verification

You can verify any RPS game manually using Python:

```python
import hmac
import hashlib

# Values from your game (get from !verify command)
server_seed = "revealed_server_seed_here"
client_seed = "your_client_seed_here"
nonce = 42

# Calculate result
message = f"{client_seed}:{nonce}"
hash_value = hmac.new(
    server_seed.encode(),
    message.encode(),
    hashlib.sha256
).hexdigest()

result = int(hash_value[:8], 16) % 3

# Map result
choices = ["🪨 Rock", "📄 Paper", "✂️ Scissors"]
house_choice = choices[result]

print(f"House Choice: {house_choice}")
# Should match what the bot showed
```

---

## User Experience Features

### Professional Design
- Clean, colorful Discord embeds
- Clear visual hierarchy
- Emoji-enhanced messages
- Consistent branding

### Interactive Elements
- Instant button feedback
- Disabled buttons after selection
- Timeout handling
- Error messages for invalid actions

### Balance Integration
- Immediate balance updates
- Clear profit/loss display
- Transaction tracking
- Gamble requirement counting

---

## Common Scenarios

### Successful Game
1. Player: `!rps 5000`
2. Bot: Shows embed with 3 buttons
3. Player: Clicks 📄 Paper button
4. Bot: Shows result - Player wins!
5. Balance updated: +5,000$

### Timeout
1. Player: `!rps 1000`
2. Bot: Shows embed with 3 buttons
3. Player: Doesn't click anything for 60 seconds
4. Bot: Buttons become disabled
5. Bet is refunded automatically

### Insufficient Balance
1. Player: `!rps 1000000` (has only 500$)
2. Bot: "❌ Insufficient balance! You have 500$, but need 1,000,000$"
3. No bet is placed

### Invalid Amount
1. Player: `!rps abc`
2. Bot: "❌ Invalid amount! Use formats like: `10k`, `5m`, `1b`"
3. No bet is placed

---

## Tips for Players

### Strategy Tips
- This is a pure chance game (33.33% win, 33.33% tie, 33.33% loss)
- No pattern can be predicted due to cryptographic randomness
- Expected value: -16.67% per game (house edge)
- Manage your bankroll carefully

### Best Practices
1. Always check `!fairinfo` before playing
2. Verify important wins with `!verify`
3. Use custom client seeds (`!setseed`) for extra security
4. Set betting limits for yourself
5. Remember: Gambling should be fun, not profitable

### Provably Fair Usage
- Check server seed hash before betting
- Keep track of your nonce
- Verify results after seed rotation
- Report any discrepancies immediately

---

## Technical Details

### Game Logic
- Implemented in `bot.py`
- Uses `discord.ui.View` for button interface
- Integrates with `provably_fair.py` module
- 60-second timeout per game

### Security Features
- CSPRNG (Python `secrets` module)
- HMAC-SHA256 result generation
- SHA-256 hash commitment
- Server-side validation only
- No client-side manipulation possible

### Database Integration
- Balance updates via `update_balance()`
- Gamble tracking via `add_gambled()`
- Bet logging in provably_fair_bets table
- Transaction history maintained

---

## Troubleshooting

### "This is not your game!"
- You clicked a button on someone else's game
- Start your own game with `!rps <amount>`

### "You already made your choice!"
- You already clicked a button
- Wait for the result to be displayed

### Buttons are disabled
- The game timed out (60 seconds)
- You need to start a new game

### "Insufficient balance!"
- You don't have enough balance
- Check your balance with `!amount`
- Deposit more or bet a smaller amount

---

## Integration with Other Systems

### Balance System
- Bet deducted immediately on game start
- Winnings credited on button click
- Ties refund the bet amount
- All transactions atomic

### Gamble Tracking
- Every bet counts toward your gamble requirement
- Visible in `!amount` command
- Tracked in database
- Used for withdrawal eligibility

### Provably Fair System
- Same system as all other games
- Shared server seed across games
- Per-user nonce incrementing
- Complete bet history logging

---

## Future Enhancements

Potential features for future versions:
- Tournament mode
- Leaderboards for RPS
- Statistics tracking (win/loss ratio)
- Best-of-three matches
- Side bets between players

---

## FAQ

**Q: Can the house see my choice before revealing theirs?**
A: No. The house choice is generated cryptographically BEFORE you click any button, using provably fair algorithms.

**Q: How do I know the house didn't change their choice?**
A: The house choice is pre-determined by the server seed (hash shown before game) and your nonce. Verify with `!verify` command.

**Q: What happens if I don't click anything?**
A: After 60 seconds, the buttons disable and your bet is refunded automatically.

**Q: Can I play multiple games at once?**
A: No, you can only have one RPS game active at a time.

**Q: Is there a maximum bet?**
A: Only your balance limits the maximum bet.

**Q: Does this count toward my gamble requirement?**
A: Yes, all bets count toward the 30% gamble requirement for withdrawals.

---

## Support

If you encounter issues:
1. Check your balance with `!amount`
2. Verify the game with `!verify`
3. Check `!fairinfo` for system status
4. Contact an admin if problems persist

---

## Conclusion

Rock Paper Scissors is a fun, fair, and interactive gambling game that combines classic gameplay with modern cryptographic security. Enjoy the game responsibly and always remember: the house has a mathematical edge, so play for entertainment, not profit!

**Good luck! 🎮🪨📄✂️**
