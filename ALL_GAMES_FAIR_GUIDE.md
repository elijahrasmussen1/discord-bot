# How to Verify All Games Are Fair

This guide shows you how to verify that every gambling game on the bot is provably fair and cannot be rigged by anyone (including admins).

---

## 📋 Quick Summary

**ALL 4 games use provably fair:**
- ✅ Coinflip (!cf)
- ✅ FlipChase (!flipchase)
- ✅ Slots (!slots)
- ✅ Blackjack (!blackjack)

**What this means:** Every result is generated using cryptographic algorithms (HMAC-SHA256) that cannot be manipulated. You can verify any bet yourself.

---

## 🔐 How It Works

### The Three Seeds System:

1. **Server Seed** (Secret until revealed)
   - Generated with cryptographically secure random number generator
   - Hash published BEFORE any bets
   - Never changed until rotation
   - Revealed after rotation for verification

2. **Client Seed** (Public, you can set it)
   - Unique to each player
   - You can customize it with `!setseed <hex>`
   - Used in combination with server seed

3. **Nonce** (Counter, increments each bet)
   - Starts at 0 for each player
   - Increases by 1 after each bet
   - Ensures different results each time

### The Algorithm:

```
Message = "{client_seed}:{nonce}"
HMAC-SHA256(server_seed, message) → hash
Take first 8 hex chars → convert to integer → apply modulo
```

