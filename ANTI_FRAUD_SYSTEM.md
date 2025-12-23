# Anti-Fraud System Documentation

## Overview

The Discord bot includes a comprehensive anti-fraud system to detect and prevent exploitation, abuse, and suspicious activities. This system monitors all gambling and financial transactions in real-time.

## Features

### 1. Gambling Requirement Enforcement

**Purpose**: Prevent users from depositing and withdrawing without gambling.

**How it works**:
- Users must gamble at least 30% of their balance before withdrawal
- `required_gamble` is set to `balance * 30%` on deposit
- Each bet increments the `gambled` counter
- Withdrawal only allowed when `gambled >= required_gamble`
- Clear error messages when requirement not met

**Example**:
```
User deposits 100M
Required to gamble: 30M
Gambled so far: 0M

After betting 20M:
Required: 30M (unchanged)
Gambled: 20M
Remaining: 10M (must gamble 10M more)

After betting another 15M:
Required: 30M
Gambled: 35M
Remaining: 0M ✅ Can withdraw
```

### 2. Transaction Audit Logging

**Purpose**: Create permanent record of all financial activities for investigation.

**Database Table**: `transaction_logs`

**Fields**:
- `id` - Auto-incrementing primary key
- `user_id` - Discord user ID
- `transaction_type` - Type of transaction (deposit, withdrawal, coinflip, slots)
- `amount` - Transaction amount
- `balance_before` - User balance before transaction
- `balance_after` - User balance after transaction
- `timestamp` - ISO format timestamp
- `details` - Additional information (e.g., win/loss)

**What gets logged**:
- ✅ Deposits via `!amount`
- ✅ Coinflip bets and results
- ✅ Slots spins and results
- ✅ Withdrawal requests
- ✅ Withdrawal approvals/denials
- ✅ Balance modifications

**Query examples**:
```sql
-- Get user's transaction history
SELECT * FROM transaction_logs WHERE user_id = ? ORDER BY timestamp DESC;

-- Find large transactions
SELECT * FROM transaction_logs WHERE amount >= 50000000;

-- Audit withdrawals
SELECT * FROM transaction_logs WHERE transaction_type = 'withdrawal';
```

### 3. Rapid Betting Detection

**Purpose**: Detect bot usage or exploit attempts through abnormally fast betting.

**Threshold**: 5 or more bets within 60 seconds

**How it works**:
1. Every bet is logged to `bet_activity` table with timestamp
2. Before processing bet, system checks recent activity
3. If 5+ bets found in last 60 seconds, alert is triggered
4. Alert sent to audit log channel
5. Bet still processes (detection only, not prevention)

**Database Table**: `bet_activity`

**Fields**:
- `id` - Auto-incrementing primary key
- `user_id` - Discord user ID
- `bet_amount` - Amount wagered
- `game_type` - coinflip or slots
- `result` - win or loss
- `timestamp` - ISO format timestamp

**Alert Example**:
```
🚨 Suspicious Activity Detected
User: @username (123456789)
Alert Type: Rapid Betting Detected

Details: User placed 7 bets in the last 60 seconds
```

### 4. High-Value Transaction Monitoring

**Purpose**: Flag large withdrawals and bets for owner review.

**Thresholds**:
- Withdrawals ≥ 100,000,000 (100M) - Automatically flagged
- Bets ≥ 50,000,000 (50M) - Logged to database

**Alert Types**:

**High Withdrawal Alert**:
```
🚨 Suspicious Activity Detected
User: @username (123456789)
Alert Type: High Withdrawal Request

Details: Withdrawal amount: 150,000,000$ (150M)
```

**Large Bet Logging**:
- Automatically logged to `bet_activity` table
- No alert sent (logged for later analysis)
- Can be queried for pattern detection

### 5. Audit Log Channel

**Channel ID**: `1451387246061293662`

**What appears here**:
- 🚨 Rapid betting alerts
- 🚨 High withdrawal requests
- 📊 Important system events
- ⚠️ Error notifications

**Alert Format**:
- Red embed for immediate attention
- User mention and ID
- Alert type clearly labeled
- Detailed description of event
- Timestamp for timeline tracking
- "Anti-Fraud System" footer

## Configuration

**In `bot.py`**:

```python
# Channel IDs
AUDIT_LOG_CHANNEL = 1451387246061293662  # Fraud alerts and activity logs

# Anti-fraud thresholds
SUSPICIOUS_WITHDRAWAL_THRESHOLD = 100_000_000  # 100M+ withdrawals flagged
RAPID_BET_THRESHOLD = 5  # 5+ bets in 60 seconds is suspicious
HIGH_BET_THRESHOLD = 50_000_000  # 50M+ bets are logged
GAMBLE_PERCENT = 0.30  # 30% gambling requirement
```

## Functions

### `log_transaction(user_id, transaction_type, amount, balance_before, balance_after, details="")`

Logs a transaction to the audit database.

**Parameters**:
- `user_id` - Discord user ID
- `transaction_type` - "deposit", "withdrawal", "coinflip", "slots", etc.
- `amount` - Transaction amount (integer)
- `balance_before` - Balance before transaction
- `balance_after` - Balance after transaction
- `details` - Optional additional information

**Returns**: None

**Example**:
```python
await log_transaction(
    ctx.author.id,
    "coinflip",
    bet_amount,
    old_balance,
    new_balance,
    "win" if won else "loss"
)
```

### `log_bet_activity(user_id, bet_amount, game_type, result)`

Tracks betting activity for fraud detection.

**Parameters**:
- `user_id` - Discord user ID
- `bet_amount` - Amount wagered
- `game_type` - "coinflip" or "slots"
- `result` - "win" or "loss"

**Returns**: None

