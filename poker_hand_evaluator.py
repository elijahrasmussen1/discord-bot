"""
Poker Hand Evaluator Module
Evaluates poker hands and determines winners.
"""

from typing import List, Tuple, Optional
from poker_deck import Card
from collections import Counter


class HandRank:
    """Constants for hand rankings."""
    HIGH_CARD = 0
    PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8
    ROYAL_FLUSH = 9
    
    RANK_NAMES = {
        0: "High Card",
        1: "Pair",
        2: "Two Pair",
        3: "Three of a Kind",
        4: "Straight",
        5: "Flush",
        6: "Full House",
        7: "Four of a Kind",
        8: "Straight Flush",
        9: "Royal Flush"
    }


class HandEvaluator:
    """Evaluates poker hands and determines the best 5-card hand."""
    
    @staticmethod
    def evaluate_hand(cards: List[Card]) -> Tuple[int, List[int]]:
        """
        Evaluate a poker hand (5-7 cards) and return its rank and tiebreakers.
        Returns: (hand_rank, tiebreaker_values)
        """
        if len(cards) < 5:
            raise ValueError("Need at least 5 cards to evaluate a hand")
        
        # If we have more than 5 cards, find the best 5-card combination
        if len(cards) > 5:
            best_rank = -1
            best_tiebreakers = []
            
            # Generate all 5-card combinations
            from itertools import combinations
            for combo in combinations(cards, 5):
                rank, tiebreakers = HandEvaluator._evaluate_5_cards(list(combo))
                if rank > best_rank or (rank == best_rank and tiebreakers > best_tiebreakers):
                    best_rank = rank
                    best_tiebreakers = tiebreakers
            
            return best_rank, best_tiebreakers
        else:
            return HandEvaluator._evaluate_5_cards(cards)
    
    @staticmethod
    def _evaluate_5_cards(cards: List[Card]) -> Tuple[int, List[int]]:
        """Evaluate exactly 5 cards."""
        if len(cards) != 5:
            raise ValueError("Must evaluate exactly 5 cards")
        
        # Sort cards by value descending
        sorted_cards = sorted(cards, key=lambda c: c.value, reverse=True)
        values = [c.value for c in sorted_cards]
        suits = [c.suit for c in sorted_cards]
        
        # Check for flush
        is_flush = len(set(suits)) == 1
        
        # Check for straight
        is_straight, straight_high = HandEvaluator._is_straight(values)
        
        # Count occurrences of each rank
        value_counts = Counter(values)
        counts = sorted(value_counts.values(), reverse=True)
        unique_values = sorted(value_counts.keys(), key=lambda v: (value_counts[v], v), reverse=True)
        
        # Royal Flush
        if is_flush and is_straight and straight_high == 14:
            return HandRank.ROYAL_FLUSH, [14]
        
        # Straight Flush
        if is_flush and is_straight:
            return HandRank.STRAIGHT_FLUSH, [straight_high]
        
        # Four of a Kind
        if counts == [4, 1]:
            four_kind = [v for v, c in value_counts.items() if c == 4][0]
            kicker = [v for v, c in value_counts.items() if c == 1][0]
            return HandRank.FOUR_OF_A_KIND, [four_kind, kicker]
        
        # Full House
        if counts == [3, 2]:
            three_kind = [v for v, c in value_counts.items() if c == 3][0]
            pair = [v for v, c in value_counts.items() if c == 2][0]
            return HandRank.FULL_HOUSE, [three_kind, pair]
        
        # Flush
        if is_flush:
            return HandRank.FLUSH, sorted(values, reverse=True)
        
        # Straight
        if is_straight:
            return HandRank.STRAIGHT, [straight_high]
        
        # Three of a Kind
        if counts == [3, 1, 1]:
            three_kind = [v for v, c in value_counts.items() if c == 3][0]
            kickers = sorted([v for v, c in value_counts.items() if c == 1], reverse=True)
            return HandRank.THREE_OF_A_KIND, [three_kind] + kickers
        
        # Two Pair
        if counts == [2, 2, 1]:
            pairs = sorted([v for v, c in value_counts.items() if c == 2], reverse=True)
            kicker = [v for v, c in value_counts.items() if c == 1][0]
            return HandRank.TWO_PAIR, pairs + [kicker]
        
        # Pair
        if counts == [2, 1, 1, 1]:
            pair = [v for v, c in value_counts.items() if c == 2][0]
            kickers = sorted([v for v, c in value_counts.items() if c == 1], reverse=True)
            return HandRank.PAIR, [pair] + kickers
        
        # High Card
        return HandRank.HIGH_CARD, sorted(values, reverse=True)
    
    @staticmethod
    def _is_straight(values: List[int]) -> Tuple[bool, int]:
        """Check if values form a straight. Returns (is_straight, high_card)."""
        sorted_values = sorted(set(values), reverse=True)
        
        # Check for regular straight
        if len(sorted_values) == 5:
            if sorted_values[0] - sorted_values[4] == 4:
                return True, sorted_values[0]
        
        # Check for Ace-low straight (A-2-3-4-5)
        if sorted_values == [14, 5, 4, 3, 2]:
            return True, 5  # In ace-low straight, 5 is the high card
        
        return False, 0
    
    @staticmethod
    def compare_hands(hand1: Tuple[int, List[int]], hand2: Tuple[int, List[int]]) -> int:
        """
        Compare two hands.
        Returns: 1 if hand1 wins, -1 if hand2 wins, 0 if tie
        """
        rank1, tiebreakers1 = hand1
        rank2, tiebreakers2 = hand2
        
        if rank1 > rank2:
            return 1
        elif rank1 < rank2:
            return -1
        else:
            # Same rank, compare tiebreakers
            for t1, t2 in zip(tiebreakers1, tiebreakers2):
                if t1 > t2:
                    return 1
                elif t1 < t2:
                    return -1
            return 0
    
    @staticmethod
    def get_hand_description(hand_rank: int, tiebreakers: List[int]) -> str:
        """Get a human-readable description of the hand."""
        rank_name = HandRank.RANK_NAMES[hand_rank]
        
        if hand_rank == HandRank.ROYAL_FLUSH:
            return "Royal Flush"
        elif hand_rank == HandRank.STRAIGHT_FLUSH:
            return f"Straight Flush, {Card.RANKS[tiebreakers[0] - 2]} high"
        elif hand_rank == HandRank.FOUR_OF_A_KIND:
            return f"Four of a Kind, {Card.RANKS[tiebreakers[0] - 2]}s"
        elif hand_rank == HandRank.FULL_HOUSE:
            return f"Full House, {Card.RANKS[tiebreakers[0] - 2]}s full of {Card.RANKS[tiebreakers[1] - 2]}s"
        elif hand_rank == HandRank.FLUSH:
            return f"Flush, {Card.RANKS[tiebreakers[0] - 2]} high"
        elif hand_rank == HandRank.STRAIGHT:
            return f"Straight, {Card.RANKS[tiebreakers[0] - 2]} high"
        elif hand_rank == HandRank.THREE_OF_A_KIND:
            return f"Three of a Kind, {Card.RANKS[tiebreakers[0] - 2]}s"
        elif hand_rank == HandRank.TWO_PAIR:
            return f"Two Pair, {Card.RANKS[tiebreakers[0] - 2]}s and {Card.RANKS[tiebreakers[1] - 2]}s"
        elif hand_rank == HandRank.PAIR:
            return f"Pair of {Card.RANKS[tiebreakers[0] - 2]}s"
        else:
            return f"High Card, {Card.RANKS[tiebreakers[0] - 2]}"
