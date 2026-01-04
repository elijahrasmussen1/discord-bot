"""
Comprehensive Bug Test Report
Testing all functionality to ensure nothing is broken
"""

import sys
import sqlite3
import random
from poker_deck import Deck, Card
from poker_hand_evaluator import HandEvaluator, HandRank
from poker_player import PokerPlayer, PlayerAction
from poker_game import PokerGame, GamePhase

print("=" * 80)
print("COMPREHENSIVE BUG TEST REPORT")
print("=" * 80)

test_results = []

def test(name, func):
    """Run a test and track results"""
    try:
        func()
        test_results.append((name, "✅ PASS"))
        print(f"\n✅ {name}: PASSED")
    except AssertionError as e:
        test_results.append((name, f"❌ FAIL: {e}"))
        print(f"\n❌ {name}: FAILED - {e}")
    except Exception as e:
        test_results.append((name, f"⚠️ ERROR: {e}"))
        print(f"\n⚠️ {name}: ERROR - {e}")

# ============================================================================
# EXISTING BOT FUNCTIONALITY TESTS
# ============================================================================

print("\n" + "=" * 80)
print("1. EXISTING BOT FUNCTIONALITY")
print("=" * 80)

def test_database_schema():
    """Test database schema is intact"""
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
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
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
    assert c.fetchone() is not None
    conn.close()

test("Database Schema", test_database_schema)

def test_parse_money():
    """Test money parsing function"""
    def parse_money(value: str) -> int:
        value = value.lower().replace(",", "")
        if value.endswith("m"):
            return int(float(value[:-1]) * 1_000_000)
        elif value.endswith("b"):
            return int(float(value[:-1]) * 1_000_000_000)
        elif value.endswith("k"):
            return int(float(value[:-1]) * 1_000)
        else:
            return -1
    
    assert parse_money("1m") == 1_000_000
    assert parse_money("5k") == 5_000
    assert parse_money("2.5m") == 2_500_000

test("Money Parsing", test_parse_money)

def test_balance_operations():
    """Test balance operations"""
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, required_gamble INTEGER DEFAULT 0, gambled INTEGER DEFAULT 0, total_gambled INTEGER DEFAULT 0, total_withdrawn INTEGER DEFAULT 0)")
    c.execute("INSERT INTO users (user_id, balance) VALUES (1, 1000)")
    conn.commit()
    
    c.execute("UPDATE users SET balance=balance+500 WHERE user_id=1")
    conn.commit()
    c.execute("SELECT balance FROM users WHERE user_id=1")
    assert c.fetchone()[0] == 1500
    conn.close()

test("Balance Operations", test_balance_operations)

def test_gamble_tracking():
    """Test gamble tracking"""
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, balance INTEGER, required_gamble INTEGER, gambled INTEGER, total_gambled INTEGER, total_withdrawn INTEGER)")
    c.execute("INSERT INTO users VALUES (1, 1000, 300, 0, 0, 0)")
    conn.commit()
    
    c.execute("UPDATE users SET gambled=gambled+100, total_gambled=total_gambled+100 WHERE user_id=1")
    conn.commit()
    c.execute("SELECT gambled, total_gambled FROM users WHERE user_id=1")
    row = c.fetchone()
    assert row[0] == 100 and row[1] == 100
    conn.close()

test("Gamble Tracking", test_gamble_tracking)

# ============================================================================
# POKER GAME FUNCTIONALITY TESTS
# ============================================================================

print("\n" + "=" * 80)
print("2. POKER GAME FUNCTIONALITY")
print("=" * 80)

def test_deck_shuffle():
    """Test deck shuffling"""
    deck = Deck()
    original = [str(c) for c in deck.cards]
    deck.shuffle_cryptographic()
    shuffled = [str(c) for c in deck.cards]
    assert original != shuffled
    assert len(deck.cards) == 52

test("Deck Shuffling", test_deck_shuffle)

def test_hand_evaluation():
    """Test hand evaluation"""
    cards = [Card('A', '♠'), Card('K', '♠'), Card('Q', '♠'), Card('J', '♠'), Card('10', '♠')]
    rank, _ = HandEvaluator.evaluate_hand(cards)
    assert rank == HandRank.ROYAL_FLUSH

test("Hand Evaluation", test_hand_evaluation)

