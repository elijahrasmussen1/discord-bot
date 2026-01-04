# Stats and Favorite Commands Documentation

## Overview

Two new commands have been added to the gambling bot to enhance user profiles and personalization.

---

## Commands

### 1. !stats [@user]

**Description:** Display a gambling profile for yourself or another user.

**Usage:**
- `!stats` - View your own gambling profile
- `!stats @username` - View another user's gambling profile

**Features:**
- Shows username and mention
- Displays user ID
- Shows current balance
- Shows all-time gambled amount
- Shows favorite game (set by user)
- Displays user's profile picture in the embed
- Timestamp in footer

**Example Output:**

```
┌─────────────────────────────────────┐
│ • Gambling Profile •                │ [User Avatar]
├─────────────────────────────────────┤
│ Username                            │
│ @johndoe (johndoe)                  │
│                                     │
│ User ID                             │
│ 123456789012345678                  │
│                                     │
│ Balance                             │
│ 5,000,000$                          │
│                                     │
│ Gambled                             │
│ 10,000,000$ (all time)              │
│                                     │
│ Favorite Game                       │
│ Blackjack                           │
└─────────────────────────────────────┘
Eli's MM Service• Today at 3:45 PM
```

---

### 2. !favorite <game>

**Description:** Set your favorite game to be displayed in your gambling profile.

**Usage:**
- `!favorite <game name>` - Set your favorite game

**Examples:**
- `!favorite Blackjack`
- `!favorite Texas Hold'em Poker`
- `!favorite Slots`
- `!favorite sjfjse` (any text is allowed)

**Features:**
- Accepts any text input (up to 100 characters)
- Supports special characters
- Case-sensitive (preserves your exact input)
- No restrictions on game name format

**Response:**
```
✅ Your favorite game has been set to: Blackjack
```

---

## Database Changes

### New Column

A new column `favorite_game` has been added to the `users` table:

```sql
ALTER TABLE users ADD COLUMN favorite_game TEXT DEFAULT 'Not Set'
```

**Default Value:** "Not Set" (when user hasn't set a favorite game yet)

**Migration:** Automatic - column is added if it doesn't exist when bot starts

---

## Implementation Details

### Helper Functions

Two new helper functions have been added:

1. **get_favorite_game(user_id)**
   - Retrieves user's favorite game from database
   - Returns "Not Set" if no game is set or user doesn't exist

2. **set_favorite_game(user_id, game_name)**
   - Sets user's favorite game in database
   - Creates user entry if it doesn't exist
   - Commits changes to database

### Validation

- **Game Name Length:** Maximum 100 characters
- **Characters:** All characters allowed (alphanumeric, spaces, special characters)
- **User ID:** Must be valid Discord user ID

---

## Usage in !assist Command

The new commands are now listed in the help menu:

```
👤 General Commands
**!amount** - View your balance and remaining required gamble
**!stats [@user]** - View gambling profile (yours or another user's)
**!favorite <game>** - Set your favorite game
**!donate @user [amount]** - Donate balance to another player
...
```

---

## Examples

### Setting Favorite Game

```
User: !favorite Blackjack
Bot: ✅ Your favorite game has been set to: Blackjack

User: !favorite Texas Hold'em Poker
Bot: ✅ Your favorite game has been set to: Texas Hold'em Poker

User: !favorite sjfjse!@#
Bot: ✅ Your favorite game has been set to: sjfjse!@#
```

### Viewing Stats

```
User: !stats
Bot: [Displays embed with user's gambling profile]

User: !stats @johndoe
Bot: [Displays embed with @johndoe's gambling profile]
```

### Error Cases

```
User: !favorite
Bot: ❌ Usage: `!favorite <game name>`
     Example: `!favorite Blackjack`

User: !favorite [101+ characters]
Bot: ❌ Game name must be 100 characters or less!
```

---

## Testing

Comprehensive tests have been created in `test_stats_commands.py`:

✅ Database migration
✅ Column creation
✅ Get/Set functions
✅ Special characters support
✅ Stats data retrieval
✅ Length validation

All tests passing!

---

## Compatibility

- **Database:** Fully compatible with existing bot.db
- **Migration:** Automatic on bot startup
- **No Breaking Changes:** Existing commands unaffected
- **Backwards Compatible:** Works with existing user data

---

## Future Enhancements

Possible future additions:
- Stats for specific time periods (daily, weekly, monthly)
- Win/loss ratios per game
- Leaderboard integration with favorite games
- Game-specific statistics
- Achievement badges based on stats

---

**Last Updated:** January 4, 2026  
**Version:** 1.1.0  
**Commands Added:** !stats, !favorite
