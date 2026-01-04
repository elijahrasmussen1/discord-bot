"""
Basic tests for poker game functionality.
These tests verify core game logic without requiring Discord.
"""

from poker_deck import Deck, Card
from poker_hand_evaluator import HandEvaluator, HandRank
from poker_player import PokerPlayer, PlayerAction
from poker_game import PokerGame, GamePhase


def test_deck_creation():
    """Test that a deck is created with 52 cards."""
    deck = Deck()
    assert len(deck.cards) == 52, "Deck should have 52 cards"
    print("✅ Deck creation test passed")


def test_cryptographic_shuffle():
    """Test that shuffle produces a hash and changes card order."""
    deck1 = Deck()
    original_order = [str(card) for card in deck1.cards]
    
    # Shuffle and get hash
    hash1 = deck1.shuffle_cryptographic()
    shuffled_order = [str(card) for card in deck1.cards]
    
    assert len(hash1) == 64, "SHA-256 hash should be 64 characters"
    assert original_order != shuffled_order, "Shuffle should change card order"
    
    # Verify the shuffle
    verification = deck1.get_shuffle_verification()
    assert deck1.verify_shuffle(verification), "Shuffle verification should pass"
    
    print("✅ Cryptographic shuffle test passed")


def test_dealing_cards():
    """Test dealing cards from the deck."""
    deck = Deck()
    deck.shuffle_cryptographic()
    
    # Deal 2 cards
    hand = deck.deal(2)
    assert len(hand) == 2, "Should deal 2 cards"
    assert deck.cards_remaining() == 50, "Should have 50 cards remaining"
    
    print("✅ Card dealing test passed")


def test_hand_evaluation_royal_flush():
    """Test royal flush detection."""
    cards = [
        Card('A', '♠'),
        Card('K', '♠'),
        Card('Q', '♠'),
        Card('J', '♠'),
        Card('10', '♠')
    ]
    rank, tiebreakers = HandEvaluator.evaluate_hand(cards)
    assert rank == HandRank.ROYAL_FLUSH, "Should detect royal flush"
    print("✅ Royal flush test passed")


def test_hand_evaluation_straight_flush():
    """Test straight flush detection."""
    cards = [
        Card('9', '♥'),
        Card('8', '♥'),
        Card('7', '♥'),
        Card('6', '♥'),
        Card('5', '♥')
    ]
    rank, tiebreakers = HandEvaluator.evaluate_hand(cards)
    assert rank == HandRank.STRAIGHT_FLUSH, "Should detect straight flush"
    assert tiebreakers[0] == 9, "High card should be 9"
    print("✅ Straight flush test passed")


def test_hand_evaluation_four_of_a_kind():
    """Test four of a kind detection."""
    cards = [
        Card('K', '♠'),
        Card('K', '♥'),
        Card('K', '♦'),
        Card('K', '♣'),
        Card('2', '♠')
    ]
    rank, tiebreakers = HandEvaluator.evaluate_hand(cards)
    assert rank == HandRank.FOUR_OF_A_KIND, "Should detect four of a kind"
    assert tiebreakers[0] == 13, "Four of a kind should be Kings (13)"
    print("✅ Four of a kind test passed")


def test_hand_evaluation_full_house():
    """Test full house detection."""
    cards = [
        Card('A', '♠'),
        Card('A', '♥'),
        Card('A', '♦'),
        Card('K', '♣'),
        Card('K', '♠')
    ]
    rank, tiebreakers = HandEvaluator.evaluate_hand(cards)
    assert rank == HandRank.FULL_HOUSE, "Should detect full house"
    assert tiebreakers[0] == 14, "Three of a kind should be Aces (14)"
    assert tiebreakers[1] == 13, "Pair should be Kings (13)"
    print("✅ Full house test passed")


def test_hand_evaluation_flush():
    """Test flush detection."""
    cards = [
        Card('A', '♣'),
        Card('J', '♣'),
        Card('8', '♣'),
        Card('5', '♣'),
        Card('2', '♣')
    ]
    rank, tiebreakers = HandEvaluator.evaluate_hand(cards)
    assert rank == HandRank.FLUSH, "Should detect flush"
    print("✅ Flush test passed")


