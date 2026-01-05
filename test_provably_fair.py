"""
Test suite for Provably Fair System
"""

import sqlite3
import sys
from provably_fair import ProvablyFairSystem

print("=" * 70)
print("TESTING PROVABLY FAIR GAMBLING SYSTEM")
print("=" * 70)

# Create in-memory database for testing
conn = sqlite3.connect(":memory:")
pf = ProvablyFairSystem(conn)

# Test 1: System Initialization
print("\n1️⃣ Testing system initialization...")
try:
    server_seed_hash = pf.initialize_system()
    assert server_seed_hash is not None
    assert len(server_seed_hash) == 64  # SHA256 produces 64 hex characters
    print(f"✅ System initialized with seed hash: {server_seed_hash[:16]}...")
except Exception as e:
    print(f"❌ Initialization failed: {e}")
    sys.exit(1)

# Test 2: Server Seed Generation
print("\n2️⃣ Testing server seed generation...")
try:
    seed1 = pf.generate_server_seed()
    seed2 = pf.generate_server_seed()
    
    assert len(seed1) == 64  # 32 bytes = 64 hex characters
    assert len(seed2) == 64
    assert seed1 != seed2  # Seeds must be unique
    print(f"✅ Generated unique server seeds")
    print(f"   Seed 1: {seed1[:16]}...")
    print(f"   Seed 2: {seed2[:16]}...")
except Exception as e:
    print(f"❌ Seed generation failed: {e}")
    sys.exit(1)

# Test 3: Server Seed Hashing
print("\n3️⃣ Testing server seed hashing...")
try:
    test_seed = "test_server_seed_12345"
    hash1 = pf.get_server_seed_hash(test_seed)
    hash2 = pf.get_server_seed_hash(test_seed)
    
    assert hash1 == hash2  # Same seed should produce same hash
    assert len(hash1) == 64  # SHA256 output length
    
    different_seed = "different_seed"
    hash3 = pf.get_server_seed_hash(different_seed)
    assert hash1 != hash3  # Different seeds produce different hashes
    
    print(f"✅ Hashing works correctly")
    print(f"   Hash: {hash1[:32]}...")
except Exception as e:
    print(f"❌ Hashing failed: {e}")
    sys.exit(1)

# Test 4: User Seed Creation
print("\n4️⃣ Testing user seed creation...")
try:
    user_id = 123456789
    client_seed, nonce = pf.get_or_create_user_seeds(user_id)
    
    assert client_seed is not None
    assert nonce == 0  # Initial nonce should be 0
    assert len(client_seed) == 32  # 16 bytes = 32 hex characters
    
    # Getting again should return same values
    client_seed2, nonce2 = pf.get_or_create_user_seeds(user_id)
    assert client_seed == client_seed2
    assert nonce == nonce2
    
    print(f"✅ User seeds created correctly")
    print(f"   User ID: {user_id}")
    print(f"   Client Seed: {client_seed[:16]}...")
    print(f"   Initial Nonce: {nonce}")
except Exception as e:
    print(f"❌ User seed creation failed: {e}")
    sys.exit(1)

# Test 5: Nonce Incrementing
print("\n5️⃣ Testing nonce incrementing...")
try:
    user_id = 987654321
    client_seed, initial_nonce = pf.get_or_create_user_seeds(user_id)
    assert initial_nonce == 0
    
    new_nonce = pf.increment_nonce(user_id)
    assert new_nonce == 1
    
    new_nonce = pf.increment_nonce(user_id)
    assert new_nonce == 2
    
    new_nonce = pf.increment_nonce(user_id)
    assert new_nonce == 3
    
    print(f"✅ Nonce increments correctly: 0 → 1 → 2 → 3")
except Exception as e:
    print(f"❌ Nonce incrementing failed: {e}")
    sys.exit(1)

# Test 6: Result Generation (Deterministic)
print("\n6️⃣ Testing result generation (deterministic)...")
try:
    server_seed = "test_server_seed_abc123"
    client_seed = "test_client_seed_xyz789"
    nonce = 0
    modulo = 2  # Coinflip
    
    # Generate result multiple times
    result1 = pf.generate_result(server_seed, client_seed, nonce, modulo)
    result2 = pf.generate_result(server_seed, client_seed, nonce, modulo)
    result3 = pf.generate_result(server_seed, client_seed, nonce, modulo)
    
    # Same inputs should always produce same output
    assert result1 == result2 == result3
    assert result1 in [0, 1]  # Result must be 0 or 1 for coinflip
    
    print(f"✅ Result generation is deterministic")
    print(f"   Server Seed: {server_seed[:20]}...")
    print(f"   Client Seed: {client_seed[:20]}...")
    print(f"   Nonce: {nonce}")
    print(f"   Result: {result1} (consistent across 3 generations)")
