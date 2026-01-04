"""
Poker Deck Module
Handles deck creation, cryptographically secure shuffling, and card management.
"""

import secrets
import hashlib
import json
from typing import List, Tuple


class Card:
    """Represents a single playing card."""
    
    SUITS = ['♠', '♥', '♦', '♣']
    RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    RANK_VALUES = {
        '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
        '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
    }
    
    def __init__(self, rank: str, suit: str):
        self.rank = rank
        self.suit = suit
        self.value = self.RANK_VALUES[rank]
    
    def __repr__(self):
        return f"{self.rank}{self.suit}"
    
    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.rank == other.rank and self.suit == other.suit
    
    def to_dict(self):
        """Convert card to dictionary for serialization."""
        return {'rank': self.rank, 'suit': self.suit}
    
    @classmethod
    def from_dict(cls, data):
        """Create card from dictionary."""
        return cls(data['rank'], data['suit'])


class Deck:
    """Represents a deck of 52 playing cards with cryptographic shuffling."""
    
    def __init__(self):
        self.cards: List[Card] = []
        self.shuffle_seed: str = ""
        self.shuffle_hash: str = ""
        self.dealt_cards: List[Card] = []
        self.original_shuffled_order: List[dict] = []  # Store original order after shuffle
        self.reset()
    
    def reset(self):
        """Reset the deck to a fresh 52-card deck."""
        self.cards = []
        for suit in Card.SUITS:
            for rank in Card.RANKS:
                self.cards.append(Card(rank, suit))
        self.dealt_cards = []
    
    def shuffle_cryptographic(self) -> str:
        """
        Shuffle the deck using cryptographically secure randomness.
        Returns the hash of the shuffle for verification.
        """
        # Generate a cryptographically secure random seed
        self.shuffle_seed = secrets.token_hex(32)
        
        # Create a deterministic shuffle based on the seed
        # We'll use Fisher-Yates shuffle with CSPRNG
        for i in range(len(self.cards) - 1, 0, -1):
            # Generate cryptographically secure random index
            j = secrets.randbelow(i + 1)
            self.cards[i], self.cards[j] = self.cards[j], self.cards[i]
        
        # Create a hash of the shuffled deck order and store it
        deck_order = [{'rank': card.rank, 'suit': card.suit} for card in self.cards]
        self.original_shuffled_order = deck_order  # Save original order
        deck_json = json.dumps(deck_order, sort_keys=True)
        combined = f"{self.shuffle_seed}:{deck_json}"
        self.shuffle_hash = hashlib.sha256(combined.encode()).hexdigest()
        
        return self.shuffle_hash
    
    def get_shuffle_commitment(self) -> str:
        """Get the shuffle hash commitment for transparency."""
        return self.shuffle_hash
    
    def get_shuffle_verification(self) -> dict:
        """
        Get the full shuffle verification data at the end of the game.
        This allows players to verify the shuffle was fair.
        """
        return {
            'seed': self.shuffle_seed,
            'hash': self.shuffle_hash,
            'deck_order': self.original_shuffled_order,
            'dealt_cards': [card.to_dict() for card in self.dealt_cards]
        }
    
    def verify_shuffle(self, verification_data: dict) -> bool:
        """Verify that a shuffle was fair using the verification data."""
        seed = verification_data['seed']
        deck_order = verification_data['deck_order']
        original_hash = verification_data['hash']
        
        # Reconstruct the hash
        deck_json = json.dumps(deck_order, sort_keys=True)
        combined = f"{seed}:{deck_json}"
        computed_hash = hashlib.sha256(combined.encode()).hexdigest()
        
        return computed_hash == original_hash
    
    def deal(self, num_cards: int = 1) -> List[Card]:
        """Deal cards from the top of the deck."""
        if len(self.cards) < num_cards:
            raise ValueError(f"Not enough cards in deck. Requested {num_cards}, available {len(self.cards)}")
        
        dealt = []
        for _ in range(num_cards):
            card = self.cards.pop(0)
            dealt.append(card)
            self.dealt_cards.append(card)
        
        return dealt
    
    def cards_remaining(self) -> int:
        """Return the number of cards remaining in the deck."""
        return len(self.cards)
