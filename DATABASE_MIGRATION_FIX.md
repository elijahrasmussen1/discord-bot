# Database Migration Fix

## Problem
Users reported error: `❌ Error during [commands]: not enough values to unpack (expected 6, got 4)`

## Root Cause
The bot's database schema evolved to include 6 columns:
1. user_id (PRIMARY KEY)
2. balance
3. required_gamble
4. gambled
5. total_gambled
6. total_withdrawn

However, older deployments may have databases with only 4 columns (missing `total_gambled` and `total_withdrawn`). The `CREATE TABLE IF NOT EXISTS` statement doesn't modify existing tables, so old databases remained incompatible.

## Solution
Added automatic database migration on bot startup:

```python
# Database migration: Add missing columns if they don't exist
try:
    # Check if total_gambled and total_withdrawn columns exist
    c.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in c.fetchall()]
    
    if 'total_gambled' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN total_gambled INTEGER DEFAULT 0")
        print("✅ Added total_gambled column to users table")
    
    if 'total_withdrawn' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN total_withdrawn INTEGER DEFAULT 0")
        print("✅ Added total_withdrawn column to users table")
    
    conn.commit()
except Exception as e:
    print(f"⚠️ Database migration error (non-fatal): {e}")
```

## How It Works
1. On startup, the bot checks the existing schema using `PRAGMA table_info(users)`
2. If `total_gambled` or `total_withdrawn` columns are missing, they're added with `ALTER TABLE`
3. Default value of 0 is applied to all existing rows
4. Migration is non-fatal - if it fails, the bot continues (to avoid breaking new deployments)

## Result
✅ Old databases are automatically upgraded
✅ New deployments work as before
✅ All commands now work correctly
✅ No data loss