def test_hand_evaluation_straight():
    """Test straight detection."""
    cards = [
        Card('10', '♠'),
        Card('9', '♥'),
        Card('8', '♦'),
        Card('7', '♣'),
        Card('6', '♠')
    ]
    rank, tiebreakers = HandEvaluator.evaluate_hand(cards)
    assert rank == HandRank.STRAIGHT, "Should detect straight"
    assert tiebreakers[0] == 10, "High card should be 10"
    print("✅ Straight test passed")


def test_hand_evaluation_three_of_a_kind():
    """Test three of a kind detection."""
    cards = [
        Card('Q', '♠'),
        Card('Q', '♥'),
        Card('Q', '♦'),
        Card('5', '♣'),
        Card('2', '♠')
    ]
    rank, tiebreakers = HandEvaluator.evaluate_hand(cards)
    assert rank == HandRank.THREE_OF_A_KIND, "Should detect three of a kind"
    assert tiebreakers[0] == 12, "Three of a kind should be Queens (12)"
    print("✅ Three of a kind test passed")


def test_hand_evaluation_two_pair():
    """Test two pair detection."""
    cards = [
        Card('J', '♠'),
        Card('J', '♥'),
        Card('5', '♦'),
        Card('5', '♣'),
        Card('2', '♠')
    ]
    rank, tiebreakers = HandEvaluator.evaluate_hand(cards)
    assert rank == HandRank.TWO_PAIR, "Should detect two pair"
    assert tiebreakers[0] == 11, "High pair should be Jacks (11)"
    assert tiebreakers[1] == 5, "Low pair should be 5s"
    print("✅ Two pair test passed")


def test_hand_evaluation_pair():
    """Test pair detection."""
    cards = [
        Card('10', '♠'),
        Card('10', '♥'),
        Card('K', '♦'),
        Card('5', '♣'),
        Card('2', '♠')
    ]
    rank, tiebreakers = HandEvaluator.evaluate_hand(cards)
    assert rank == HandRank.PAIR, "Should detect pair"
    assert tiebreakers[0] == 10, "Pair should be 10s"
    print("✅ Pair test passed")


def test_hand_evaluation_high_card():
    """Test high card detection."""
    cards = [
        Card('A', '♠'),
        Card('K', '♥'),
        Card('8', '♦'),
        Card('5', '♣'),
        Card('2', '♠')
    ]
    rank, tiebreakers = HandEvaluator.evaluate_hand(cards)
    assert rank == HandRank.HIGH_CARD, "Should detect high card"
    assert tiebreakers[0] == 14, "High card should be Ace (14)"
    print("✅ High card test passed")


def test_hand_comparison():
    """Test comparing hands."""
    # Royal flush vs straight flush
    royal_flush = (HandRank.ROYAL_FLUSH, [14])
    straight_flush = (HandRank.STRAIGHT_FLUSH, [9])
    assert HandEvaluator.compare_hands(royal_flush, straight_flush) == 1
    
    # Same rank, different kickers
    pair_aces = (HandRank.PAIR, [14, 13, 10, 5])
    pair_kings = (HandRank.PAIR, [13, 14, 10, 5])
    assert HandEvaluator.compare_hands(pair_aces, pair_kings) == 1
    
    # Tie
    hand1 = (HandRank.FLUSH, [14, 13, 10, 5, 2])
    hand2 = (HandRank.FLUSH, [14, 13, 10, 5, 2])
    assert HandEvaluator.compare_hands(hand1, hand2) == 0
    
    print("✅ Hand comparison test passed")


def test_player_creation():
    """Test creating a player."""
    player = PokerPlayer(12345, "TestPlayer", 1000)
    assert player.user_id == 12345
    assert player.username == "TestPlayer"
    assert player.stack == 1000
    assert player.is_active == True
    print("✅ Player creation test passed")


def test_player_actions():
    """Test player actions."""
    player = PokerPlayer(12345, "TestPlayer", 1000)
    
    # Test bet
    amount_bet = player.bet(100)
    assert amount_bet == 100
    assert player.stack == 900
    assert player.current_bet == 100
    assert player.last_action == PlayerAction.BET
    
    # Test call
    player.reset_for_new_round()
    amount_called = player.call(50)
    assert amount_called == 50
    assert player.stack == 850
    assert player.current_bet == 50
    
    # Test fold
    player.fold()
    assert player.is_active == False
    
    print("✅ Player actions test passed")