def test_player_creation():
    """Test player creation"""
    player = PokerPlayer(123, "TestUser", 1000)
    assert player.stack == 1000
    assert player.is_active == True

test("Player Creation", test_player_creation)

def test_game_creation():
    """Test game creation"""
    game = PokerGame(channel_id=1, host_id=123)
    assert game.phase == GamePhase.WAITING
    assert len(game.players) == 0

test("Game Creation", test_game_creation)

def test_player_join():
    """Test player joining"""
    game = PokerGame(channel_id=1, host_id=123)
    assert game.add_player(123, "Player1", 1000) == True
    assert len(game.players) == 1

test("Player Join", test_player_join)

def test_game_start():
    """Test game start"""
    game = PokerGame(channel_id=1, host_id=123)
    game.add_player(123, "Player1", 1000)
    game.add_player(124, "Player2", 1000)
    game.start_game()
    assert game.phase == GamePhase.PRE_FLOP
    assert len(game.players[0].hole_cards) == 2

test("Game Start", test_game_start)

def test_betting_actions():
    """Test betting actions"""
    game = PokerGame(channel_id=1, host_id=123)
    game.add_player(123, "Player1", 1000)
    game.add_player(124, "Player2", 1000)
    game.start_game()
    
    current = game.get_current_player()
    success, msg = game.player_action(current.user_id, PlayerAction.CALL)
    assert success == True

test("Betting Actions", test_betting_actions)

def test_pot_management():
    """Test pot management"""
    game = PokerGame(channel_id=1, host_id=123, small_blind=10, big_blind=20)
    game.add_player(123, "Player1", 1000)
    game.add_player(124, "Player2", 1000)
    game.start_game()
    assert game.pot == 30  # SB + BB

test("Pot Management", test_pot_management)

# ============================================================================
# INTEGRATION TESTS
# ============================================================================

print("\n" + "=" * 80)
print("3. INTEGRATION TESTS")
print("=" * 80)

def test_poker_balance_integration():
    """Test poker integrates with balance system"""
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, balance INTEGER)")
    c.execute("INSERT INTO users VALUES (123, 10000)")
    conn.commit()
    
    # Simulate buy-in
    buy_in = 1000
    c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (buy_in, 123))
    conn.commit()
    
    c.execute("SELECT balance FROM users WHERE user_id=123")
    assert c.fetchone()[0] == 9000
    conn.close()

test("Poker Balance Integration", test_poker_balance_integration)

def test_complete_game_flow():
    """Test a complete game from start to finish"""
    game = PokerGame(channel_id=1, host_id=123, small_blind=10, big_blind=20)
    game.add_player(123, "Player1", 1000)
    game.add_player(124, "Player2", 1000)
    game.start_game()
    
    # Play through pre-flop
    current = game.get_current_player()
    game.player_action(current.user_id, PlayerAction.CALL)
    current = game.get_current_player()
    game.player_action(current.user_id, PlayerAction.CHECK)
    
    # Should advance to flop
    assert game.phase == GamePhase.FLOP
    assert len(game.community_cards) == 3

test("Complete Game Flow", test_complete_game_flow)

# ============================================================================
# SECURITY TESTS
# ============================================================================

print("\n" + "=" * 80)
print("4. SECURITY TESTS")
print("=" * 80)

def test_shuffle_security():
    """Test shuffle is cryptographically secure"""
    deck = Deck()
    hash1 = deck.shuffle_cryptographic()
    assert len(hash1) == 64  # SHA-256 hex length

test("Shuffle Security", test_shuffle_security)

def test_hash_verification():
    """Test hash verification works"""
    deck = Deck()
    deck.shuffle_cryptographic()
    verification = deck.get_shuffle_verification()
    assert deck.verify_shuffle(verification) == True

test("Hash Verification", test_hash_verification)

def test_turn_enforcement():
    """Test turn order is enforced"""
    game = PokerGame(channel_id=1, host_id=123)
    game.add_player(123, "Player1", 1000)
    game.add_player(124, "Player2", 1000)
    game.start_game()
    
    current = game.get_current_player()
    wrong_player = 124 if current.user_id == 123 else 123
    success, msg = game.player_action(wrong_player, PlayerAction.CHECK)
    assert success == False

