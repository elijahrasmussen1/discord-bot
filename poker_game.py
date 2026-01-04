"""
Poker Game Module
Core game logic for Texas Hold'em.
"""

import asyncio
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from poker_deck import Deck, Card
from poker_player import PokerPlayer, PlayerAction
from poker_hand_evaluator import HandEvaluator, HandRank


class GamePhase:
    """Constants for game phases."""
    WAITING = "waiting"
    PRE_FLOP = "pre_flop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    FINISHED = "finished"


class PokerGame:
    """Manages a Texas Hold'em poker game."""
    
    def __init__(self, channel_id: int, host_id: int, small_blind: int = 50, big_blind: int = 100):
        self.channel_id = channel_id
        self.host_id = host_id
        self.small_blind = small_blind
        self.big_blind = big_blind
        
        # Game state
        self.players: List[PokerPlayer] = []
        self.deck = Deck()
        self.community_cards: List[Card] = []
        self.pot = 0
        self.current_bet = 0
        self.phase = GamePhase.WAITING
        self.dealer_position = 0
        self.current_player_index = 0
        self.min_players = 2
        self.max_players = 10
        
        # Turn management
        self.turn_timeout = 30  # seconds
        self.turn_start_time = 0
        
        # Shuffle verification
        self.shuffle_hash = ""
        self.shuffle_verification: Optional[Dict] = None
        
        # Game log for replay
        self.game_log: List[Dict] = []
        self.hand_number = 0
        
        # Side pots for all-in situations
        self.side_pots: List[Dict] = []
    
    def add_player(self, user_id: int, username: str, buy_in: int) -> bool:
        """Add a player to the game."""
        if len(self.players) >= self.max_players:
            return False
        
        if self.phase != GamePhase.WAITING:
            return False
        
        if any(p.user_id == user_id for p in self.players):
            return False
        
        player = PokerPlayer(user_id, username, buy_in)
        player.position = len(self.players)
        self.players.append(player)
        
        self.log_action({
            'action': 'join',
            'user_id': user_id,
            'username': username,
            'buy_in': buy_in,
            'timestamp': datetime.now().isoformat()
        })
        
        return True
    
    def remove_player(self, user_id: int) -> bool:
        """Remove a player from the game."""
        if self.phase != GamePhase.WAITING:
            return False
        
        self.players = [p for p in self.players if p.user_id != user_id]
        
        # Update positions
        for i, player in enumerate(self.players):
            player.position = i
        
        self.log_action({
            'action': 'leave',
            'user_id': user_id,
            'timestamp': datetime.now().isoformat()
        })
        
        return True
    
    def can_start(self) -> bool:
        """Check if the game can start."""
        return len(self.players) >= self.min_players and self.phase == GamePhase.WAITING
    
    def start_game(self):
        """Start the poker game."""
        if not self.can_start():
            raise ValueError("Cannot start game - need at least 2 players")
        
        self.hand_number = 1
        self.start_new_hand()
        
        self.log_action({
            'action': 'game_start',
            'players': [{'user_id': p.user_id, 'username': p.username, 'stack': p.stack} for p in self.players],
            'timestamp': datetime.now().isoformat()
        })
    
    def start_new_hand(self):
        """Start a new hand."""
        # Reset deck and shuffle
        self.deck.reset()
        self.shuffle_hash = self.deck.shuffle_cryptographic()
        
        # Reset game state
        self.community_cards = []
        self.pot = 0
        self.current_bet = 0
        self.side_pots = []
        
        # Reset players for new hand
        for player in self.players:
            player.reset_for_new_hand()
        
        # Remove players with no chips
        self.players = [p for p in self.players if p.stack > 0]
        
        if len(self.players) < 2:
            self.phase = GamePhase.FINISHED
            return
        
        # Deal hole cards
        for player in self.players:
            player.deal_hole_cards(self.deck.deal(2))
        
        # Post blinds
        self.post_blinds()
        
        # Start pre-flop betting
        self.phase = GamePhase.PRE_FLOP
        self.start_betting_round()
        
        self.log_action({
            'action': 'new_hand',
            'hand_number': self.hand_number,
            'shuffle_hash': self.shuffle_hash,
            'dealer_position': self.dealer_position,
            'timestamp': datetime.now().isoformat()
        })
    
    def post_blinds(self):
        """Post small and big blinds."""
        num_players = len(self.players)
        
        if num_players == 2:
            # Heads-up: dealer posts small blind
            sb_pos = self.dealer_position
            bb_pos = (self.dealer_position + 1) % num_players
        else:
            # Multi-way: small blind is left of dealer
            sb_pos = (self.dealer_position + 1) % num_players
            bb_pos = (self.dealer_position + 2) % num_players
        
        # Post small blind
        sb_player = self.players[sb_pos]
        sb_amount = sb_player.bet(min(self.small_blind, sb_player.stack))
        self.pot += sb_amount
        self.current_bet = sb_amount
        
        self.log_action({
            'action': 'small_blind',
            'user_id': sb_player.user_id,
            'amount': sb_amount,
            'timestamp': datetime.now().isoformat()
        })
        
        # Post big blind
        bb_player = self.players[bb_pos]
        bb_amount = bb_player.bet(min(self.big_blind, bb_player.stack))
        self.pot += bb_amount
        self.current_bet = bb_amount
        
        self.log_action({
            'action': 'big_blind',
            'user_id': bb_player.user_id,
            'amount': bb_amount,
            'timestamp': datetime.now().isoformat()
        })
    
    def start_betting_round(self):
        """Start a new betting round."""
        # Reset players for new betting round (except pre-flop where blinds are already posted)
        if self.phase != GamePhase.PRE_FLOP:
            for player in self.players:
                player.reset_for_new_round()
        else:
            # For pre-flop, only reset has_acted flag
            for player in self.players:
                player.has_acted = False
        
        # Determine first player to act
        num_players = len(self.players)
        
        if self.phase == GamePhase.PRE_FLOP:
            # Pre-flop: first to act is left of big blind
            if num_players == 2:
                self.current_player_index = self.dealer_position
            else:
                self.current_player_index = (self.dealer_position + 3) % num_players
        else:
            # Post-flop: first to act is left of dealer
            self.current_player_index = (self.dealer_position + 1) % num_players
        
        # Skip to first active player who can act (if current player can't act)
        current_player = self.players[self.current_player_index]
        if not current_player.is_active or current_player.is_all_in:
            self.advance_to_next_player()
        
        self.turn_start_time = time.time()
    
    def advance_to_next_player(self):
        """Advance to the next player who can act."""
        num_players = len(self.players)
        start_index = self.current_player_index
        
        # Move to next player
        self.current_player_index = (self.current_player_index + 1) % num_players
        
        # Find next player who can act
        while True:
            player = self.players[self.current_player_index]
            
            # Player can act if they're active and not all-in
            if player.is_active and not player.is_all_in:
                break
            
            self.current_player_index = (self.current_player_index + 1) % num_players
            
            # If we've looped back, no one else can act
            if self.current_player_index == start_index:
                break
        
        self.turn_start_time = time.time()
    
    def get_current_player(self) -> Optional[PokerPlayer]:
        """Get the player whose turn it is."""
        if self.phase in [GamePhase.WAITING, GamePhase.FINISHED, GamePhase.SHOWDOWN]:
            return None
        return self.players[self.current_player_index]
    
    def is_betting_round_complete(self) -> bool:
        """Check if the current betting round is complete."""
        active_players = [p for p in self.players if p.is_active and not p.is_all_in]
        
        if len(active_players) == 0:
            return True
        
        if len(active_players) == 1:
            return True
        
        # All active players have acted and matched the current bet
        for player in active_players:
            if not player.has_acted:
                return False
            if player.current_bet < self.current_bet:
                return False
        
        return True
    
    def player_action(self, user_id: int, action: str, amount: int = 0) -> Tuple[bool, str]:
        """
        Process a player action.
        Returns (success, message)
        """
        current_player = self.get_current_player()
        
        if current_player is None or current_player.user_id != user_id:
            return False, "It's not your turn!"
        
        if action == PlayerAction.FOLD:
            current_player.fold()
            message = f"{current_player.username} folds"
        
        elif action == PlayerAction.CHECK:
            if self.current_bet > current_player.current_bet:
                return False, "You cannot check, there is a bet to call"
            current_player.check()
            message = f"{current_player.username} checks"
        
        elif action == PlayerAction.CALL:
            amount_to_call = self.current_bet - current_player.current_bet
            if amount_to_call == 0:
                return False, "Nothing to call, you can check"
            actual_call = current_player.call(amount_to_call)
            self.pot += actual_call
            message = f"{current_player.username} calls {actual_call}"
        
        elif action == PlayerAction.BET:
            if self.current_bet > 0:
                return False, "There is already a bet, use raise instead"
            if amount < self.big_blind:
                return False, f"Minimum bet is {self.big_blind}"
            actual_bet = current_player.bet(amount)
            self.pot += actual_bet
            self.current_bet = current_player.current_bet
            message = f"{current_player.username} bets {actual_bet}"
        
        elif action == PlayerAction.RAISE:
            amount_to_call = self.current_bet - current_player.current_bet
            min_raise = self.current_bet + self.big_blind
            total_bet = amount_to_call + amount
            
            if total_bet < min_raise and current_player.stack > min_raise:
                return False, f"Minimum raise is {min_raise}"
            
            actual_raise = current_player.raise_bet(amount, amount_to_call)
            self.pot += actual_raise
            self.current_bet = current_player.current_bet
            
            # Reset other players' acted status since there's a new bet
            for p in self.players:
                if p.user_id != user_id and p.is_active and not p.is_all_in:
                    p.has_acted = False
            
            message = f"{current_player.username} raises to {current_player.current_bet}"
        
        else:
            return False, "Invalid action"
        
        self.log_action({
            'action': action,
            'user_id': user_id,
            'username': current_player.username,
            'amount': amount,
            'pot': self.pot,
            'timestamp': datetime.now().isoformat()
        })
        
        # Check if betting round is complete
        if self.is_betting_round_complete():
            self.advance_phase()
        else:
            self.advance_to_next_player()
        
        return True, message
    
    def advance_phase(self):
        """Advance to the next phase of the game."""
        active_players = [p for p in self.players if p.is_active]
        
        # If only one player remains, they win
        if len(active_players) == 1:
            self.phase = GamePhase.SHOWDOWN
            self.determine_winner()
            return
        
        if self.phase == GamePhase.PRE_FLOP:
            # Deal the flop
            self.community_cards.extend(self.deck.deal(3))
            self.phase = GamePhase.FLOP
            self.current_bet = 0  # Reset current bet for new round
            self.start_betting_round()
            
            self.log_action({
                'action': 'flop',
                'cards': [str(c) for c in self.community_cards],
                'timestamp': datetime.now().isoformat()
            })
        
        elif self.phase == GamePhase.FLOP:
            # Deal the turn
            self.community_cards.append(self.deck.deal(1)[0])
            self.phase = GamePhase.TURN
            self.current_bet = 0  # Reset current bet for new round
            self.start_betting_round()
            
            self.log_action({
                'action': 'turn',
                'card': str(self.community_cards[-1]),
                'timestamp': datetime.now().isoformat()
            })
        
        elif self.phase == GamePhase.TURN:
            # Deal the river
            self.community_cards.append(self.deck.deal(1)[0])
            self.phase = GamePhase.RIVER
            self.current_bet = 0  # Reset current bet for new round
            self.start_betting_round()
            
            self.log_action({
                'action': 'river',
                'card': str(self.community_cards[-1]),
                'timestamp': datetime.now().isoformat()
            })
        
        elif self.phase == GamePhase.RIVER:
            # Go to showdown
            self.phase = GamePhase.SHOWDOWN
            self.determine_winner()
    
    def determine_winner(self):
        """Determine the winner(s) and distribute pot."""
        active_players = [p for p in self.players if p.is_active]
        
        if len(active_players) == 1:
            # Only one player left, they win
            winner = active_players[0]
            winner.stack += self.pot
            
            self.log_action({
                'action': 'winner',
                'user_id': winner.user_id,
                'username': winner.username,
                'amount': self.pot,
                'reason': 'all others folded',
                'timestamp': datetime.now().isoformat()
            })
            
            self.shuffle_verification = self.deck.get_shuffle_verification()
            self.phase = GamePhase.FINISHED
            return
        
        # Multiple players, evaluate hands
        player_hands = []
        for player in active_players:
            all_cards = player.hole_cards + self.community_cards
            hand_rank, tiebreakers = HandEvaluator.evaluate_hand(all_cards)
            hand_desc = HandEvaluator.get_hand_description(hand_rank, tiebreakers)
            player_hands.append({
                'player': player,
                'rank': hand_rank,
                'tiebreakers': tiebreakers,
                'description': hand_desc
            })
        
        # Sort by hand strength
        player_hands.sort(key=lambda x: (x['rank'], x['tiebreakers']), reverse=True)
        
        # Determine winners (may be multiple in case of tie)
        best_hand = player_hands[0]
        winners = [best_hand['player']]
        
        for ph in player_hands[1:]:
            comparison = HandEvaluator.compare_hands(
                (best_hand['rank'], best_hand['tiebreakers']),
                (ph['rank'], ph['tiebreakers'])
            )
            if comparison == 0:
                winners.append(ph['player'])
            else:
                break
        
        # Distribute pot
        pot_share = self.pot // len(winners)
        remainder = self.pot % len(winners)
        
        for i, winner in enumerate(winners):
            share = pot_share + (1 if i < remainder else 0)
            winner.stack += share
            
            # Find winner's hand description
            hand_desc = next(ph['description'] for ph in player_hands if ph['player'].user_id == winner.user_id)
            
            self.log_action({
                'action': 'winner',
                'user_id': winner.user_id,
                'username': winner.username,
                'amount': share,
                'hand': hand_desc,
                'hole_cards': winner.get_hole_cards_string(),
                'timestamp': datetime.now().isoformat()
            })
        
        self.shuffle_verification = self.deck.get_shuffle_verification()
        self.phase = GamePhase.FINISHED
    
    def get_time_remaining(self) -> int:
        """Get seconds remaining for current player's turn."""
        elapsed = time.time() - self.turn_start_time
        remaining = max(0, self.turn_timeout - int(elapsed))
        return remaining
    
    def is_turn_expired(self) -> bool:
        """Check if current player's turn has expired."""
        return time.time() - self.turn_start_time >= self.turn_timeout
    
    def handle_turn_timeout(self):
        """Handle a turn timeout by auto-folding the current player."""
        current_player = self.get_current_player()
        if current_player:
            self.player_action(current_player.user_id, PlayerAction.FOLD)
    
    def log_action(self, action_data: Dict):
        """Log a game action for replay."""
        self.game_log.append(action_data)
    
    def get_game_state(self) -> Dict:
        """Get current game state for display."""
        return {
            'phase': self.phase,
            'pot': self.pot,
            'current_bet': self.current_bet,
            'community_cards': [str(c) for c in self.community_cards],
            'players': [
                {
                    'user_id': p.user_id,
                    'username': p.username,
                    'stack': p.stack,
                    'current_bet': p.current_bet,
                    'is_active': p.is_active,
                    'is_all_in': p.is_all_in,
                    'last_action': p.last_action,
                    'position': p.position
                }
                for p in self.players
            ],
            'current_player': self.get_current_player().user_id if self.get_current_player() else None,
            'time_remaining': self.get_time_remaining() if self.get_current_player() else 0,
            'dealer_position': self.dealer_position
        }
