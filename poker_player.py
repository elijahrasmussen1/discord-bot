"""
Poker Player Module
Manages individual player state and actions.
"""

from typing import List, Optional
from poker_deck import Card


class PlayerAction:
    """Constants for player actions."""
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


class PokerPlayer:
    """Represents a player in a poker game."""
    
    def __init__(self, user_id: int, username: str, stack: int):
        self.user_id = user_id
        self.username = username
        self.stack = stack  # Chip count
        self.hole_cards: List[Card] = []
        self.current_bet = 0  # Amount bet in current betting round
        self.total_bet = 0  # Total amount bet in this hand
        self.is_active = True  # Still in the hand
        self.is_all_in = False
        self.has_acted = False  # Has acted in current betting round
        self.last_action: Optional[str] = None
        self.position = 0  # Position at table (0 = dealer button)
    
    def reset_for_new_hand(self):
        """Reset player state for a new hand."""
        self.hole_cards = []
        self.current_bet = 0
        self.total_bet = 0
        self.is_active = True
        self.is_all_in = False
        self.has_acted = False
        self.last_action = None
    
    def reset_for_new_round(self):
        """Reset player state for a new betting round."""
        self.current_bet = 0
        self.has_acted = False
    
    def deal_hole_cards(self, cards: List[Card]):
        """Deal hole cards to the player."""
        self.hole_cards = cards
    
    def fold(self):
        """Player folds their hand."""
        self.is_active = False
        self.last_action = PlayerAction.FOLD
        self.has_acted = True
    
    def check(self):
        """Player checks (only valid if no bet to call)."""
        self.last_action = PlayerAction.CHECK
        self.has_acted = True
    
    def bet(self, amount: int) -> int:
        """
        Player bets an amount.
        Returns the actual amount bet (may be less if all-in).
        """
        if amount >= self.stack:
            # All-in
            actual_bet = self.stack
            self.stack = 0
            self.is_all_in = True
            self.last_action = PlayerAction.ALL_IN
        else:
            actual_bet = amount
            self.stack -= amount
            self.last_action = PlayerAction.BET
        
        self.current_bet += actual_bet
        self.total_bet += actual_bet
        self.has_acted = True
        return actual_bet
    
    def call(self, amount_to_call: int) -> int:
        """
        Player calls a bet.
        Returns the actual amount called (may be less if all-in).
        """
        if amount_to_call >= self.stack:
            # All-in
            actual_call = self.stack
            self.stack = 0
            self.is_all_in = True
            self.last_action = PlayerAction.ALL_IN
        else:
            actual_call = amount_to_call
            self.stack -= amount_to_call
            self.last_action = PlayerAction.CALL
        
        self.current_bet += actual_call
        self.total_bet += actual_call
        self.has_acted = True
        return actual_call
    
    def raise_bet(self, raise_amount: int, amount_to_call: int) -> int:
        """
        Player raises the bet.
        Returns the actual amount raised (may be less if all-in).
        """
        total_amount = amount_to_call + raise_amount
        
        if total_amount >= self.stack:
            # All-in
            actual_raise = self.stack
            self.stack = 0
            self.is_all_in = True
            self.last_action = PlayerAction.ALL_IN
        else:
            actual_raise = total_amount
            self.stack -= total_amount
            self.last_action = PlayerAction.RAISE
        
        self.current_bet += actual_raise
        self.total_bet += actual_raise
        self.has_acted = True
        return actual_raise
    
    def can_bet(self) -> bool:
        """Check if player can bet (has chips and is active)."""
        return self.is_active and not self.is_all_in and self.stack > 0
    
    def get_hole_cards_string(self) -> str:
        """Get a string representation of hole cards."""
        return " ".join(str(card) for card in self.hole_cards)
    
    def __repr__(self):
        return f"PokerPlayer({self.username}, stack={self.stack}, active={self.is_active})"
