"""
Provably Fair Gambling System
------------------------------
Implements SHA256 HMAC-based provably fair system for gambling games.

System Overview:
- Uses server_seed (secret), client_seed (public), and nonce (counter)
- Server seed hash is published before any bets
- Results are deterministic based on HMAC-SHA256
- Seeds can be rotated and old seeds revealed for verification

Security:
- Admins cannot manipulate outcomes
- Players can verify all past bets
- Transparent and auditable
"""

import hashlib
import hmac
import secrets
import sqlite3
import time
from datetime import datetime

class ProvablyFairSystem:
    """
    Provably Fair System using HMAC-SHA256
    
    This system ensures that gambling outcomes are fair and verifiable.
    """
    
    def __init__(self, db_connection):
        """Initialize the provably fair system with database connection."""
        self.conn = db_connection
        self.c = db_connection.cursor()
        self._initialize_database()
    
    def _initialize_database(self):
        """Create necessary database tables for provably fair system."""
        
        # Table for storing active and historical server seeds
        self.c.execute("""
            CREATE TABLE IF NOT EXISTS provably_fair_seeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_seed TEXT NOT NULL,
                server_seed_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revealed_at TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Table for storing per-user client seeds and nonces
        self.c.execute("""
            CREATE TABLE IF NOT EXISTS provably_fair_users (
                user_id INTEGER PRIMARY KEY,
                client_seed TEXT NOT NULL,
                nonce INTEGER DEFAULT 0,
                last_updated TEXT NOT NULL
            )
        """)
        
        # Table for logging all bets for verification
        self.c.execute("""
            CREATE TABLE IF NOT EXISTS provably_fair_bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                game_type TEXT NOT NULL,
                server_seed_hash TEXT NOT NULL,
                client_seed TEXT NOT NULL,
                nonce INTEGER NOT NULL,
                result INTEGER NOT NULL,
                bet_amount INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        
        self.conn.commit()
    
    def generate_server_seed(self):
        """
        Generate a new cryptographically secure server seed.
        
        Returns:
            str: A 64-character hexadecimal server seed
        """
        return secrets.token_hex(32)  # 32 bytes = 64 hex characters
    
    def get_server_seed_hash(self, server_seed):
        """
        Generate SHA256 hash of the server seed.
        
        Args:
            server_seed (str): The server seed to hash
            
        Returns:
            str: SHA256 hash of the server seed
        """
        return hashlib.sha256(server_seed.encode()).hexdigest()
    
    def get_active_server_seed(self):
        """
        Get the current active server seed and its hash.
        
        Returns:
            tuple: (server_seed, server_seed_hash) or None if no active seed
        """
        self.c.execute("""
            SELECT server_seed, server_seed_hash 
            FROM provably_fair_seeds 
            WHERE is_active = 1 
            ORDER BY id DESC 
            LIMIT 1
        """)
        result = self.c.fetchone()
        return result if result else None
    
    def get_active_server_seed_hash(self):
        """
        Get only the hash of the active server seed (public information).
        
        Returns:
            str: The server seed hash or None
        """
        self.c.execute("""
            SELECT server_seed_hash 
            FROM provably_fair_seeds 
            WHERE is_active = 1 
            ORDER BY id DESC 
            LIMIT 1
        """)
        result = self.c.fetchone()
        return result[0] if result else None
    
    def initialize_system(self):
        """
        Initialize the provably fair system with a new server seed.
        Should be called on bot startup if no active seed exists.
        
        Returns:
            str: The hash of the newly created server seed
        """
        # Check if there's already an active seed
        existing = self.get_active_server_seed()
        if existing:
            return existing[1]  # Return existing hash
        
        # Generate new server seed
        server_seed = self.generate_server_seed()
        server_seed_hash = self.get_server_seed_hash(server_seed)
        created_at = datetime.utcnow().isoformat()
        
        # Store in database
        self.c.execute("""
            INSERT INTO provably_fair_seeds 
            (server_seed, server_seed_hash, created_at, is_active)
            VALUES (?, ?, ?, 1)
        """, (server_seed, server_seed_hash, created_at))
        
        self.conn.commit()
        
        return server_seed_hash
    
    def get_or_create_user_seeds(self, user_id):
        """
        Get user's client seed and nonce, creating them if they don't exist.
        
        Args:
            user_id (int): Discord user ID
            
        Returns:
            tuple: (client_seed, nonce)
        """
        self.c.execute("""
            SELECT client_seed, nonce 
            FROM provably_fair_users 
            WHERE user_id = ?
        """, (user_id,))
        
        result = self.c.fetchone()
        
        if result:
            return result
        
        # Create new client seed for user
        client_seed = secrets.token_hex(16)  # 16 bytes = 32 hex characters
        current_time = datetime.utcnow().isoformat()
        
        self.c.execute("""
            INSERT INTO provably_fair_users 
            (user_id, client_seed, nonce, last_updated)
            VALUES (?, ?, 0, ?)
        """, (user_id, client_seed, current_time))
        
        self.conn.commit()
        
        return (client_seed, 0)
    
    def increment_nonce(self, user_id):
        """
        Increment the user's nonce after a bet.
        
        Args:
            user_id (int): Discord user ID
            
        Returns:
            int: The new nonce value
        """
        current_time = datetime.utcnow().isoformat()
        
        self.c.execute("""
            UPDATE provably_fair_users 
            SET nonce = nonce + 1, last_updated = ?
            WHERE user_id = ?
        """, (current_time, user_id))
        
        self.conn.commit()
        
        # Get the new nonce
        self.c.execute("SELECT nonce FROM provably_fair_users WHERE user_id = ?", (user_id,))
        result = self.c.fetchone()
        return result[0] if result else 0
    
    def set_client_seed(self, user_id, new_client_seed):
        """
        Allow user to set their own client seed.
        
        Args:
            user_id (int): Discord user ID
            new_client_seed (str): The new client seed (must be valid hex string)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Validate that it's a valid hex string
            int(new_client_seed, 16)
            
            current_time = datetime.utcnow().isoformat()
            
            # Ensure user exists first
            self.get_or_create_user_seeds(user_id)
            
            self.c.execute("""
                UPDATE provably_fair_users 
                SET client_seed = ?, last_updated = ?
                WHERE user_id = ?
            """, (new_client_seed, current_time, user_id))
            
            self.conn.commit()
            return True
        except ValueError:
            return False
    
    def generate_result(self, server_seed, client_seed, nonce, modulo):
        """
        Generate a provably fair result using HMAC-SHA256.
        
        Algorithm:
        1. Create message: "{client_seed}:{nonce}"
        2. HMAC-SHA256(server_seed, message)
        3. Take first 8 hex characters
        4. Convert to integer
        5. Apply modulo
        
        Args:
            server_seed (str): The server seed (secret)
            client_seed (str): The client seed (public)
            nonce (int): The nonce (counter)
            modulo (int): The modulo to apply (e.g., 2 for coinflip)
            
        Returns:
            int: The result (0 to modulo-1)
        """
        # Create the message
        message = f"{client_seed}:{nonce}"
        
        # Generate HMAC-SHA256
        hmac_hash = hmac.new(
            server_seed.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Take first 8 hex characters
        hex_slice = hmac_hash[:8]
        
        # Convert to integer
        result_int = int(hex_slice, 16)
        
        # Apply modulo
        result = result_int % modulo
        
        return result
    
    def generate_multiple_results(self, server_seed, client_seed, nonce, count, modulo):
        """
        Generate multiple provably fair results from a single nonce.
        Uses different segments of the HMAC hash for each result.
        
        Args:
            server_seed (str): The server seed (secret)
            client_seed (str): The client seed (public)
            nonce (int): The nonce (counter)
            count (int): Number of results to generate
            modulo (int): The modulo to apply
            
        Returns:
            list: List of results
        """
        # Create the message
        message = f"{client_seed}:{nonce}"
        
        # Generate HMAC-SHA256
        hmac_hash = hmac.new(
            server_seed.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        results = []
        # Use different 8-character segments for each result
        for i in range(count):
            # Calculate offset (wrap around if needed)
            offset = (i * 8) % (len(hmac_hash) - 8)
            hex_slice = hmac_hash[offset:offset+8]
            
            # Convert to integer and apply modulo
            result_int = int(hex_slice, 16)
            result = result_int % modulo
            results.append(result)
        
        return results
    
    def place_bet(self, user_id, game_type, bet_amount, modulo):
        """
        Place a bet and generate a provably fair result.
        
        Args:
            user_id (int): Discord user ID
            game_type (str): Type of game (e.g., "coinflip", "dice")
            bet_amount (int): Amount being bet
            modulo (int): The modulo for the game
            
        Returns:
            tuple: (result, client_seed, nonce, server_seed_hash)
        """
        # Get active server seed
        server_seed_data = self.get_active_server_seed()
        if not server_seed_data:
            raise Exception("No active server seed! System not initialized.")
        
        server_seed, server_seed_hash = server_seed_data
        
        # Get or create user seeds
        client_seed, current_nonce = self.get_or_create_user_seeds(user_id)
        
        # Generate result
        result = self.generate_result(server_seed, client_seed, current_nonce, modulo)
        
        # Log the bet
        timestamp = datetime.utcnow().isoformat()
        self.c.execute("""
            INSERT INTO provably_fair_bets
            (user_id, game_type, server_seed_hash, client_seed, nonce, result, bet_amount, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, game_type, server_seed_hash, client_seed, current_nonce, result, bet_amount, timestamp))
        
        self.conn.commit()
        
        # Increment nonce for next bet
        self.increment_nonce(user_id)
        
        return (result, client_seed, current_nonce, server_seed_hash)
    
    def place_bet_multiple(self, user_id, game_type, bet_amount, count, modulo):
        """
        Place a bet and generate multiple provably fair results.
        Used for games like slots (9 symbols) or blackjack (card draws).
        
        Args:
            user_id (int): Discord user ID
            game_type (str): Type of game (e.g., "slots", "blackjack")
            bet_amount (int): Amount being bet
            count (int): Number of results to generate
            modulo (int): The modulo for the game
            
        Returns:
            tuple: (results_list, client_seed, nonce, server_seed_hash)
        """
        # Get active server seed
        server_seed_data = self.get_active_server_seed()
        if not server_seed_data:
            raise Exception("No active server seed! System not initialized.")
        
        server_seed, server_seed_hash = server_seed_data
        
        # Get or create user seeds
        client_seed, current_nonce = self.get_or_create_user_seeds(user_id)
        
        # Generate multiple results
        results = self.generate_multiple_results(server_seed, client_seed, current_nonce, count, modulo)
        
        # Log the bet (store results as comma-separated string)
        timestamp = datetime.utcnow().isoformat()
        results_str = ','.join(map(str, results))
        self.c.execute("""
            INSERT INTO provably_fair_bets
            (user_id, game_type, server_seed_hash, client_seed, nonce, result, bet_amount, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, game_type, server_seed_hash, client_seed, current_nonce, results_str, bet_amount, timestamp))
        
        self.conn.commit()
        
        # Increment nonce for next bet
        self.increment_nonce(user_id)
        
        return (results, client_seed, current_nonce, server_seed_hash)
    
    def verify_bet(self, server_seed, client_seed, nonce, expected_result, modulo):
        """
        Verify that a bet result is correct.
        
        Args:
            server_seed (str): The revealed server seed
            client_seed (str): The client seed used
            nonce (int): The nonce used
            expected_result (int): The expected result
            modulo (int): The modulo used
            
        Returns:
            bool: True if result matches, False otherwise
        """
        actual_result = self.generate_result(server_seed, client_seed, nonce, modulo)
        return actual_result == expected_result
    
    def rotate_server_seed(self):
        """
        Rotate the server seed (reveal old one and generate new one).
        
        Returns:
            tuple: (old_server_seed, new_server_seed_hash)
        """
        # Get current active seed
        current_seed_data = self.get_active_server_seed()
        if not current_seed_data:
            raise Exception("No active server seed to rotate!")
        
        old_server_seed, old_hash = current_seed_data
        
        # Mark current seed as inactive and set revealed_at
        revealed_at = datetime.utcnow().isoformat()
        self.c.execute("""
            UPDATE provably_fair_seeds 
            SET is_active = 0, revealed_at = ?
            WHERE server_seed_hash = ? AND is_active = 1
        """, (revealed_at, old_hash))
        
        # Generate new server seed
        new_server_seed = self.generate_server_seed()
        new_server_seed_hash = self.get_server_seed_hash(new_server_seed)
        created_at = datetime.utcnow().isoformat()
        
        # Store new seed
        self.c.execute("""
            INSERT INTO provably_fair_seeds 
            (server_seed, server_seed_hash, created_at, is_active)
            VALUES (?, ?, ?, 1)
        """, (new_server_seed, new_server_seed_hash, created_at))
        
        self.conn.commit()
        
        return (old_server_seed, new_server_seed_hash)
    
    def get_revealed_seeds(self, limit=10):
        """
        Get list of revealed server seeds.
        
        Args:
            limit (int): Maximum number of seeds to return
            
        Returns:
            list: List of tuples (server_seed, server_seed_hash, revealed_at)
        """
        self.c.execute("""
            SELECT server_seed, server_seed_hash, revealed_at
            FROM provably_fair_seeds
            WHERE is_active = 0 AND revealed_at IS NOT NULL
            ORDER BY revealed_at DESC
            LIMIT ?
        """, (limit,))
        
        return self.c.fetchall()
    
    def get_user_bet_history(self, user_id, limit=10):
        """
        Get user's betting history for verification.
        
        Args:
            user_id (int): Discord user ID
            limit (int): Maximum number of bets to return
            
        Returns:
            list: List of bet records
        """
        self.c.execute("""
            SELECT id, game_type, server_seed_hash, client_seed, nonce, result, bet_amount, timestamp
            FROM provably_fair_bets
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit))
        
        return self.c.fetchall()
    
    def get_system_stats(self):
        """
        Get statistics about the provably fair system.
        
        Returns:
            dict: System statistics
        """
        # Get active seed info
        self.c.execute("""
            SELECT server_seed_hash, created_at
            FROM provably_fair_seeds
            WHERE is_active = 1
            LIMIT 1
        """)
        active_seed = self.c.fetchone()
        
        # Get total bets
        self.c.execute("SELECT COUNT(*) FROM provably_fair_bets")
        total_bets = self.c.fetchone()[0]
        
        # Get total users
        self.c.execute("SELECT COUNT(*) FROM provably_fair_users")
        total_users = self.c.fetchone()[0]
        
        # Get total rotations
        self.c.execute("SELECT COUNT(*) FROM provably_fair_seeds WHERE is_active = 0")
        total_rotations = self.c.fetchone()[0]
        
        return {
            'active_seed_hash': active_seed[0] if active_seed else None,
            'active_since': active_seed[1] if active_seed else None,
            'total_bets': total_bets,
            'total_users': total_users,
            'total_rotations': total_rotations
        }