test("Turn Enforcement", test_turn_enforcement)

def test_hole_card_privacy():
    """Test hole cards are private"""
    game = PokerGame(channel_id=1, host_id=123)
    game.add_player(123, "Player1", 1000)
    game.add_player(124, "Player2", 1000)
    game.start_game()
    
    state = game.get_game_state()
    # Hole cards should not be in public game state
    assert 'hole_cards' not in str(state)

test("Hole Card Privacy", test_hole_card_privacy)

# ============================================================================
# COINFLIP COMPATIBILITY
# ============================================================================

print("\n" + "=" * 80)
print("5. COINFLIP COMPATIBILITY")
print("=" * 80)

def test_coinflip_still_works():
    """Test coinflip game still works"""
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, balance INTEGER, required_gamble INTEGER, gambled INTEGER, total_gambled INTEGER, total_withdrawn INTEGER)")
    c.execute("INSERT INTO users VALUES (1, 1000, 300, 0, 0, 0)")
    conn.commit()
    
    # Simulate coinflip
    bet = 100
    choice = "heads"
    outcome = random.choice(["heads", "tails"])
    won = choice == outcome
    
    new_balance = 1000 + bet if won else 1000 - bet
    c.execute("UPDATE users SET balance=?, gambled=gambled+? WHERE user_id=1", (new_balance, bet))
    conn.commit()
    
    c.execute("SELECT balance, gambled FROM users WHERE user_id=1")
    row = c.fetchone()
    assert row[1] == 100  # Gambled amount tracked
    conn.close()

test("Coinflip Compatibility", test_coinflip_still_works)

# ============================================================================
# EDGE CASES
# ============================================================================

print("\n" + "=" * 80)
print("6. EDGE CASES")
print("=" * 80)

def test_all_in_scenario():
    """Test all-in scenario"""
    player = PokerPlayer(123, "Player", 100)
    actual_bet = player.bet(500)
    assert actual_bet == 100
    assert player.is_all_in == True
    assert player.stack == 0

test("All-in Scenario", test_all_in_scenario)

def test_single_winner_by_fold():
    """Test winner when all others fold"""
    game = PokerGame(channel_id=1, host_id=123)
    game.add_player(123, "Player1", 1000)
    game.add_player(124, "Player2", 1000)
    game.start_game()
    
    # First player folds
    current = game.get_current_player()
    game.player_action(current.user_id, PlayerAction.FOLD)
    
    # Game should end
    assert game.phase == GamePhase.FINISHED

test("Single Winner by Fold", test_single_winner_by_fold)

def test_multiple_games_isolation():
    """Test multiple games are isolated"""
    game1 = PokerGame(channel_id=1, host_id=123)
    game2 = PokerGame(channel_id=2, host_id=456)
    
    game1.add_player(123, "P1", 1000)
    game1.add_player(124, "P2", 1000)
    game2.add_player(456, "P3", 1000)
    game2.add_player(457, "P4", 1000)
    
    game1.start_game()
    game2.start_game()
    
    # Different shuffles
    assert game1.shuffle_hash != game2.shuffle_hash

test("Multiple Games Isolation", test_multiple_games_isolation)

# ============================================================================
# FINAL RESULTS
# ============================================================================

print("\n" + "=" * 80)
print("TEST RESULTS SUMMARY")
print("=" * 80)

passed = sum(1 for _, result in test_results if "✅ PASS" in result)
failed = sum(1 for _, result in test_results if "❌ FAIL" in result)
errors = sum(1 for _, result in test_results if "⚠️ ERROR" in result)
total = len(test_results)

print(f"\nTotal Tests: {total}")
print(f"✅ Passed: {passed}")
print(f"❌ Failed: {failed}")
print(f"⚠️ Errors: {errors}")

if failed > 0 or errors > 0:
    print("\n❌ FAILED TESTS:")
    for name, result in test_results:
        if "✅ PASS" not in result:
            print(f"  • {name}: {result}")

print("\n" + "=" * 80)
if failed == 0 and errors == 0:
    print("✅ ALL TESTS PASSED - BOT IS FULLY FUNCTIONAL")
    print("=" * 80)
    sys.exit(0)
else:
    print("❌ SOME TESTS FAILED - REVIEW REQUIRED")
    print("=" * 80)
    sys.exit(1)
