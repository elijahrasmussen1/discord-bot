# Stats Command Visual Example

## !stats Command Output

When a user runs `!stats` or `!stats @user`, they will see an embed like this:

```
┌──────────────────────────────────────────────────┐
│ • Gambling Profile •                    [Avatar] │
│                                                   │
│ Username                                          │
│ @username (username)                              │
│                                                   │
│ User ID                                           │
│ 123456789012345678                                │
│                                                   │
│ Balance                                           │
│ 5,000,000$                                        │
│                                                   │
│ Gambled                                           │
│ 10,000,000$ (all time)                            │
│                                                   │
│ Favorite Game                                     │
│ Blackjack                                         │
│                                                   │
└──────────────────────────────────────────────────┘
Eli's MM Service• Today at 3:45 PM
```

**Features:**
- 🔷 Blue embed color
- 👤 User's profile picture in top-right corner
- 📝 Clean, organized field layout
- ⏰ Dynamic timestamp in footer
- 💬 Username with mention + plain username

---

## !favorite Command

**Input:**
```
!favorite Blackjack
```

**Output:**
```
✅ Your favorite game has been set to: Blackjack
```

Then when you run `!stats`, your favorite game will show as "Blackjack" in the embed.

---

## Examples

### Setting Different Favorite Games

```
!favorite Texas Hold'em Poker
✅ Your favorite game has been set to: Texas Hold'em Poker

!favorite Slots
✅ Your favorite game has been set to: Slots

!favorite sjfjse
✅ Your favorite game has been set to: sjfjse
```

### Viewing Different Users' Stats

```
!stats
[Shows your own gambling profile]

!stats @johndoe
[Shows @johndoe's gambling profile]
```

---

## Technical Details

**Embed Configuration:**
- Title: "• Gambling Profile •"
- Color: Blue (discord.Color.blue())
- Thumbnail: User's avatar (display_avatar.url)
- Footer: "Eli's MM Service• Today at [HH:MM AM/PM]"
- Fields: Username, User ID, Balance, Gambled (all time), Favorite Game

**Database:**
- New column: `favorite_game TEXT DEFAULT 'Not Set'`
- Automatic migration on bot startup
- No manual database changes required

**Validation:**
- Maximum game name length: 100 characters
- Supports all characters (alphanumeric, spaces, special)
- Case-sensitive (preserves exact input)
