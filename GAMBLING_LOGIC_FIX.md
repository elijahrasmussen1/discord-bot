# Gambling Logic Fix

## Problem
The gambling requirement was being recalculated on every bet based on the current balance, making it impossible for users to reach 0 remaining and withdraw their funds.

### Example of the bug:
1. Deposit 100M → Required: 30M, Gambled: 0, Remaining: 30M
2. Bet 10M (lose) → Balance: 90M, Required: **27M** (recalculated!), Gambled: 10M, Remaining: 17M
3. Bet 10M (win) → Balance: 100M, Required: **30M** (recalculated again!), Gambled: 20M, Remaining: 10M

The requirement kept changing, making it nearly impossible to reach 0.

## Solution
Removed the recalculation of `required_gamble` in the coinflip command. The requirement now only changes when:
1. **On Deposit**: Set to `balance * 30%`
2. **On Withdrawal**: Reset to `new_balance * 30%`

### Fixed Code
**Before (line 466):**
```python
required_gamble = int(balance * GAMBLE_PERCENT)  # ❌ Recalculating on every bet
c.execute(
    "UPDATE users SET balance=?, gambled=?, total_gambled=?, required_gamble=? WHERE user_id=?",
    (balance, gambled, total_gambled, required_gamble, ctx.author.id)
)
```

**After:**
```python
# Do NOT recalculate required_gamble - it stays the same until withdrawal
c.execute(
    "UPDATE users SET balance=?, gambled=?, total_gambled=? WHERE user_id=?",
    (balance, gambled, total_gambled, ctx.author.id)
)
```

## How It Works Now

### 1. Deposit Flow
When a user deposits money (via `update_balance`):
- `balance` increases by deposit amount
- `required_gamble = balance * 30%` (set once)
- `gambled` remains at current value (usually 0 after withdrawal)

### 2. Gambling Flow
Each time a user gambles (win or loss):
- `balance` increases (win) or decreases (loss) by bet amount
- `gambled` increases by bet amount (tracks progress toward requirement)
- `required_gamble` **stays the same** (not recalculated)
- `remaining = required_gamble - gambled` (decreases with each bet)

### 3. Withdrawal Flow
When a user withdraws (via `withdraw_balance`):
- Check: `gambled >= required_gamble` (must have gambled enough)
- Withdraw the balance
- `gambled = 0` (reset counter)
- `required_gamble = new_balance * 30%` (set new requirement for remaining balance)

## Example Scenario

**Initial State:**
- User deposits 100M

**After deposit:**
- Balance: 100,000,000
- Required Gamble: 30,000,000
- Gambled: 0
- Remaining: 30,000,000

**After betting 10M (loss):**
- Balance: 90,000,000 (decreased)
- Required Gamble: 30,000,000 (unchanged ✓)
- Gambled: 10,000,000 (increased)
- Remaining: 20,000,000 (decreased)

**After betting 15M (win):**
- Balance: 105,000,000 (increased)
- Required Gamble: 30,000,000 (unchanged ✓)
- Gambled: 25,000,000 (increased)
- Remaining: 5,000,000 (decreased)

**After betting 5M (loss):**
- Balance: 100,000,000 (decreased)
- Required Gamble: 30,000,000 (unchanged ✓)
- Gambled: 30,000,000 (increased)
- Remaining: 0 (can now withdraw! ✓)

**After withdrawal:**
- Balance: 0
- Required Gamble: 0
- Gambled: 0
- Total Withdrawn: 100,000,000

## Benefits
✅ Predictable requirement - users know exactly how much they need to gamble
✅ Fair system - requirement doesn't change based on wins/losses
✅ Achievable goal - users can actually reach 0 remaining
✅ Proper cycle - new requirement set after withdrawal based on remaining balance