**Result:** Deterministic (same inputs = same output) but unpredictable (you can't guess without server seed).

---

## 🎮 Verification by Game

### Coinflip (!cf)

**How it generates results:**
- Modulo 2 (0 = Heads, 1 = Tails)
- Single result per bet

**Verification steps:**
1. Play: `!cf 1000 heads`
2. Bot shows result with seed info
3. Use `!verify [bet#]` to check
4. Or manually calculate (see example below)

**Manual verification:**
```python
import hmac, hashlib

# From your bet
server_seed = "revealed_after_rotation"  # Get from !revealedseed
client_seed = "your_client_seed"  # Get from !myseeds
nonce = 42  # From bet result

# Calculate
message = f"{client_seed}:{nonce}"
hash_result = hmac.new(server_seed.encode(), message.encode(), hashlib.sha256).hexdigest()
result = int(hash_result[:8], 16) % 2

print(f"Result: {'Heads' if result == 0 else 'Tails'}")
```

---

### FlipChase (!flipchase)

**How it generates results:**
- Each flip in the chain uses provably fair
- Modulo 2 (0 = Heads, 1 = Tails)
- Nonce increments with each flip

**Verification steps:**
1. Play: `!flipchase 5000`
2. Chase multiple rounds
3. Each flip has its own nonce
4. Verify each flip individually with `!verify`

**Example chain:**
```
Initial bet: Nonce 10, Result: Heads (fair ✓)
First chase: Nonce 11, Result: Tails (fair ✓)
Second chase: Nonce 12, Result: Heads (fair ✓)
```

---

### Slots (!slots)

**How it generates results:**
- 9 results for 3x3 grid (one per symbol)
- Modulo 7 maps to symbols:
  - 0 = 🍒 (Cherry)
  - 1 = 🍋 (Lemon)
  - 2 = 🍊 (Orange)
  - 3 = 🍇 (Grape)
  - 4 = 💎 (Diamond)
  - 5 = ⭐ (Star)
  - 6 = 7️⃣ (Seven)

**Verification steps:**
1. Play: `!slots 1000`
2. Bot shows grid with seed info
3. Use `!verify` or manually verify

**Manual verification:**
```python
import hmac, hashlib

server_seed = "revealed_seed"
client_seed = "your_seed"
nonce = 17

message = f"{client_seed}:{nonce}"
hash_result = hmac.new(server_seed.encode(), message.encode(), hashlib.sha256).hexdigest()

symbols = ["🍒", "🍋", "🍊", "🍇", "💎", "⭐", "7️⃣"]
grid = []

# Generate 9 results
for i in range(9):
    offset = (i * 8) % (len(hash_result) - 8)
    hex_slice = hash_result[offset:offset+8]
    result = int(hex_slice, 16) % 7
    grid.append(symbols[result])

# Display as 3x3
print(f"{grid[0]} {grid[1]} {grid[2]}")
print(f"{grid[3]} {grid[4]} {grid[5]}")
print(f"{grid[6]} {grid[7]} {grid[8]}")
```

---

### Blackjack (!blackjack)

**How it generates results:**
- 52 results for deck shuffle
- Creates deterministic but unpredictable deck order
- Uses 2 decks (104 cards) for standard blackjack

**Verification steps:**
1. Play: `!blackjack 5000`
2. Game completes with seed info
3. Verify deck order was fair

**Manual verification:**
```python
import hmac, hashlib

server_seed = "revealed_seed"
client_seed = "your_seed"
nonce = 89

message = f"{client_seed}:{nonce}"
hash_result = hmac.new(server_seed.encode(), message.encode(), hashlib.sha256).hexdigest()

# Generate 52 shuffle results
shuffle_results = []
for i in range(52):
    offset = (i * 8) % (len(hash_result) - 8)
    hex_slice = hash_result[offset:offset+8]
    result = int(hex_slice, 16) % 104  # For 2-deck system
    shuffle_results.append(result)

# Create ordered deck
suits = ['♠️', '♥️', '♣️', '♦️']
ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
ordered_deck = []
for _ in range(2):  # 2 decks
    for suit in suits:
        for rank in ranks:
            ordered_deck.append(f"{rank}{suit}")

# Apply shuffle
shuffled_deck = []
remaining = ordered_deck.copy()
for result in shuffle_results:
    if remaining:
        index = result % len(remaining)
        shuffled_deck.append(remaining.pop(index))

print("First 5 cards:", shuffled_deck[:5])
```

---

## 🛠️ Verification Commands

### !fairinfo
Shows current server seed hash and system stats.
```
!fairinfo
→ Active Seed Hash: e0741c69...
→ Total Bets: 1,247
→ Total Users: 42
```

### !myseeds
Shows your client seed and current nonce.
```
!myseeds
→ Your Client Seed: abc12345...
→ Your Nonce: 17
```

### !setseed <hex>
Set a custom client seed (must be hex).
```
!setseed deadbeefcafebabe1234567890abcdef
→ ✅ Client seed updated!
```

### !verify [bet#]
Verify a past bet (leave empty for last bet).
```
!verify 123
→ ✅ VERIFIED - Result is correct!
→ Server Seed Hash: e0741c...
→ Client Seed: abc123...
→ Nonce: 42
→ Result: 1 (Tails)
```

### !revealedseed
View all revealed server seeds (after rotation).
```
!revealedseed
→ Seed 1: cbb3a0c8... (Rotated: 2024-01-04)
→ Hash: 6659f599... ✓ MATCHES
```

### !rotateseed (Owner Only)
Rotates server seed and reveals old one.
```
!rotateseed
→ Old seed revealed: cbb3a0c8...
→ New seed hash: 405cfb84...
```

---

## 🔍 Step-by-Step: Full Verification

### Before Betting:
1. Run `!fairinfo` to see current server seed hash
2. Write down the hash (this is your guarantee)
3. Optionally set custom client seed with `!setseed`

### While Betting:
1. Play any game (coinflip, slots, blackjack, flipchase)
2. Bot shows result with seed info
3. Note your nonce (increases each bet)

### After Server Seed Rotation:
1. Run `!revealedseed` to get old server seed
2. Verify the revealed seed matches the original hash
3. Use revealed seed to recalculate all your bets
4. If they match → PROVEN FAIR ✅
5. If they don't match → SOMETHING IS WRONG ❌

---

## 📊 What You're Checking

### Hash Commitment:
- Server publishes hash BEFORE you bet
- Server cannot change seed without changing hash
- After rotation, revealed seed must match hash
- If it matches → server didn't cheat ✅

### Result Generation:
- HMAC-SHA256 is one-way (cannot reverse)
- Server cannot predict your client seed
- Result is deterministic (same inputs = same output)
- You can independently verify each result

### Transparency:
- Every bet logged in database
- Full parameters stored (seeds, nonce, result)
- You can audit your entire betting history
- System is completely open for inspection

---

## ❓ Common Questions

### Q: Can the server manipulate results?
**A:** No. The server seed hash is published before you bet. If the server changes the seed, the hash won't match when revealed.

### Q: Can the server see my bets before they happen?
**A:** No. Your client seed is involved in the calculation, and the server cannot predict the exact moment you'll bet (which affects the nonce).

### Q: What if I don't trust the hash commitment?
**A:** You can set your own client seed with `!setseed`. Even if the server had a "magic" server seed, your custom client seed ensures fair results.

### Q: Can I verify bets immediately?
**A:** You can verify the hash matches what was published. Full verification (recalculating results) requires waiting for server seed rotation.

### Q: How often are seeds rotated?
**A:** By admin decision, but recommended weekly or after major betting volume. When rotated, old seed is revealed for verification.

### Q: What if verification fails?
**A:** Contact admins immediately. If a revealed seed doesn't match its hash, that's proof of tampering.

---

## 🎓 Learn More

- **PROVABLY_FAIR_DOCUMENTATION.md** - Technical details
- **SECURITY_REPORT.md** - Security analysis
- **POKER_DOCUMENTATION.md** - Poker-specific fairness

---

## ✅ Trust But Verify

**The beauty of provably fair systems:** You don't have to trust anyone. You can verify everything yourself using mathematics and cryptography.

**Every bet. Every game. Completely transparent.**

---

**Questions? Use `!fairinfo` or contact an admin.**
