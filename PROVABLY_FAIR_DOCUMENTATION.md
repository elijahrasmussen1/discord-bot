# Provably Fair Gambling System Documentation

## Overview

The gambling bot now implements a **Provably Fair System** using cryptographic proof to ensure that all gambling outcomes are fair, transparent, and verifiable. This system eliminates any possibility of manipulation by administrators or the bot itself.

---

## How It Works

### Core Components

The system uses three values to determine every bet outcome:

1. **Server Seed** (Secret)
   - A 64-character random hexadecimal string
   - Kept secret until the seed is rotated
   - Cannot be changed mid-session

2. **Client Seed** (Public)
   - A 32-character random hexadecimal string (default)
   - Unique to each user
   - Can be customized by the user at any time

3. **Nonce** (Counter)
   - Starts at 0 for each user
   - Increments by 1 after each bet
   - Ensures each bet has a unique result

### Algorithm

Every bet result is generated using **HMAC-SHA256**:

```
1. Create message: "{client_seed}:{nonce}"
2. Generate HMAC-SHA256(server_seed, message)
3. Take first 8 hexadecimal characters
4. Convert to integer
5. Apply modulo based on game type
```

**Example for Coinflip:**
- Modulo 2: Result is 0 or 1
- 0 = Heads
- 1 = Tails

### Transparency

**Before any bets:**
- The SHA256 hash of the server seed is published
- Players can see this hash but not the actual seed
- This prevents the server from changing the seed after seeing bet choices

**After seed rotation:**
- The old server seed is revealed
- Players can verify all past bets using the revealed seed
- A new server seed is generated and its hash is published

---

## Commands

### User Commands

#### `!fairinfo`
Displays comprehensive information about the provably fair system.

**Shows:**
- How the system works
- Current server seed hash
- System statistics
- Available commands

#### `!myseeds`
View your current client seed and nonce.

**Shows:**
- Your client seed (32 hex characters)
- Your current nonce
- Current server seed hash

#### `!setseed <hex_string>`
Set your own custom client seed.

**Requirements:**
- Must be a valid hexadecimal string
- Example: `!setseed deadbeefcafe1234567890abcdef0123`

**Benefits:**
- Increases randomness
- Allows you to use a seed you trust
- Can be changed at any time

#### `!verify [bet_number]`
Verify your recent bets for fairness.

**Usage:**
- `!verify` - Verifies your most recent bet
- `!verify 3` - Verifies your 3rd most recent bet

**Shows:**
- Bet details (amount, result, nonce)
- Seeds used (client seed, server hash)
- Verification status (if server seed is revealed)

#### `!revealedseed`
View all revealed server seeds.

**Shows:**
- Up to 5 most recent revealed seeds
- When each seed was revealed
- Complete seed and hash for verification

### Owner Commands

#### `!rotateseed`
Rotate the server seed (owner only).

**What happens:**
1. Current server seed is revealed
2. New server seed is generated
3. New seed hash is published
4. All users can now verify past bets

**When to use:**
- Periodically (e.g., weekly/monthly)
- After major gambling events
- On player request for transparency

---

## Security Features

### Cannot Be Manipulated

✅ **Server cannot predict outcomes**
- Server seed is generated using cryptographically secure RNG
- HMAC-SHA256 ensures deterministic but unpredictable results

✅ **Server cannot change outcomes**
- Server seed hash is published before any bets
- Changing the seed would change the hash
- Players can verify the hash matches after revelation

✅ **Admins cannot influence results**
- Results are mathematically determined
- No manual intervention possible
- All outcomes are logged and verifiable

✅ **Players cannot predict outcomes**
- Server seed is kept secret until rotation
- Even knowing client seed and nonce doesn't reveal result
- HMAC-SHA256 is cryptographically secure

### Transparency

✅ **Every bet is logged**
- Server seed hash
- Client seed
- Nonce
- Result
- Timestamp

✅ **All bets are verifiable**
- Use `!verify` to check any bet
- Compare with revealed server seeds
- Mathematically prove fairness

✅ **Seed rotations are logged**
- Audit trail in admin channel
- Old seeds are archived
- Full transparency

---

## Examples

### Example 1: First Bet

**User places coinflip bet:**
```
!cf 100k heads
```

**System processes:**
1. Gets active server seed (e.g., `abc123...`)
2. Gets user's client seed (e.g., `def456...`)
3. Gets user's nonce (e.g., `0`)
4. Generates result:
   - Message: `def456...:0`
   - HMAC-SHA256(abc123..., def456...:0) = `7f3a9b2c...`
   - First 8 chars: `7f3a9b2c`
   - Convert to int: `2135456556`
   - Modulo 2: `0` (Heads)