### `check_rapid_betting(user_id)`

Checks if user is betting too rapidly.

**Parameters**:
- `user_id` - Discord user ID

**Returns**: Boolean - True if rapid betting detected

**Example**:
```python
is_rapid = await check_rapid_betting(ctx.author.id)
if is_rapid:
    await send_fraud_alert(bot, ctx.author, "Rapid Betting Detected", ...)
```

### `send_fraud_alert(bot, user, alert_type, details)`

Sends fraud alert to audit log channel.

**Parameters**:
- `bot` - Bot instance
- `user` - Discord user object
- `alert_type` - Type of alert (e.g., "Rapid Betting Detected")
- `details` - Description of suspicious activity

**Returns**: None

### `log_user_activity(bot, user, activity_type, details)`

Logs important user activities to audit channel.

**Parameters**:
- `bot` - Bot instance
- `user` - Discord user object
- `activity_type` - Type of activity
- `details` - Activity description

**Returns**: None

## Integration Examples

### Coinflip Command
```python
# Log bet activity
await log_bet_activity(ctx.author.id, amount, "coinflip", "win" if won else "loss")

# Check for rapid betting
is_rapid = await check_rapid_betting(ctx.author.id)
if is_rapid:
    await send_fraud_alert(bot, ctx.author, "Rapid Betting Detected", 
                          f"User placed multiple coinflip bets in rapid succession")

# Log transaction
await log_transaction(ctx.author.id, "coinflip", amount, old_balance, new_balance, 
                     "win" if won else "loss")
```

### Withdrawal Command
```python
# Check high withdrawal threshold
if balance >= SUSPICIOUS_WITHDRAWAL_THRESHOLD:
    await send_fraud_alert(bot, ctx.author, "High Withdrawal Request",
                          f"Withdrawal amount: {balance:,}$ ({balance/1_000_000}M)")

# Log transaction on approval
await log_transaction(user_id, "withdrawal", amount, balance, 0, 
                     f"Approved by {interaction.user.name}")
```

### Slots Command
```python
# Log bet activity
await log_bet_activity(ctx.author.id, bet_amount, "slots", "win" if won else "loss")

# Check rapid betting
is_rapid = await check_rapid_betting(ctx.author.id)
if is_rapid:
    await send_fraud_alert(bot, ctx.author, "Rapid Betting Detected",
                          f"User placed {bet_count} slot bets in 60 seconds")

# Log transaction
await log_transaction(ctx.author.id, "slots", bet_amount, old_balance, new_balance,
                     f"multiplier: {multiplier}" if won else "loss")
```

## Limitations

### IP Banning

**Not Possible**: Discord's API does not expose user IP addresses to bots for privacy and security reasons.

**Alternatives**:
1. **Discord Native Banning**: Use Discord's built-in ban system
2. **Third-Party Bots**: Use MEE6, Carl-bot, or similar for advanced moderation
3. **Account Linking**: Some bots can detect alt accounts through behavioral patterns
4. **Manual Review**: Monitor audit logs for suspicious patterns

### What CAN be detected:
- ✅ Rapid command usage
- ✅ Large transactions
- ✅ Unusual betting patterns
- ✅ Multiple accounts from same user (manual review of patterns)

### What CANNOT be detected:
- ❌ IP addresses
- ❌ Device fingerprints
- ❌ Physical location
- ❌ Automated alt account detection (requires external tools)

## Monitoring Best Practices

1. **Regular Audit Log Review**
   - Check audit channel daily for alerts
   - Investigate flagged users
   - Look for patterns in transaction logs

2. **Database Queries**
   - Run weekly reports on high-value transactions
   - Check for users with unusual bet patterns
   - Monitor withdrawal-to-deposit ratios

3. **Threshold Adjustment**
   - Adjust thresholds based on server economy
   - Lower thresholds for tighter control
   - Raise thresholds to reduce false positives

4. **Response Protocol**
   - Investigate all fraud alerts within 24 hours
   - Document findings in external system
   - Ban or warn users based on severity
   - Adjust thresholds if needed

## Database Maintenance

### Clean Old Records

**Bet Activity** (optional - for performance):
```sql
-- Delete bet records older than 30 days
DELETE FROM bet_activity WHERE timestamp < datetime('now', '-30 days');
```

**Transaction Logs** (keep forever for audit):
```sql
-- Never delete transaction logs
-- They are the permanent audit trail
```

### Query Examples

**Find rapid betters**:
```sql
SELECT user_id, COUNT(*) as bet_count
FROM bet_activity
WHERE timestamp > datetime('now', '-1 hour')
GROUP BY user_id
HAVING bet_count >= 10
ORDER BY bet_count DESC;
```

**Find high rollers**:
```sql
SELECT user_id, SUM(amount) as total_bet
FROM transaction_logs
WHERE transaction_type IN ('coinflip', 'slots')
  AND timestamp > datetime('now', '-7 days')
GROUP BY user_id
ORDER BY total_bet DESC
LIMIT 10;
```

**Withdrawal analysis**:
```sql
SELECT 
    user_id,
    COUNT(*) as withdrawal_count,
    SUM(amount) as total_withdrawn
FROM transaction_logs
WHERE transaction_type = 'withdrawal'
GROUP BY user_id
ORDER BY total_withdrawn DESC;
```

## Summary

The anti-fraud system provides:
- ✅ Gambling requirement enforcement (prevents deposit-withdraw abuse)
- ✅ Complete transaction audit trail
- ✅ Real-time fraud detection
- ✅ Automated owner alerts
- ✅ Database for pattern analysis
- ✅ Configurable thresholds
- ✅ Production-ready implementation

This system significantly reduces fraud risk and provides tools for investigating suspicious behavior.
