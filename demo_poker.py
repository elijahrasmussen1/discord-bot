"""
Poker Game Demo Script
This demonstrates a complete poker game without Discord.
"""

from poker_game import PokerGame, GamePhase
from poker_player import PlayerAction


def print_separator():
    print("\n" + "=" * 60 + "\n")


def print_game_state(game):
    """Print the current game state."""
    print(f"Phase: {game.phase}")
    print(f"Pot: ${game.pot}")
    print(f"Current Bet: ${game.current_bet}")
    
    if game.community_cards:
        cards_str = " ".join(str(c) for c in game.community_cards)
        print(f"Community Cards: {cards_str}")
    
    print("\nPlayers:")
    for i, player in enumerate(game.players):
        status = "✅" if player.is_active else "❌"
        if player.is_all_in:
            status = "🔴"
        
        dealer = " (DEALER)" if i == game.dealer_position else ""
        current = " <- YOUR TURN" if game.get_current_player() and player.user_id == game.get_current_player().user_id else ""
        action = f" [{player.last_action}]" if player.last_action else ""
        
        print(f"  {status} {player.username}{dealer}: ${player.stack} (bet: ${player.current_bet}){action}{current}")


def demo_game():
    """Run a demo poker game."""
    print("🃏 Texas Hold'em Poker Demo")
    print_separator()
    
    # Create game
    game = PokerGame(channel_id=1, host_id=101, small_blind=50, big_blind=100)
    print("Created poker table:")
    print(f"  Small Blind: ${game.small_blind}")
    print(f"  Big Blind: ${game.big_blind}")
    
    # Add players
    print("\nPlayers joining...")
    game.add_player(101, "Alice", 1000)
    game.add_player(102, "Bob", 1000)
    print("  ✓ Alice joined with $1000")
    print("  ✓ Bob joined with $1000")
    
    print_separator()
    
    # Start game
    print("Starting game...")
    game.start_game()
    print(f"Shuffle Hash (for verification): {game.shuffle_hash[:32]}...")
    
    # Show initial state
    print_separator()
    print("PRE-FLOP")
    print_game_state(game)
    
    print("\nHole Cards:")
    for player in game.players:
        cards = " ".join(str(c) for c in player.hole_cards)
        print(f"  {player.username}: {cards}")
    
    # Pre-flop betting
    print_separator()
    current = game.get_current_player()
    print(f"{current.username} to act (needs to call $90 more)...")
    success, msg = game.player_action(current.user_id, PlayerAction.CALL)
    print(f"  Action: {msg}")
    
    current = game.get_current_player()
    print(f"\n{current.username} to act...")
    success, msg = game.player_action(current.user_id, PlayerAction.CHECK)
    print(f"  Action: {msg}")
    
    # Flop
    print_separator()
    print("FLOP")
    print_game_state(game)
    
    current = game.get_current_player()
    print(f"\n{current.username} to act...")
    success, msg = game.player_action(current.user_id, PlayerAction.BET, 100)
    print(f"  Action: {msg}")
    
    current = game.get_current_player()
    print(f"\n{current.username} to act...")
    success, msg = game.player_action(current.user_id, PlayerAction.CALL)
    print(f"  Action: {msg}")
    
    # Turn
    print_separator()
    print("TURN")
    print_game_state(game)
    
    current = game.get_current_player()
    print(f"\n{current.username} to act...")
    success, msg = game.player_action(current.user_id, PlayerAction.CHECK)
    print(f"  Action: {msg}")
    
    current = game.get_current_player()
    print(f"\n{current.username} to act...")
    success, msg = game.player_action(current.user_id, PlayerAction.CHECK)
    print(f"  Action: {msg}")
    
    # River
    print_separator()
    print("RIVER")
    print_game_state(game)
    
    current = game.get_current_player()
    print(f"\n{current.username} to act...")
    success, msg = game.player_action(current.user_id, PlayerAction.BET, 200)
    print(f"  Action: {msg}")
    
    current = game.get_current_player()
    print(f"\n{current.username} to act...")
    success, msg = game.player_action(current.user_id, PlayerAction.CALL)
    print(f"  Action: {msg}")
    
    # Showdown
    print_separator()
    print("SHOWDOWN")
    print_game_state(game)
    
    print("\n🏆 Results:")
    winners = [log for log in game.game_log if log.get('action') == 'winner']
    for winner_log in winners:
        print(f"  Winner: {winner_log['username']}")
        print(f"  Hand: {winner_log['hand']}")
        print(f"  Hole Cards: {winner_log['hole_cards']}")
        print(f"  Won: ${winner_log['amount']}")
    
    # Shuffle verification
    print("\n🔒 Shuffle Verification:")
    verification = game.shuffle_verification
    is_valid = game.deck.verify_shuffle(verification)
    print(f"  Hash: {verification['hash'][:32]}...")
    print(f"  Verified: {'✅ Fair shuffle confirmed' if is_valid else '❌ Verification failed'}")
    
    print_separator()
    print("Game complete!")


if __name__ == "__main__":
    demo_game()