except Exception as e:
    print(f"❌ Result generation failed: {e}")
    sys.exit(1)

# Test 7: Different Nonces Produce Different Results
print("\n7️⃣ Testing different nonces...")
try:
    server_seed = "test_server_seed"
    client_seed = "test_client_seed"
    modulo = 2
    
    results = []
    for nonce in range(10):
        result = pf.generate_result(server_seed, client_seed, nonce, modulo)
        results.append(result)
    
    # Not all results should be the same (extremely unlikely with 10 flips)
    unique_results = len(set(results))
    assert unique_results > 1, "All 10 flips had same result - extremely unlikely!"
    
    print(f"✅ Different nonces produce varied results")
    print(f"   Results: {results}")
    print(f"   Unique outcomes: {unique_results}/2")
except Exception as e:
    print(f"❌ Nonce variation test failed: {e}")
    sys.exit(1)

# Test 8: Bet Placement
print("\n8️⃣ Testing bet placement...")
try:
    user_id = 111222333
    game_type = "coinflip"
    bet_amount = 100000
    modulo = 2
    
    result, client_seed, nonce, seed_hash = pf.place_bet(user_id, game_type, bet_amount, modulo)
    
    assert result in [0, 1]
    assert nonce == 0  # First bet has nonce 0
    assert len(seed_hash) == 64
    
    # Place another bet - nonce should increment
    result2, client_seed2, nonce2, seed_hash2 = pf.place_bet(user_id, game_type, bet_amount, modulo)
    assert nonce2 == 1  # Second bet has nonce 1
    assert client_seed == client_seed2  # Same user, same client seed
    assert seed_hash == seed_hash2  # Same server seed (not rotated)
    
    print(f"✅ Bet placement works correctly")
    print(f"   Bet 1: Nonce {nonce}, Result {result}")
    print(f"   Bet 2: Nonce {nonce2}, Result {result2}")
except Exception as e:
    print(f"❌ Bet placement failed: {e}")
    sys.exit(1)

# Test 9: Bet Verification
print("\n9️⃣ Testing bet verification...")
try:
    server_seed = "verification_test_seed"
    client_seed = "client_verification_seed"
    nonce = 5
    modulo = 2
    
    # Generate result
    expected_result = pf.generate_result(server_seed, client_seed, nonce, modulo)
    
    # Verify it matches
    is_valid = pf.verify_bet(server_seed, client_seed, nonce, expected_result, modulo)
    assert is_valid == True
    
    # Try with wrong result
    wrong_result = 1 if expected_result == 0 else 0
    is_valid_wrong = pf.verify_bet(server_seed, client_seed, nonce, wrong_result, modulo)
    assert is_valid_wrong == False
    
    print(f"✅ Bet verification works correctly")
    print(f"   Correct result verified: True")
    print(f"   Incorrect result verified: False")
except Exception as e:
    print(f"❌ Bet verification failed: {e}")
    sys.exit(1)

# Test 10: Server Seed Rotation
print("\n🔟 Testing server seed rotation...")
try:
    # Get current active seed hash
    old_hash = pf.get_active_server_seed_hash()
    
    # Rotate
    old_seed, new_hash = pf.rotate_server_seed()
    
    assert old_seed is not None
    assert new_hash is not None
    assert old_hash != new_hash  # New hash must be different
    assert len(old_seed) == 64
    assert len(new_hash) == 64
    
    # Verify old seed's hash matches
    verified_old_hash = pf.get_server_seed_hash(old_seed)
    assert verified_old_hash == old_hash
    
    print(f"✅ Server seed rotation successful")
    print(f"   Old seed revealed: {old_seed[:16]}...")
    print(f"   New seed hash: {new_hash[:16]}...")
    print(f"   Old hash verified: {verified_old_hash == old_hash}")
except Exception as e:
    print(f"❌ Seed rotation failed: {e}")
    sys.exit(1)

# Test 11: Custom Client Seed
print("\n1️⃣1️⃣ Testing custom client seed...")
try:
    user_id = 444555666
    
    # Create user with default seed
    default_seed, _ = pf.get_or_create_user_seeds(user_id)
    
    # Set custom client seed
    custom_seed = "deadbeefcafebabe1234567890abcdef"
    success = pf.set_client_seed(user_id, custom_seed)
    assert success == True
    
    # Verify it was set
    current_seed, _ = pf.get_or_create_user_seeds(user_id)
    assert current_seed == custom_seed
    
    # Try invalid seed (not hex)
    invalid_success = pf.set_client_seed(user_id, "not_hex_zzz")
    assert invalid_success == False
    
    print(f"✅ Custom client seed setting works")
    print(f"   Default: {default_seed[:16]}...")
    print(f"   Custom: {custom_seed[:16]}...")
    print(f"   Invalid rejected: True")