def test_player_all_in():
    """Test player going all-in."""
    player = PokerPlayer(12345, "TestPlayer", 50)
    
    # Try to bet more than stack
    amount_bet = player.bet(100)
    assert amount_bet == 50, "Should bet entire stack"
    assert player.stack == 0
    assert player.is_all_in == True
    assert player.last_action == PlayerAction.ALL_IN
    
    print("✅ Player all-in test passed")


def test_game_creation():
    """Test creating a poker game."""
    game = PokerGame(channel_id=123, host_id=456, small_blind=50, big_blind=100)
    assert game.channel_id == 123
    assert game.host_id == 456
    assert game.small_blind == 50
    assert game.big_blind == 100
    assert game.phase == GamePhase.WAITING
    print("✅ Game creation test passed")


def test_game_player_management():
    """Test adding and removing players."""
    game = PokerGame(channel_id=123, host_id=456)
    
    # Add players
    assert game.add_player(101, "Player1", 1000) == True
    assert game.add_player(102, "Player2", 1000) == True
    assert len(game.players) == 2
    
    # Try to add duplicate
    assert game.add_player(101, "Player1", 1000) == False
    
    # Remove player
    assert game.remove_player(102) == True
    assert len(game.players) == 1
    
    print("✅ Game player management test passed")


def test_game_start():
    """Test starting a game."""
    game = PokerGame(channel_id=123, host_id=456, small_blind=10, big_blind=20)
    
    # Add 2 players
    game.add_player(101, "Player1", 1000)
    game.add_player(102, "Player2", 1000)
    
    # Check can start
    assert game.can_start() == True
    
    # Start game
    game.start_game()
    assert game.phase == GamePhase.PRE_FLOP
    assert len(game.community_cards) == 0
    
    # Check players have hole cards
    assert len(game.players[0].hole_cards) == 2
    assert len(game.players[1].hole_cards) == 2
    
    # Check blinds were posted
    assert game.pot == 30  # 10 + 20
    
    print("✅ Game start test passed")


def test_betting_round():
    """Test a betting round."""
    game = PokerGame(channel_id=123, host_id=456, small_blind=10, big_blind=20)
    game.add_player(101, "Player1", 1000)
    game.add_player(102, "Player2", 1000)
    game.start_game()
    
    # Player 1 should act first (dealer in heads-up)
    current_player = game.get_current_player()
    assert current_player is not None
    
    # Player calls
    success, msg = game.player_action(current_player.user_id, PlayerAction.CALL)
    assert success == True
    
    # Now player 2's turn
    current_player = game.get_current_player()
    success, msg = game.player_action(current_player.user_id, PlayerAction.CHECK)
    assert success == True
    
    # Should advance to flop
    assert game.phase == GamePhase.FLOP
    assert len(game.community_cards) == 3
    
    print("✅ Betting round test passed")


def run_all_tests():
    """Run all tests."""
    print("\n🧪 Running Poker Game Tests\n")
    
    # Deck tests
    test_deck_creation()
    test_cryptographic_shuffle()
    test_dealing_cards()
    
    # Hand evaluation tests
    test_hand_evaluation_royal_flush()
    test_hand_evaluation_straight_flush()
    test_hand_evaluation_four_of_a_kind()
    test_hand_evaluation_full_house()
    test_hand_evaluation_flush()
    test_hand_evaluation_straight()
    test_hand_evaluation_three_of_a_kind()
    test_hand_evaluation_two_pair()
    test_hand_evaluation_pair()
    test_hand_evaluation_high_card()
    test_hand_comparison()
    
    # Player tests
    test_player_creation()
    test_player_actions()
    test_player_all_in()
    
    # Game tests
    test_game_creation()
    test_game_player_management()
    test_game_start()
    test_betting_round()
    
    print("\n✅ All tests passed! 🎉\n")


if __name__ == "__main__":
    run_all_tests()
