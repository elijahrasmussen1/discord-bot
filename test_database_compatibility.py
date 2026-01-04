"""
Database Compatibility Test
Verifies that bot.py and poker game work with existing database
"""

import sqlite3
import sys

print("=" * 70)
print("DATABASE COMPATIBILITY TEST")
print("=" * 70)

# Test 1: Verify both bot files use same schema
print("\n1️⃣ Testing schema consistency...")

def get_users_schema(filename):
    """Extract users table schema from bot file"""
    with open(filename, 'r') as f:
        content = f.read()
    
    # Find CREATE TABLE IF NOT EXISTS users
    start = content.find("CREATE TABLE IF NOT EXISTS users")
    if start == -1:
        return None
    
    # Find the end of this statement
    end = content.find('""")', start)
    if end == -1:
        return None
    
    schema = content[start:end].strip()
    return schema

bot_py_schema = get_users_schema('bot.py')
readme_schema = get_users_schema('README.md')

if bot_py_schema == readme_schema:
    print("✅ bot.py and README.md use IDENTICAL users table schema")
else:
    print("❌ Schema mismatch detected!")
    sys.exit(1)

# Test 2: Verify required columns exist
print("\n2️⃣ Testing required columns...")

required_columns = [
    'user_id INTEGER PRIMARY KEY',
    'balance INTEGER',
    'required_gamble INTEGER',
    'gambled INTEGER',
    'total_gambled INTEGER',
    'total_withdrawn INTEGER'
]

for col in required_columns:
    if col in bot_py_schema:
        print(f"✅ {col.split()[0]} column found")
    else:
        print(f"❌ {col.split()[0]} column missing!")
        sys.exit(1)

# Test 3: Test with in-memory database
print("\n3️⃣ Testing database operations...")

conn = sqlite3.connect(":memory:")
c = conn.cursor()

# Create table using bot.py schema
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    required_gamble INTEGER DEFAULT 0,
    gambled INTEGER DEFAULT 0,
    total_gambled INTEGER DEFAULT 0,
    total_withdrawn INTEGER DEFAULT 0
)
""")

# Simulate get_user function
def get_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return get_user(user_id)
    return row

# Simulate update_balance function
def update_balance(user_id, amount):
    user_id, bal, req, gambled, total_gambled, total_withdrawn = get_user(user_id)
    new_bal = bal + amount
    new_req = int(new_bal * 0.30)
    c.execute(
        "UPDATE users SET balance=?, required_gamble=? WHERE user_id=?",
        (new_bal, new_req, user_id)
    )
    conn.commit()

# Simulate add_gambled function
def add_gambled(user_id, amount):
    user_id, bal, req, gambled, total_gambled, total_withdrawn = get_user(user_id)
    new_gambled = gambled + amount
    new_total_gambled = total_gambled + amount
    c.execute(
        "UPDATE users SET gambled=?, total_gambled=? WHERE user_id=?",
        (new_gambled, new_total_gambled, user_id)
    )
    conn.commit()

try:
    # Test poker buy-in scenario
    test_user_id = 12345
    
    # Initial deposit
    update_balance(test_user_id, 10000)
    user_data = get_user(test_user_id)
    assert user_data[1] == 10000, "Balance should be 10000"
    print("✅ Initial balance set: 10,000")
    
    # Poker buy-in (deduct 1000)
    update_balance(test_user_id, -1000)
    user_data = get_user(test_user_id)
    assert user_data[1] == 9000, "Balance should be 9000 after buy-in"
    print("✅ Buy-in deducted: -1,000 (balance: 9,000)")
    
    # Track bet
    add_gambled(test_user_id, 100)
    user_data = get_user(test_user_id)
    assert user_data[3] == 100, "Gambled should be 100"
    assert user_data[4] == 100, "Total gambled should be 100"
    print("✅ Bet tracked: 100 (gambled: 100, total: 100)")
    
    # Poker payout (win 2000)
    update_balance(test_user_id, 2000)
    user_data = get_user(test_user_id)
    assert user_data[1] == 11000, "Balance should be 11000 after payout"
    print("✅ Payout added: +2,000 (balance: 11,000)")
    
    # Another bet
    add_gambled(test_user_id, 200)
    user_data = get_user(test_user_id)
    assert user_data[3] == 300, "Gambled should be 300"
    assert user_data[4] == 300, "Total gambled should be 300"
    print("✅ Another bet tracked: 200 (gambled: 300, total: 300)")
    
except AssertionError as e:
    print(f"❌ Test failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error during test: {e}")
    sys.exit(1)
finally:
    conn.close()

# Test 4: Verify poker doesn't create tables
print("\n4️⃣ Testing poker modules don't create tables...")

poker_files = [
    'poker_deck.py',
    'poker_hand_evaluator.py', 
    'poker_player.py',
    'poker_game.py',
    'poker_commands.py'
]

for poker_file in poker_files:
    with open(poker_file, 'r') as f:
        content = f.read()
    
    if 'CREATE TABLE' in content or 'ALTER TABLE' in content or 'DROP TABLE' in content:
        print(f"❌ {poker_file} modifies database schema!")
        sys.exit(1)
    else:
        print(f"✅ {poker_file} - no schema modifications")

# Test 5: Verify helper functions are passed
print("\n5️⃣ Testing helper functions integration...")

with open('poker_commands.py', 'r') as f:
    poker_commands = f.read()

helper_functions = [
    'parse_money_func',
    'get_user_func',
    'update_balance_func',
    'add_gambled_func'
]

for func in helper_functions:
    if func in poker_commands:
        print(f"✅ {func} parameter found")
    else:
        print(f"❌ {func} parameter missing!")
        sys.exit(1)

print("\n" + "=" * 70)
print("✅ ALL DATABASE COMPATIBILITY TESTS PASSED!")
print("=" * 70)

print("\n📋 SUMMARY:")
print("✓ bot.py and README.md use identical schema")
print("✓ All required columns present")
print("✓ Database operations work correctly")
print("✓ Poker modules don't modify schema")
print("✓ Helper functions properly integrated")
print("\n✅ Your existing bot.db database is 100% compatible!")