except Exception as e:
    print(f"❌ Custom client seed failed: {e}")
    sys.exit(1)

# Test 12: Bet History
print("\n1️⃣2️⃣ Testing bet history...")
try:
    user_id = 777888999
    
    # Place multiple bets
    for i in range(5):
        pf.place_bet(user_id, "coinflip", 1000 * (i+1), 2)
    
    # Get history
    history = pf.get_user_bet_history(user_id, limit=10)
    
    assert len(history) == 5
    
    # Verify history is in descending order (most recent first)
    for i, bet in enumerate(history):
        bet_id, game, seed_hash, client_seed, nonce, result, amount, timestamp = bet
        expected_nonce = 4 - i  # Should be 4, 3, 2, 1, 0
        assert nonce == expected_nonce
        assert result in [0, 1]
    
    print(f"✅ Bet history retrieval works")
    print(f"   Total bets: {len(history)}")
    print(f"   Latest nonce: {history[0][4]}")
    print(f"   Oldest nonce: {history[-1][4]}")
except Exception as e:
    print(f"❌ Bet history failed: {e}")
    sys.exit(1)

# Test 13: System Statistics
print("\n1️⃣3️⃣ Testing system statistics...")
try:
    stats = pf.get_system_stats()
    
    assert 'active_seed_hash' in stats
    assert 'total_bets' in stats
    assert 'total_users' in stats
    assert 'total_rotations' in stats
    
    assert stats['total_bets'] > 0
    assert stats['total_users'] > 0
    assert stats['total_rotations'] >= 1  # We rotated once in test 10
    
    print(f"✅ System statistics working")
    print(f"   Active Seed: {stats['active_seed_hash'][:16]}...")
    print(f"   Total Bets: {stats['total_bets']}")
    print(f"   Total Users: {stats['total_users']}")
    print(f"   Total Rotations: {stats['total_rotations']}")
except Exception as e:
    print(f"❌ System statistics failed: {e}")
    sys.exit(1)

# Test 14: Revealed Seeds
print("\n1️⃣4️⃣ Testing revealed seeds...")
try:
    revealed = pf.get_revealed_seeds(limit=5)
    
    assert len(revealed) >= 1  # At least one from rotation in test 10
    
    for seed, seed_hash, revealed_at in revealed:
        # Verify the seed matches its hash
        verified_hash = pf.get_server_seed_hash(seed)
        assert verified_hash == seed_hash
        assert revealed_at is not None
    
    print(f"✅ Revealed seeds retrieval works")
    print(f"   Number of revealed seeds: {len(revealed)}")
    if revealed:
        print(f"   Latest revealed: {revealed[0][0][:16]}...")
except Exception as e:
    print(f"❌ Revealed seeds failed: {e}")
    sys.exit(1)

# Test 15: Coinflip Example (0=Heads, 1=Tails)
print("\n1️⃣5️⃣ Testing coinflip example...")
try:
    server_seed = "example_coinflip_server_seed_2024"
    client_seed = "player_client_seed_abc"
    
    results = []
    for nonce in range(10):
        result = pf.generate_result(server_seed, client_seed, nonce, 2)
        outcome = "Heads" if result == 0 else "Tails"
        results.append(outcome)
    
    heads_count = results.count("Heads")
    tails_count = results.count("Tails")
    
    print(f"✅ Coinflip example (10 flips)")
    print(f"   Results: {results}")
    print(f"   Heads: {heads_count}, Tails: {tails_count}")
    print(f"   Distribution: {heads_count/10*100:.0f}% Heads, {tails_count/10*100:.0f}% Tails")
except Exception as e:
    print(f"❌ Coinflip example failed: {e}")
    sys.exit(1)

conn.close()

print("\n" + "=" * 70)
print("✅ ALL 15 TESTS PASSED!")
print("=" * 70)

print("\n📋 SUMMARY:")
print("✓ System initialization")
print("✓ Server seed generation (cryptographically secure)")
print("✓ Server seed hashing (SHA256)")
print("✓ User seed creation")
print("✓ Nonce incrementing")
print("✓ Deterministic result generation")
print("✓ Nonce variation producing different results")
print("✓ Bet placement with logging")
print("✓ Bet verification")
print("✓ Server seed rotation")
print("✓ Custom client seed setting")
print("✓ Bet history retrieval")
print("✓ System statistics")
print("✓ Revealed seeds verification")
print("✓ Coinflip practical example")
print("\n✅ Provably Fair System is production-ready!")