5. User wins!
6. Nonce increments to `1`

**Result displayed with provably fair info:**
```
🎉 Coinflip Won!
You won! The coin landed on HEADS!

🔐 Provably Fair
Client Seed: def456...
Nonce: 0
Server Hash: sha256(abc123...)...
```

### Example 2: Verification

**After seed rotation, user verifies bet:**
```
!verify 1
```

**System shows:**
```
🔍 Bet Verification #12345
Game: Coinflip
Timestamp: 2026-01-04 12:30:45 UTC

Bet Details:
Amount: 100,000$
Result: 0 (Heads)
Nonce: 0

Seeds Used:
Client Seed: def456...
Server Hash: sha256(abc123...)...

✅ Server Seed Revealed:
abc123...

Verification Result:
✅ VERIFIED - Result is correct!
```

### Example 3: Custom Client Seed

**User sets custom seed:**
```
!setseed feedbeefdeadcafe1234567890abcdef
```

**Response:**
```
✅ Your client seed has been updated!
💡 Your nonce has been preserved.
```

**Next bet uses new seed:**
- Result will be different from default seed
- User has control over their randomness source

---

## Technical Details

### HMAC-SHA256 Algorithm

```python
import hmac
import hashlib

def generate_result(server_seed, client_seed, nonce, modulo):
    # Create message
    message = f"{client_seed}:{nonce}"
    
    # Generate HMAC
    hmac_hash = hmac.new(
        server_seed.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Take first 8 hex characters
    hex_slice = hmac_hash[:8]
    
    # Convert to integer
    result_int = int(hex_slice, 16)
    
    # Apply modulo
    result = result_int % modulo
    
    return result
```

### Database Schema

**provably_fair_seeds**
- Stores active and historical server seeds
- Tracks when seeds are created and revealed

**provably_fair_users**
- Stores per-user client seeds and nonces
- Tracks last update time

**provably_fair_bets**
- Logs every bet for verification
- Includes all parameters needed for verification

### Security Standards

- **RNG**: Python's `secrets` module (CSPRNG)
- **Hashing**: SHA-256 (256-bit)
- **MAC**: HMAC-SHA256
- **Seed Length**: 256 bits (64 hex characters)

---

## Best Practices

### For Users

1. **Change your client seed periodically**
   - Use `!setseed` with your own random hex string
   - Increases security and randomness

2. **Verify your bets regularly**
   - Use `!verify` to check fairness
   - Especially for large bets

3. **Note the server seed hash**
   - Check `!fairinfo` before betting sessions
   - Verify it matches after seed rotation

### For Admins

1. **Rotate seeds regularly**
   - Use `!rotateseed` weekly or monthly
   - Announce rotations to players

2. **Never rotate mid-session**
   - Wait for natural breaks
   - Log all rotations

3. **Monitor the system**
   - Check system stats with `!fairinfo`
   - Ensure database backups include provably fair tables

---

## Comparison to Industry Standards

Our system matches or exceeds standards used by major gambling sites:

| Feature | Our System | Industry Standard |
|---------|-----------|------------------|
| RNG | CSPRNG (secrets module) | ✅ CSPRNG |
| Hash Algorithm | SHA-256 | ✅ SHA-256 |
| MAC | HMAC-SHA256 | ✅ HMAC-SHA256 |
| Seed Publication | Hash published before bets | ✅ Required |
| Verification | All bets verifiable | ✅ Required |
| Client Seed | User-customizable | ✅ Recommended |
| Seed Rotation | Manual with revelation | ✅ Standard |

---

## FAQ

**Q: Can the bot manipulate results?**
A: No. Results are mathematically determined using cryptographic functions. The server seed hash is published before any bets, making it impossible to change outcomes.

**Q: How do I know the server seed is really random?**
A: The seed is generated using Python's `secrets` module, which is cryptographically secure. After rotation, you can verify the seed matches the published hash.

**Q: What if I lose many bets in a row?**
A: This is normal variance in gambling. You can verify each bet with `!verify` to confirm fairness. The system cannot be rigged.

**Q: Should I change my client seed?**
A: It's optional but recommended. Changing your seed adds an extra layer of randomness and control.

**Q: How often are server seeds rotated?**
A: Server seeds are rotated by admins periodically (typically weekly or monthly). Check `!fairinfo` for the current seed hash.

**Q: What happens to old bets when seed is rotated?**
A: Old bets remain verifiable! The old server seed is revealed, allowing you to verify all bets made with that seed.

---

## Support

For questions or issues:
- Use `!fairinfo` for basic information
- Contact server admins for technical support
- Report any discrepancies immediately

---

**Last Updated:** January 4, 2026  
**Version:** 1.0.0  
**System:** Provably Fair HMAC-SHA256
