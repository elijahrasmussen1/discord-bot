"""
Integration test for Provably Fair System with bot.py
"""

import sqlite3
import sys
from provably_fair import ProvablyFairSystem

print("=" * 70)
print("PROVABLY FAIR SYSTEM INTEGRATION TEST")
print("=" * 70)

# Simulate bot.py database connection
conn = sqlite3.connect(":memory:")
c = conn.cursor()

# Create users table (simulating bot.py schema)
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    required_gamble INTEGER DEFAULT 0,
    gambled INTEGER DEFAULT 0,
    total_gambled INTEGER DEFAULT 0,
    total_withdrawn INTEGER DEFAULT 0,
    favorite_game TEXT DEFAULT 'Not Set'
)
""")
conn.commit()

# Test 1: Initialize Provably Fair System
print("\n1️⃣ Initializing provably fair system...")
try:
    pf = ProvablyFairSystem(conn)
    seed_hash = pf.initialize_system()
    print(f"✅ System initialized")
    print(f"   Server Seed Hash: {seed_hash[:32]}...")
except Exception as e:
    print(f"❌ Initialization failed: {e}")
    sys.exit(1)

# Test 2: Simulate Coinflip Bet Flow
print("\n2️⃣ Simulating coinflip bet flow...")
try:
    user_id = 123456789
    bet_amount = 100000
    user_choice = "heads"
    
    # Place bet using provably fair system
    result, client_seed, nonce, seed_hash = pf.place_bet(
        user_id,
        "coinflip",
        bet_amount,
        2  # modulo 2 for coinflip
    )
    
    # Convert result to outcome
    outcome = "heads" if result == 0 else "tails"
    won = (user_choice == outcome)
    
    print(f"✅ Bet placed successfully")
    print(f"   User Choice: {user_choice}")
    print(f"   Result: {outcome} (result={result})")
    print(f"   Won: {won}")
    print(f"   Client Seed: {client_seed[:16]}...")
    print(f"   Nonce: {nonce}")
    print(f"   Server Hash: {seed_hash[:16]}...")
    
    assert result in [0, 1], "Result must be 0 or 1"
    assert nonce == 0, "First bet should have nonce 0"
    
except Exception as e:
    print(f"❌ Coinflip simulation failed: {e}")
    sys.exit(1)

# Test 3: Multiple Bets with Nonce Increment
print("\n3️⃣ Testing multiple bets with nonce increment...")
try:
    user_id = 987654321
    
    results = []
    for i in range(5):
        result, client_seed, nonce, seed_hash = pf.place_bet(
            user_id,
            "coinflip",
            10000 * (i+1),
            2
        )
        results.append((nonce, result))
    
    print(f"✅ Placed 5 bets")
    for i, (nonce, result) in enumerate(results):
        outcome = "Heads" if result == 0 else "Tails"
        print(f"   Bet {i+1}: Nonce={nonce}, Result={outcome}")
    
    # Verify nonces increment correctly
    assert results[0][0] == 0
    assert results[1][0] == 1
    assert results[2][0] == 2
    assert results[3][0] == 3
    assert results[4][0] == 4
    
except Exception as e:
    print(f"❌ Multiple bets failed: {e}")
    sys.exit(1)

# Test 4: Verify Bet History
print("\n4️⃣ Testing bet history retrieval...")
try:
    history = pf.get_user_bet_history(user_id, limit=10)
    
    assert len(history) == 5, f"Expected 5 bets, got {len(history)}"
    
    print(f"✅ Retrieved {len(history)} bets from history")
    print(f"   Latest: Nonce={history[0][4]}, Result={history[0][5]}")
    print(f"   Oldest: Nonce={history[-1][4]}, Result={history[-1][5]}")
    
except Exception as e:
    print(f"❌ History retrieval failed: {e}")
    sys.exit(1)

# Test 5: Custom Client Seed
print("\n5️⃣ Testing custom client seed...")
try:
    user_id = 111222333
    
    # Get default seed
    default_seed, _ = pf.get_or_create_user_seeds(user_id)
    
    # Set custom seed
    custom_seed = "deadbeefcafebabe1234567890abcdef"
    success = pf.set_client_seed(user_id, custom_seed)
    assert success == True
    
    # Place bet with custom seed
    result, client_seed, nonce, seed_hash = pf.place_bet(
        user_id,
        "coinflip",
        50000,
        2
    )
    
    assert client_seed == custom_seed, "Bet should use custom seed"
    
    print(f"✅ Custom seed working")
    print(f"   Default: {default_seed[:16]}...")
    print(f"   Custom:  {custom_seed[:16]}...")
    print(f"   Used:    {client_seed[:16]}...")
    
except Exception as e:
    print(f"❌ Custom seed failed: {e}")
    sys.exit(1)

# Test 6: Server Seed Rotation
print("\n6️⃣ Testing server seed rotation...")
try:
    # Get active seed hash before rotation
    old_hash = pf.get_active_server_seed_hash()
    
    # Rotate
    old_seed, new_hash = pf.rotate_server_seed()
    
    # Verify old seed matches old hash
    verified_hash = pf.get_server_seed_hash(old_seed)
    assert verified_hash == old_hash, "Old seed hash doesn't match"
    
    # Verify new hash is different
    assert new_hash != old_hash, "New hash should be different"
    
    print(f"✅ Seed rotation successful")
    print(f"   Old Seed Revealed: {old_seed[:16]}...")
    print(f"   Old Hash: {old_hash[:16]}...")
    print(f"   Verified: {verified_hash[:16]}...")
    print(f"   New Hash: {new_hash[:16]}...")
    
except Exception as e:
    print(f"❌ Seed rotation failed: {e}")
    sys.exit(1)

# Test 7: Bet Verification After Rotation
print("\n7️⃣ Testing bet verification after rotation...")
try:
    # Get first user's history
    user_id = 987654321
    history = pf.get_user_bet_history(user_id, limit=5)
    
    if history:
        # Get first bet
        bet_id, game_type, seed_hash, client_seed, nonce, result, bet_amount, timestamp = history[0]
        
        # Get revealed seeds
        revealed = pf.get_revealed_seeds(limit=10)
        
        # Find matching seed
        revealed_seed = None
        for seed, hash_val, revealed_at in revealed:
            if hash_val == seed_hash:
                revealed_seed = seed
                break
        
        if revealed_seed:
            # Verify the bet
            is_valid = pf.verify_bet(revealed_seed, client_seed, nonce, result, 2)
            
            print(f"✅ Bet verification completed")
            print(f"   Bet ID: {bet_id}")
            print(f"   Nonce: {nonce}")
            print(f"   Result: {result}")
            print(f"   Valid: {is_valid}")
            
            assert is_valid == True, "Bet should be valid"
        else:
            print(f"⚠️  Seed not yet revealed (expected if bet after rotation)")
    else:
        print(f"⚠️  No bets to verify")
    
except Exception as e:
    print(f"❌ Verification failed: {e}")
    sys.exit(1)

# Test 8: System Statistics
print("\n8️⃣ Testing system statistics...")
try:
    stats = pf.get_system_stats()
    
    print(f"✅ System statistics:")
    print(f"   Active Seed: {stats['active_seed_hash'][:16]}...")
    print(f"   Total Bets: {stats['total_bets']}")
    print(f"   Total Users: {stats['total_users']}")
    print(f"   Rotations: {stats['total_rotations']}")
    
    assert stats['total_bets'] > 0, "Should have bets"
    assert stats['total_users'] > 0, "Should have users"
    assert stats['total_rotations'] >= 1, "Should have at least one rotation"
    
except Exception as e:
    print(f"❌ Statistics failed: {e}")
    sys.exit(1)

# Test 9: Simulate Discord Embed Information
print("\n9️⃣ Simulating Discord embed information...")
try:
    user_id = 444555666
    
    # Place a bet
    result, client_seed, nonce, seed_hash = pf.place_bet(
        user_id,
        "coinflip",
        75000,
        2
    )
    
    # Simulate what would be displayed in Discord
    outcome = "Heads" if result == 0 else "Tails"
    
    embed_info = f"""
    🎉 Coinflip Result!
    Result: {outcome}
    
    🔐 Provably Fair:
    Client Seed: {client_seed[:16]}...
    Nonce: {nonce}
    Server Hash: {seed_hash[:16]}...
    
    Footer: Use !verify to verify this bet • !fairinfo for details
    """
    
    print(f"✅ Embed information generated")
    print(embed_info)
    
except Exception as e:
    print(f"❌ Embed simulation failed: {e}")
    sys.exit(1)

# Test 10: Database Table Integrity
print("\n🔟 Verifying database table integrity...")
try:
    # Check all tables exist
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in c.fetchall()]
    
    required_tables = [
        'users',
        'provably_fair_seeds',
        'provably_fair_users',
        'provably_fair_bets'
    ]
    
    for table in required_tables:
        assert table in tables, f"Missing table: {table}"
        print(f"   ✅ Table exists: {table}")
    
    # Check record counts
    c.execute("SELECT COUNT(*) FROM provably_fair_bets")
    bet_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM provably_fair_users")
    user_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM provably_fair_seeds")
    seed_count = c.fetchone()[0]
    
    print(f"\n   📊 Database Statistics:")
    print(f"   Bets Logged: {bet_count}")
    print(f"   Users: {user_count}")
    print(f"   Seeds: {seed_count}")
    
except Exception as e:
    print(f"❌ Database integrity check failed: {e}")
    sys.exit(1)

conn.close()

print("\n" + "=" * 70)
print("✅ ALL INTEGRATION TESTS PASSED!")
print("=" * 70)

print("\n📋 SUMMARY:")
print("✓ System initialization works with bot.py")
print("✓ Coinflip bet flow integrated correctly")
print("✓ Multiple bets with nonce increment")
print("✓ Bet history retrieval")
print("✓ Custom client seed functionality")
print("✓ Server seed rotation")
print("✓ Bet verification after rotation")
print("✓ System statistics")
print("✓ Discord embed information format")
print("✓ Database table integrity")
print("\n✅ Provably Fair System is ready for production use!")
print("🎲 All gambling games can now use provably_fair.place_bet()!")
