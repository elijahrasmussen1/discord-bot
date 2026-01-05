import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import sqlite3
import random
import os
import asyncio
from datetime import datetime, timedelta

# -----------------------------
# INTENTS
# -----------------------------
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# CONFIG
# -----------------------------
OWNER_IDS = [1182265710248996874, 1249352131870195744, 1250923685443797035]
TICKET_CATEGORY_ID = 1442410056019742750
TRANSCRIPT_CHANNEL_ID = 1442288590611681401
WITHDRAWAL_LOG_CHANNEL = 1450656547402285167
AUDIT_LOG_CHANNEL = 1451387246061293662  # Channel for fraud detection and activity logs
DEPOSIT_STATS_CHANNEL = 1452401825994248212  # Channel for 15-minute deposit statistics
STOCK_CHANNEL = 1452562733080776835  # Channel for brainrot pet stock/inventory
PING_ROLES = [1442285602166018069, 1442993726057087089]
MIN_DEPOSIT = 10_000_000
GAMBLE_PERCENT = 0.30
USERS_PER_PAGE = 5
GUILD_ID = 1442270020959867162

# Anti-fraud thresholds
SUSPICIOUS_WITHDRAWAL_THRESHOLD = 100_000_000  # 100M+ withdrawals are flagged
RAPID_BET_THRESHOLD = 5  # More than 5 bets in 60 seconds is suspicious
HIGH_BET_THRESHOLD = 50_000_000  # 50M+ bets are logged

# Stick message tracking
stick_messages = {}  # {channel_id: {"message_id": int, "content": str, "last_update": datetime}}

# -----------------------------
# DATABASE
# -----------------------------
conn = sqlite3.connect("bot.db")
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
c.execute("""
CREATE TABLE IF NOT EXISTS tickets (
    user_id INTEGER,
    ticket_number INTEGER
)
""")

# Ticket metadata for close command
c.execute("""
CREATE TABLE IF NOT EXISTS ticket_metadata (
    channel_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    panel_name TEXT NOT NULL,
    ticket_name TEXT NOT NULL,
    open_date TEXT NOT NULL
)
""")

# Transaction audit log table
c.execute("""
CREATE TABLE IF NOT EXISTS transaction_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    transaction_type TEXT NOT NULL,
    amount INTEGER NOT NULL,
    balance_before INTEGER,
    balance_after INTEGER,
    timestamp TEXT NOT NULL,
    details TEXT
)
""")

# Bet activity tracking for rapid betting detection
c.execute("""
CREATE TABLE IF NOT EXISTS bet_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    bet_amount INTEGER NOT NULL,
    game_type TEXT NOT NULL,
    result TEXT,
    timestamp TEXT NOT NULL
)
""")

# Stock/Inventory system for brainrot pets
c.execute("""
CREATE TABLE IF NOT EXISTS stock_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_name TEXT NOT NULL,
    mutation TEXT NOT NULL,
    trait TEXT NOT NULL,
    price INTEGER NOT NULL,
    stock_amount INTEGER NOT NULL,
    account_stored TEXT NOT NULL,
    image_url TEXT,
    date_added TEXT NOT NULL
)
""")

# Stock Market System
c.execute("""
CREATE TABLE IF NOT EXISTS stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    base_price REAL NOT NULL,
    current_price REAL NOT NULL,
    total_shares INTEGER DEFAULT 1000000,
    available_shares INTEGER DEFAULT 1000000
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS stock_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id INTEGER NOT NULL,
    price REAL NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (stock_id) REFERENCES stocks (id)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    stock_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    avg_purchase_price REAL NOT NULL,
    UNIQUE(user_id, stock_id),
    FOREIGN KEY (stock_id) REFERENCES stocks (id)
)
""")

# Spin Wheel system tables
c.execute("""
CREATE TABLE IF NOT EXISTS spin_wheel_data (
    user_id INTEGER PRIMARY KEY,
    free_spins INTEGER DEFAULT 0,
    purchased_spins INTEGER DEFAULT 0,
    last_spin_time TEXT,
    total_spins_used INTEGER DEFAULT 0,
    total_winnings INTEGER DEFAULT 0,
    daily_purchased INTEGER DEFAULT 0,
    last_purchase_date TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS spin_wheel_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    prize_type TEXT NOT NULL,
    prize_value TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    spin_type TEXT NOT NULL
)
""")

# Add migration for daily_purchased and last_purchase_date columns if they don't exist
try:
    c.execute("ALTER TABLE spin_wheel_data ADD COLUMN daily_purchased INTEGER DEFAULT 0")
except:
    pass  # Column already exists

try:
    c.execute("ALTER TABLE spin_wheel_data ADD COLUMN last_purchase_date TEXT")
except:
    pass  # Column already exists

conn.commit()

# Database migration: Add missing columns if they don't exist
try:
    # Check if total_gambled and total_withdrawn columns exist
    c.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in c.fetchall()]
    
    if 'total_gambled' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN total_gambled INTEGER DEFAULT 0")
        print("✅ Added total_gambled column to users table")
    
    if 'total_withdrawn' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN total_withdrawn INTEGER DEFAULT 0")
        print("✅ Added total_withdrawn column to users table")
    
    if 'favorite_game' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN favorite_game TEXT DEFAULT 'Not Set'")
        print("✅ Added favorite_game column to users table")
    
    conn.commit()
except Exception as e:
    print(f"⚠️ Database migration error (non-fatal): {e}")

# -----------------------------
# PROVABLY FAIR SYSTEM
# -----------------------------
from provably_fair import ProvablyFairSystem

# Initialize provably fair system
provably_fair = ProvablyFairSystem(conn)
print("🎲 Initializing provably fair system...")
active_seed_hash = provably_fair.initialize_system()
print(f"✅ Provably fair system initialized")
print(f"   Active Server Seed Hash: {active_seed_hash[:32]}...")

# -----------------------------
# STOCK MARKET INITIALIZATION
# -----------------------------
def initialize_stock_market():
    """Initialize stock market with default stocks if not exists."""
    try:
        c.execute("SELECT COUNT(*) FROM stocks")
        count = c.fetchone()[0]
        
        if count == 0:
            # Initial stock list with diverse categories
            initial_stocks = [
                # Technology Stocks
                ("TECH", "TechCorp", "Technology", 100.0),
                ("BYTE", "ByteWorks", "Technology", 75.0),
                ("DIGI", "DigiSoft", "Technology", 120.0),
                ("CODE", "CodeLabs", "Technology", 95.0),
                
                # Food & Agriculture
                ("FOOD", "FoodCo", "Food", 50.0),
                ("FARM", "FarmFresh", "Food", 40.0),
                ("MEAL", "MealMasters", "Food", 60.0),
                
                # Energy
                ("VOLT", "VoltEnergy", "Energy", 110.0),
                ("FUEL", "FuelMax", "Energy", 85.0),
                ("SOLAR", "SolarPower", "Energy", 130.0),
                
                # Healthcare
                ("MEDIC", "MediCare", "Healthcare", 150.0),
                ("HEAL", "HealWell", "Healthcare", 125.0),
                ("CURE", "CureTech", "Healthcare", 140.0),
                
                # Finance
                ("BANK", "BankCorp", "Finance", 90.0),
                ("COIN", "CoinTrade", "Finance", 105.0),
                ("INVEST", "InvestPro", "Finance", 115.0),
                
                # Entertainment
                ("PLAY", "PlayTime", "Entertainment", 70.0),
                ("GAME", "GameZone", "Entertainment", 80.0),
                ("STREAM", "StreamHub", "Entertainment", 95.0),
                
                # Transportation
                ("RIDE", "RideShare", "Transportation", 65.0),
                ("CARGO", "CargoMax", "Transportation", 55.0),
                ("FLY", "FlyHigh", "Transportation", 100.0),
            ]
            
            for ticker, name, category, base_price in initial_stocks:
                c.execute("""
                    INSERT INTO stocks (ticker, name, category, base_price, current_price)
                    VALUES (?, ?, ?, ?, ?)
                """, (ticker, name, category, base_price, base_price))
                
                # Record initial price
                stock_id = c.lastrowid
                c.execute("""
                    INSERT INTO stock_prices (stock_id, price)
                    VALUES (?, ?)
                """, (stock_id, base_price))
            
            conn.commit()
            print(f"✅ Initialized stock market with {len(initial_stocks)} stocks")
        else:
            print(f"✅ Stock market already initialized with {count} stocks")
    except Exception as e:
        print(f"❌ Error initializing stock market: {e}")

# Initialize stock market on startup
initialize_stock_market()

# Global variables for stock market
donation_cooldowns = {}  # {user_id: expiry_timestamp}
stock_market_cache = {}  # Cache for stock data to reduce DB queries

# Global variables for spin wheel
spin_wheel_active = False  # Tracks if wheel has been activated by owner
current_special_prize = None  # {pet_id: int, pet_name: str} for 0.5% stock pet prize

# -----------------------------
# HELPERS
# -----------------------------
def parse_money(value: str) -> int:
    """Parse money string and return integer value. Returns -1 if invalid."""
    try:
        # Input validation and sanitization
        if not isinstance(value, str):
            return -1
        
        value = value.lower().strip().replace(",", "")
        
        # Check for empty string
        if not value:
            return -1
        
        if value.endswith("m"):
            num = float(value[:-1])
            return int(num * 1_000_000)
        elif value.endswith("b"):
            num = float(value[:-1])
            return int(num * 1_000_000_000)
        elif value.endswith("k"):
            num = float(value[:-1])
            return int(num * 1_000)
        else:
            # Try to parse as plain integer
            return int(value)
    except (ValueError, AttributeError):
        return -1

def format_money(value: int) -> str:
    """Format integer money value with commas and $ sign."""
    return f"{value:,}$"

def is_owner(user):
    return user.id in OWNER_IDS

def calculate_total_pages(total_items, items_per_page):
    """Calculate total number of pages for pagination."""
    import math
    return max(1, math.ceil(total_items / items_per_page))

def get_user(user_id):
    """Get user from database, creating entry if needed. Returns tuple of user data."""
    # Input validation
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid user_id: {user_id}")
    
    # Use loop instead of recursion to prevent stack overflow
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        # Fetch the newly created row
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    return row

def get_balance(user_id):
    """Get user's current balance."""
    user_id_db, bal, req, gambled, total_gambled, total_withdrawn, favorite_game = get_user(user_id)
    return bal

def update_balance(user_id, amount):
    """Update user balance by adding amount. Validates inputs."""
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid amount: {amount}")
    
    user_id_db, bal, req, gambled, total_gambled, total_withdrawn, _ = get_user(user_id)
    new_bal = bal + amount
    new_req = int(new_bal * GAMBLE_PERCENT)
    c.execute(
        "UPDATE users SET balance=?, required_gamble=? WHERE user_id=?",
        (new_bal, new_req, user_id_db)
    )
    conn.commit()

def set_balance(user_id, new_balance):
    """Set user balance to a specific amount. Validates inputs."""
    try:
        new_balance = int(new_balance)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid balance: {new_balance}")
    
    user_id_db, _, _, _, _, _, _ = get_user(user_id)
    new_req = int(new_balance * GAMBLE_PERCENT)
    c.execute(
        "UPDATE users SET balance=?, required_gamble=? WHERE user_id=?",
        (new_balance, new_req, user_id_db)
    )
    conn.commit()

def add_gambled(user_id, amount):
    """Add gambled amount to user's gamble stats. Validates inputs."""
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid amount: {amount}")
    
    user_id_db, bal, req, gambled, total_gambled, total_withdrawn, _ = get_user(user_id)
    new_gambled = gambled + amount
    new_total_gambled = total_gambled + amount
    c.execute(
        "UPDATE users SET gambled=?, total_gambled=? WHERE user_id=?",
        (new_gambled, new_total_gambled, user_id_db)
    )
    conn.commit()

def withdraw_balance(user_id, amount):
    """Withdraw balance from user account. Validates inputs."""
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid amount: {amount}")
    
    user_id_db, bal, req, gambled, total_gambled, total_withdrawn, _ = get_user(user_id)
    new_bal = bal - amount
    new_req = int(new_bal * GAMBLE_PERCENT)
    new_total_withdrawn = total_withdrawn + amount
    c.execute(
        "UPDATE users SET balance=?, required_gamble=?, gambled=0, total_withdrawn=? WHERE user_id=?",
        (new_bal, new_req, new_total_withdrawn, user_id_db)
    )
    conn.commit()

def get_favorite_game(user_id):
    """Get user's favorite game."""
    c.execute("SELECT favorite_game FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    if result:
        return result[0] if result[0] else "Not Set"
    return "Not Set"

def set_favorite_game(user_id, game_name):
    """Set user's favorite game."""
    # Ensure user exists
    get_user(user_id)
    # Update favorite game
    c.execute("UPDATE users SET favorite_game=? WHERE user_id=?", (game_name, user_id))
    conn.commit()

# -----------------------------
# STOCK MARKET HELPERS
# -----------------------------
def get_stock_by_ticker(ticker):
    """Get stock data by ticker symbol."""
    c.execute("SELECT * FROM stocks WHERE ticker=?", (ticker.upper(),))
    return c.fetchone()

def get_all_stocks():
    """Get all stocks from database."""
    c.execute("SELECT * FROM stocks ORDER BY category, ticker")
    return c.fetchall()

def get_user_holdings(user_id):
    """Get all stock holdings for a user."""
    c.execute("""
        SELECT h.*, s.ticker, s.name, s.current_price, s.category
        FROM holdings h
        JOIN stocks s ON h.stock_id = s.id
        WHERE h.user_id = ?
        ORDER BY s.ticker
    """, (user_id,))
    return c.fetchall()

def calculate_portfolio_value(user_id):
    """Calculate total value of user's stock portfolio."""
    holdings = get_user_holdings(user_id)
    total_value = sum(h[3] * h[6] for h in holdings)  # quantity * current_price
    return int(total_value)

def update_stock_price(stock_id, new_price):
    """Update stock price and log the change."""
    c.execute("UPDATE stocks SET current_price=? WHERE id=?", (new_price, stock_id))
    c.execute("INSERT INTO stock_prices (stock_id, price) VALUES (?, ?)", (stock_id, new_price))
    conn.commit()

def apply_demand_price_change(stock_id, is_buy):
    """Apply price change based on buy/sell demand."""
    c.execute("SELECT current_price FROM stocks WHERE id=?", (stock_id,))
    current_price = c.fetchone()[0]
    
    # Buy increases price by 0.5%, Sell decreases by 0.5%
    change_percent = 0.005 if is_buy else -0.005
    new_price = current_price * (1 + change_percent)
    
    # Ensure price doesn't go below 1.0
    new_price = max(1.0, new_price)
    
    update_stock_price(stock_id, new_price)
    return new_price

def calculate_random_price_change(base_price, current_price, category):
    """Calculate random price change based on category volatility."""
    # Different categories have different volatility ranges
    volatility_ranges = {
        "Technology": (0.08, 0.15),      # 8-15% volatility
        "Food": (0.03, 0.08),            # 3-8% volatility
        "Energy": (0.06, 0.12),          # 6-12% volatility
        "Healthcare": (0.04, 0.10),      # 4-10% volatility
        "Finance": (0.05, 0.12),         # 5-12% volatility
        "Entertainment": (0.07, 0.14),   # 7-14% volatility
        "Transportation": (0.05, 0.11),  # 5-11% volatility
    }
    
    min_vol, max_vol = volatility_ranges.get(category, (0.05, 0.10))
    
    # Random change within volatility range
    change_percent = random.uniform(-max_vol, max_vol)
    new_price = current_price * (1 + change_percent)
    
    # Apply mean reversion - prices tend to return toward base price
    # If price is far from base, apply slight correction
    deviation = (current_price - base_price) / base_price
    if abs(deviation) > 0.5:  # More than 50% away from base
        reversion_factor = -deviation * 0.05  # 5% reversion
        new_price = new_price * (1 + reversion_factor)
    
    # Ensure price doesn't go below 10% of base price or above 500% of base price
    min_price = base_price * 0.1
    max_price = base_price * 5.0
    new_price = max(min_price, min(max_price, new_price))
    
    return new_price

# -----------------------------
# ANTI-FRAUD & AUDIT LOGGING
# -----------------------------
async def log_transaction(user_id, transaction_type, amount, balance_before, balance_after, details=""):
    """Log all transactions to database for audit trail."""
    try:
        timestamp = datetime.now().isoformat()
        c.execute(
            "INSERT INTO transaction_logs (user_id, transaction_type, amount, balance_before, balance_after, timestamp, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, transaction_type, amount, balance_before, balance_after, timestamp, details)
        )
        conn.commit()
    except Exception as e:
        print(f"⚠️ Transaction logging error: {e}")

async def log_bet_activity(user_id, bet_amount, game_type, result):
    """Track betting activity for fraud detection."""
    try:
        timestamp = datetime.now().isoformat()
        c.execute(
            "INSERT INTO bet_activity (user_id, bet_amount, game_type, result, timestamp) VALUES (?, ?, ?, ?, ?)",
            (user_id, bet_amount, game_type, result, timestamp)
        )
        conn.commit()
    except Exception as e:
        print(f"⚠️ Bet activity logging error: {e}")

async def check_rapid_betting(user_id):
    """Check if user is betting too rapidly (potential bot/exploit)."""
    try:
        # Check bets in last 60 seconds
        one_minute_ago = (datetime.now() - timedelta(seconds=60)).isoformat()
        c.execute(
            "SELECT COUNT(*) FROM bet_activity WHERE user_id=? AND timestamp > ?",
            (user_id, one_minute_ago)
        )
        bet_count = c.fetchone()[0]
        return bet_count >= RAPID_BET_THRESHOLD
    except Exception as e:
        print(f"⚠️ Rapid betting check error: {e}")
        return False

async def send_fraud_alert(bot, user, alert_type, details):
    """Send fraud alert to audit log channel."""
    try:
        audit_channel = bot.get_channel(AUDIT_LOG_CHANNEL)
        if not audit_channel:
            print(f"⚠️ Audit log channel {AUDIT_LOG_CHANNEL} not found")
            return
        
        embed = discord.Embed(
            title=f"🚨 Suspicious Activity Detected",
            description=f"**User:** {user.mention} ({user.id})\n**Alert Type:** {alert_type}",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Details", value=details, inline=False)
        embed.set_footer(text="Anti-Fraud System")
        
        await audit_channel.send(embed=embed)
    except Exception as e:
        print(f"⚠️ Fraud alert error: {e}")

async def log_user_activity(bot, user, activity_type, details):
    """Log important user activities to audit channel."""
    try:
        audit_channel = bot.get_channel(AUDIT_LOG_CHANNEL)
        if not audit_channel:
            return
        
        embed = discord.Embed(
            title=f"📋 User Activity Log",
            description=f"**User:** {user.mention} ({user.id})\n**Activity:** {activity_type}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Details", value=details, inline=False)
        
        await audit_channel.send(embed=embed)
    except Exception as e:
        print(f"⚠️ Activity logging error: {e}")

# -----------------------------
# WITHDRAWAL CONFIRMATION VIEW
# -----------------------------
class WithdrawalConfirmView(View):
    def __init__(self, user, amount, channel):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user = user
        self.amount = amount
        self.channel = channel
        self.confirmed = False
    
    @discord.ui.button(label="✅ Confirm Withdrawal", style=discord.ButtonStyle.green, custom_id="confirm_withdrawal")
    async def confirm_withdrawal(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in OWNER_IDS:
            await interaction.response.send_message("❌ Only owners can confirm withdrawals.", ephemeral=True)
            return
        
        try:
            # Get balance before withdrawal for logging
            user_id, bal_before, req, gambled, total_gambled, total_withdrawn, _ = get_user(self.user.id)
            
            # Check for suspicious activity
            if self.amount >= SUSPICIOUS_WITHDRAWAL_THRESHOLD:
                await send_fraud_alert(
                    interaction.client,
                    self.user,
                    "High Value Withdrawal",
                    f"Amount: {self.amount:,}$\nApproved by: {interaction.user.mention}"
                )
            
            # Process the withdrawal
            withdraw_balance(self.user.id, self.amount)
            
            # Log transaction to database
            await log_transaction(
                self.user.id,
                "WITHDRAWAL",
                self.amount,
                bal_before,
                bal_before - self.amount,
                f"Approved by {interaction.user.name} ({interaction.user.id})"
            )
            
            # Log to audit channel
            await log_user_activity(
                interaction.client,
                self.user,
                "Withdrawal Approved",
                f"Amount: {self.amount:,}$\nApproved by: {interaction.user.mention}\nPrevious Balance: {bal_before:,}$\nNew Balance: {bal_before - self.amount:,}$"
            )
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            # Update the original message
            embed = discord.Embed(
                title="✅ Withdrawal Approved",
                description=f"{self.user.mention} withdrew {self.amount:,}$ SAB currency.",
                color=discord.Color.green()
            )
            embed.add_field(name="Approved By", value=interaction.user.mention)
            await interaction.response.edit_message(embed=embed, view=self)
            
            # Notify user
            await self.channel.send(f"✅ {self.user.mention} Your withdrawal of {self.amount:,}$ has been approved!")
            
            # Log the withdrawal
            log_channel = interaction.client.get_channel(WITHDRAWAL_LOG_CHANNEL)
            if log_channel:
                await log_channel.send(f"💸 {self.user} withdrew {self.amount:,}$ SAB currency. Approved by {interaction.user}.")
            
            self.confirmed = True
            self.stop()
        except Exception as e:
            await interaction.response.send_message(f"❌ Error processing withdrawal: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="❌ Decline Withdrawal", style=discord.ButtonStyle.red, custom_id="decline_withdrawal")
    async def decline_withdrawal(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in OWNER_IDS:
            await interaction.response.send_message("❌ Only owners can decline withdrawals.", ephemeral=True)
            return
        
        try:
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            # Update the original message
            embed = discord.Embed(
                title="❌ Withdrawal Declined",
                description=f"Withdrawal request from {self.user.mention} has been declined.",
                color=discord.Color.red()
            )
            embed.add_field(name="Declined By", value=interaction.user.mention)
            await interaction.response.edit_message(embed=embed, view=self)
            
            # Notify user
            await self.channel.send(f"❌ {self.user.mention} Your withdrawal request has been declined.")
            
            self.stop()
        except Exception as e:
            await interaction.response.send_message(f"❌ Error declining withdrawal: {str(e)}", ephemeral=True)
    
    async def on_timeout(self):
        """Called when the view times out."""
        try:
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            embed = discord.Embed(
                title="⏱️ Withdrawal Request Expired",
                description=f"Withdrawal request from {self.user.mention} has timed out.",
                color=discord.Color.orange()
            )
            # Try to edit the message if possible
            # Note: This may fail if the message was deleted
        except:
            pass

# -----------------------------
# TICKET VIEWS
# -----------------------------
class TicketCloseView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket_button")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in OWNER_IDS:
            await interaction.response.send_message("❌ Only owners can close this ticket.", ephemeral=True)
            return

        try:
            messages = []
            async for m in self.channel.history(limit=None, oldest_first=True):
                timestamp = m.created_at.strftime("%Y-%m-%d %H:%M")
                messages.append(f"**[{timestamp}] {m.author.display_name}:** {m.content}")

            transcript_channel = interaction.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
            if not transcript_channel:
                await interaction.response.send_message("❌ Transcript channel not found.", ephemeral=True)
                return
            
            ticket_name = self.channel.name
            ticket_id = self.channel.id

            embed = discord.Embed(title="📄 Ticket Transcript", color=discord.Color.blue())
            embed.add_field(name="Ticket Information", value=f"Ticket Name: {ticket_name}\nTicket ID: {ticket_id}", inline=False)
            await transcript_channel.send(embed=embed)

            # Split messages into chunks to avoid embed size limits
            for i in range(0, len(messages), 10):
                chunk = "\n".join(messages[i:i+10])
                # Discord embed description limit is 4096 characters
                if len(chunk) > 4096:
                    # Further split if needed - send in embed format for consistency
                    await transcript_channel.send(embed=discord.Embed(
                        description=chunk[:4096],
                        color=discord.Color.blue()
                    ))
                else:
                    await transcript_channel.send(embed=discord.Embed(
                        description=chunk,
                        color=discord.Color.blue()
                    ))

            await interaction.response.send_message("✅ Ticket closed and transcript saved.", ephemeral=True)
            
            # Add error handling for channel deletion
            try:
                await self.channel.delete()
            except discord.Forbidden:
                await transcript_channel.send(f"⚠️ Failed to delete channel {ticket_name} (ID: {ticket_id}) - Missing permissions.")
            except discord.HTTPException as e:
                await transcript_channel.send(f"⚠️ Failed to delete channel {ticket_name} (ID: {ticket_id}) - HTTP error: {e}")
        except Exception as e:
            # Catch any other errors during transcript creation
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error closing ticket: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Error closing ticket: {str(e)}", ephemeral=True)

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Deposit Ticket", style=discord.ButtonStyle.green, custom_id="open_deposit_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        user = interaction.user

        try:
            c.execute("SELECT ticket_number FROM tickets WHERE user_id=?", (user.id,))
            row = c.fetchone()
            ticket_num = row[0] + 1 if row else 1
            c.execute("REPLACE INTO tickets VALUES (?,?)", (user.id, ticket_num))
            conn.commit()

            category = guild.get_channel(TICKET_CATEGORY_ID)
            if not category:
                await interaction.response.send_message("❌ Ticket category not found. Please contact an administrator.", ephemeral=True)
                return
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(view_channel=True)
            }

            ticket_name = f"deposit-{user.name}-{ticket_num:03}"
            channel = await guild.create_text_channel(
                name=ticket_name,
                category=category,
                overwrites=overwrites
            )
            
            # Store ticket metadata for close command
            open_date = datetime.utcnow().strftime("%B %d, %Y %I:%M %p")
            c.execute("""
                INSERT INTO ticket_metadata (channel_id, user_id, panel_name, ticket_name, open_date)
                VALUES (?, ?, ?, ?, ?)
            """, (channel.id, user.id, "Deposit Request", ticket_name, open_date))
            conn.commit()

            # Send ping message first
            await channel.send(content=" ".join(f"<@&{r}>" for r in PING_ROLES))
            
            # Send welcome message without pings
            await channel.send(
                embed=discord.Embed(
                    title="💰 Deposit Ticket",
                    description=f"Welcome {user.mention} to the deposit tickets of Eli's MM! An owner will be with you very shortly. Please state what you would like to deposit.",
                    color=discord.Color.orange()
                ),
                view=TicketCloseView(channel)
            )

            await interaction.response.send_message(f"✅ Your deposit ticket has been created: {channel.mention}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot lacks permissions to create ticket channel.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error creating ticket: {str(e)}", ephemeral=True)

class WithdrawalPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Withdrawal Ticket", style=discord.ButtonStyle.green, custom_id="open_withdraw_ticket")
    async def open_withdraw_ticket(self, interaction: discord.Interaction, button: Button):
        try:
            user_id, bal, req, gambled, _, _, _ = get_user(interaction.user.id)
            remaining_gamble = max(req - gambled, 0)

            if bal <= 0:
                await interaction.response.send_message("❌ You must make a deposit in order to withdraw.", ephemeral=True)
                return
            if remaining_gamble > 0:
                await interaction.response.send_message(f"❌ You must gamble {remaining_gamble:,}$ before opening a withdrawal ticket.", ephemeral=True)
                return

            guild = interaction.guild
            c.execute("SELECT ticket_number FROM tickets WHERE user_id=?", (interaction.user.id,))
            row = c.fetchone()
            ticket_num = row[0] + 1 if row else 1
            c.execute("REPLACE INTO tickets VALUES (?,?)", (interaction.user.id, ticket_num))
            conn.commit()

            category = guild.get_channel(TICKET_CATEGORY_ID)
            if not category:
                await interaction.response.send_message("❌ Ticket category not found. Please contact an administrator.", ephemeral=True)
                return
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(view_channel=True)
            }

            ticket_name = f"withdraw-{interaction.user.name}-{ticket_num:03}"
            channel = await guild.create_text_channel(
                name=ticket_name,
                category=category,
                overwrites=overwrites
            )
            
            # Store ticket metadata for close command
            open_date = datetime.utcnow().strftime("%B %d, %Y %I:%M %p")
            c.execute("""
                INSERT INTO ticket_metadata (channel_id, user_id, panel_name, ticket_name, open_date)
                VALUES (?, ?, ?, ?, ?)
            """, (channel.id, interaction.user.id, "Withdrawal Request", ticket_name, open_date))
            conn.commit()

            await channel.send(
                content=" ".join(f"<@&{r}>" for r in PING_ROLES),
                embed=discord.Embed(
                    title="💸 Withdrawal SAB Currency",
                    description=f"{interaction.user.mention}, click below to request your withdrawal.",
                    color=discord.Color.orange()
                ),
                view=TicketCloseView(channel)
            )

            await interaction.response.send_message(f"✅ Your withdrawal ticket has been created: {channel.mention}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bot lacks permissions to create ticket channel.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error creating withdrawal ticket: {str(e)}", ephemeral=True)

# -----------------------------
# PREFIX COMMANDS
# -----------------------------
@bot.command(name="ticketpanel")
async def ticketpanel(ctx):
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("❌ Only owners can send the ticket panel.")
        return
    embed = discord.Embed(
        title="💰 Deposit Brainrots",
        description=(
            "Welcome to Eli's MM deposit system! Here's what you need to know:\n\n"
            "**💱 Exchange Rate:**\n"
            "• 1$/s SAB (Skibidi After Brainrot) = 1$ gambling currency\n"
            "• Your SAB balance will be converted 1:1 to gambling credits\n\n"
            f"**📊 Minimum Deposit:** {MIN_DEPOSIT:,}$\n\n"
            "**🎰 Gambling Requirements:**\n"
            "• You must gamble **30% of your balance** before withdrawing\n"
            "• All gambling games count toward this requirement\n"
            "• Track your progress with `!amount` command\n\n"
            "**📝 How to Deposit:**\n"
            "1. Click the button below to open a deposit ticket\n"
            "2. An owner will assist you shortly\n"
            "3. State the SAB amount you want to deposit"
        ),
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed, view=TicketPanelView())

@bot.command(name="withdrawalpanel")
async def withdrawalpanel(ctx):
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("❌ Only owners can send the withdrawal panel.")
        return
    await ctx.send(embed=discord.Embed(
        title="💸 Withdrawal SAB Currency",
        description="Click the button below to open a withdrawal ticket.",
        color=discord.Color.orange()
    ), view=WithdrawalPanelView())

@bot.command(name="assist")
async def assist(ctx):
    embed = discord.Embed(title="📘 SAB Bot Assistance", color=discord.Color.blurple())
    embed.add_field(name="👤 General Commands", value=(
        "**!amount** - View your balance and remaining required gamble\n"
        "**!stats [@user]** - View gambling profile (yours or another user's)\n"
        "**!favorite <game>** - Set your favorite game\n"
        "**!donate @user [amount]** - Donate balance to another player\n"
        "**!withdraw** - Request a full withdrawal (requires owner approval)\n"
        "**!leaderboards** (or **!lb**) - View the top 10 players leaderboard\n"
        "**!games** - View all gambling game rules and info"
    ), inline=False)
    embed.add_field(name="🎮 Solo Gambling Games", value=(
        "**!cf [amount] [heads/tails]** - Simple coinflip! Bet on heads or tails\n"
        "**!flipchase [amount]** - Flip & Chase: Double or nothing progressive game\n"
        "**!rps [amount]** - Rock Paper Scissors with interactive buttons!\n"
        "**!baccarat** - Play Baccarat with chip buttons and strategy!\n"
        "**!slots [amount]** - Play the slot machine (3x3 grid)\n"
        "**!luckynumber [amount] [50-5000]** - Start lucky number game\n"
        "**!pick [number]** - Pick your lucky number\n"
        "**!crash [amount]** - Play crash game (cash out before it crashes!)\n"
        "**!blackjack [amount]** - Play Blackjack! Beat the dealer without going over 21\n"
        "**!limbo [amount]** - Play Limbo! Above or below 50?\n"
        "**!spinwheel** - Spin the daily wheel! (1 free daily spin)\n"
        "**!spincom** - View all spin wheel commands"
    ), inline=False)
    embed.add_field(name="⚔️ PvP Games", value=(
        "**!fight @user [amount]** - Challenge a player to a gladiator duel!\n"
        "**!pickgladiator [name]** - Pick your gladiator for fights\n"
        "**!choptree @user [amount]** - Challenge a player to risky lumberjack!\n"
        "**!chop** - Take your turn chopping the tree"
    ), inline=False)
    embed.add_field(name="🃏 Poker Commands", value=(
        "**!pokerjoin <amount>** - Join/create a poker table\n"
        "**!pokerstart** - Start the game (host only)\n"
        "**!pokercheck** - Check (no bet)\n"
        "**!pokerbet <amount>** - Place a bet\n"
        "**!pokerraise <amount>** - Raise the bet\n"
        "**!pokercall** - Call the current bet\n"
        "**!pokerfold** - Fold your hand\n"
        "**!pokertable** - View table state\n"
        "**!pokerleave** - Leave the table\n"
        "**!pokerend** - End game (host only)"
    ), inline=False)
    embed.add_field(name="🛠️ Utility Commands", value=(
        "**!resetgames** - Cancel all your active games and get refunds\n"
        "**!stats [@user]** - View gambling profile\n"
        "**!favorite <game>** - Set your favorite game"
    ), inline=False)
    embed.add_field(name="🔐 Provably Fair System", value=(
        "**!fairinfo** - Learn about our provably fair system\n"
        "**!myseeds** - View your client seed and nonce\n"
        "**!setseed <hex>** - Set custom client seed\n"
        "**!verify [bet#]** - Verify your recent bets\n"
        "**!revealedseed** - View revealed server seeds"
    ), inline=False)
    if is_owner(ctx.author):
        embed.add_field(name="🔐 Owner Commands", value=(
            "**!ownercom** - Display all owner commands (detailed list)\n"
            "**!ticketpanel** - Send deposit ticket panel\n"
            "**!withdrawalpanel** - Send withdrawal ticket panel\n"
            "**!ticketclose [reason]** - Close a ticket with optional reason\n"
            "**!deposit @user amount** - Add gambling amount to a user\n"
            "**!viewamount @user** - View a user's balance\n"
            "**!amountall [page]** - View all users balances\n"
            "**!gambledall** - View total gambling statistics across all players\n"
            "**!resetgamblingall** - Reset all gambling statistics (total_gambled & gambled)\n"
            "**!addstock <Name>, <Mutation>, <Trait>, <Price>, <Stock>, <Account>** - Add pet to stock\n"
            "**!resetstock** - Delete all current stock items\n"
            "**!wipeamount @user** - Wipe a user's balance\n"
            "**!stick [message]** - Create a sticky message at the bottom of the channel\n"
            "**!unstick** - Remove the sticky message from the current channel\n"
            "**!rotateseed** - Rotate provably fair server seed"
        ), inline=False)
    await ctx.send(embed=embed)

@bot.command(name="amount")
async def amount(ctx):
    """Display user's balance and gamble requirements."""
    try:
        user_id, bal, req, gambled, _, _, _ = get_user(ctx.author.id)
        remaining = max(req - gambled, 0)
        await ctx.send(f"💰 **Your Gambling Amount**\nBalance: `{bal:,}$`\nRequired Gamble: `{req:,}$`\nRemaining: `{remaining:,}$`")
    except Exception as e:
        await ctx.send(f"❌ Error fetching your balance: {str(e)}")

@bot.command(name="stats")
async def stats(ctx, member: discord.Member = None):
    """Display gambling profile for a user."""
    try:
        # If no member specified, show stats for command author
        target_user = member if member else ctx.author
        
        # Get user data
        user_data = get_user(target_user.id)
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = user_data[:6]
        
        # Get favorite game
        favorite_game = get_favorite_game(target_user.id)
        
        # Create embed
        embed = discord.Embed(
            title="• Gambling Profile •",
            color=discord.Color.blue()
        )
        
        # Add fields
        embed.add_field(
            name="Username",
            value=f"{target_user.mention} ({target_user.name})",
            inline=False
        )
        embed.add_field(
            name="User ID",
            value=str(target_user.id),
            inline=False
        )
        embed.add_field(
            name="Balance",
            value=format_money(balance),
            inline=False
        )
        embed.add_field(
            name="Gambled",
            value=f"{format_money(total_gambled)} (all time)",
            inline=False
        )
        embed.add_field(
            name="Favorite Game",
            value=favorite_game,
            inline=False
        )
        
        # Set thumbnail to user's avatar
        embed.set_thumbnail(url=target_user.display_avatar.url)
        
        # Set footer with timestamp
        from datetime import datetime
        current_time = datetime.now().strftime("%I:%M %p")
        embed.set_footer(text=f"Eli's MM Service• Today at {current_time}")
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error fetching stats: {str(e)}")

@bot.command(name="favorite")
async def favorite(ctx, *, game_name: str = None):
    """Set your favorite game."""
    try:
        if game_name is None:
            await ctx.send("❌ Usage: `!favorite <game name>`\nExample: `!favorite Blackjack`")
            return
        
        # Limit length to prevent abuse
        if len(game_name) > 100:
            await ctx.send("❌ Game name must be 100 characters or less!")
            return
        
        # Set the favorite game
        set_favorite_game(ctx.author.id, game_name)
        
        await ctx.send(f"✅ Your favorite game has been set to: **{game_name}**")
    except Exception as e:
        await ctx.send(f"❌ Error setting favorite game: {str(e)}")

@bot.command(name="fairinfo")
async def fairinfo(ctx):
    """Display information about the provably fair system."""
    try:
        stats = provably_fair.get_system_stats()
        
        embed = discord.Embed(
            title="🔐 Provably Fair System",
            description="Our gambling system uses cryptographic proof to ensure fairness and transparency.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="How It Works",
            value=(
                "• **Server Seed**: Secret value used to generate results\n"
                "• **Client Seed**: Your personal seed (customizable)\n"
                "• **Nonce**: Counter that increments with each bet\n"
                "• **Result**: Generated using HMAC-SHA256"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Current Server Seed Hash",
            value=f"`{stats['active_seed_hash'][:32]}...`",
            inline=False
        )
        
        embed.add_field(
            name="Your Seeds",
            value="Use `!myseeds` to view your client seed and nonce",
            inline=False
        )
        
        embed.add_field(
            name="Verification",
            value=(
                "`!verify` - Verify your recent bets\n"
                "`!setseed <seed>` - Set custom client seed\n"
                "`!revealedseed` - View revealed server seeds"
            ),
            inline=False
        )
        
        embed.add_field(
            name="System Stats",
            value=f"Total Bets: {stats['total_bets']:,}\nTotal Users: {stats['total_users']:,}\nSeed Rotations: {stats['total_rotations']}",
            inline=False
        )
        
        embed.set_footer(text="All bets are verifiable and cannot be manipulated")
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="myseeds")
async def myseeds(ctx):
    """View your current client seed and nonce."""
    try:
        client_seed, nonce = provably_fair.get_or_create_user_seeds(ctx.author.id)
        seed_hash = provably_fair.get_active_server_seed_hash()
        
        embed = discord.Embed(
            title="🔑 Your Provably Fair Seeds",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Client Seed",
            value=f"`{client_seed}`",
            inline=False
        )
        
        embed.add_field(
            name="Current Nonce",
            value=f"`{nonce}`",
            inline=True
        )
        
        embed.add_field(
            name="Server Seed Hash",
            value=f"`{seed_hash[:32]}...`",
            inline=False
        )
        
        embed.add_field(
            name="Customize",
            value="Use `!setseed <hex_string>` to set your own client seed",
            inline=False
        )
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="setseed")
async def setseed(ctx, new_seed: str = None):
    """Set your custom client seed."""
    try:
        if new_seed is None:
            await ctx.send("❌ Usage: `!setseed <hex_string>`\nExample: `!setseed deadbeefcafe1234567890abcdef`")
            return
        
        # Validate and set seed
        success = provably_fair.set_client_seed(ctx.author.id, new_seed)
        
        if success:
            await ctx.send(f"✅ Your client seed has been updated to: `{new_seed}`\n"
                          f"💡 Your nonce has been preserved. Use `!myseeds` to view your seeds.")
        else:
            await ctx.send("❌ Invalid seed! Must be a valid hexadecimal string.\n"
                          "Example: `deadbeef1234567890abcdef`")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="verify")
async def verify(ctx, bet_number: int = 1):
    """Verify your recent bets."""
    try:
        history = provably_fair.get_user_bet_history(ctx.author.id, limit=10)
        
        if not history:
            await ctx.send("❌ No betting history found!")
            return
        
        if bet_number < 1 or bet_number > len(history):
            await ctx.send(f"❌ Invalid bet number! You have {len(history)} recent bets. Use `!verify <1-{len(history)}>`")
            return
        
        # Get the bet (1-indexed for user, 0-indexed in list)
        bet = history[bet_number - 1]
        bet_id, game_type, seed_hash, client_seed, nonce, result, bet_amount, timestamp = bet
        
        embed = discord.Embed(
            title=f"🔍 Bet Verification #{bet_id}",
            description=f"**Game**: {game_type.title()}\n**Timestamp**: {timestamp[:19].replace('T', ' ')} UTC",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Bet Details",
            value=f"Amount: {format_money(bet_amount)}\nResult: `{result}`\nNonce: `{nonce}`",
            inline=False
        )
        
        embed.add_field(
            name="Seeds Used",
            value=f"Client Seed: `{client_seed[:24]}...`\nServer Hash: `{seed_hash[:24]}...`",
            inline=False
        )
        
        # Check if server seed has been revealed
        revealed_seeds = provably_fair.get_revealed_seeds(limit=50)
        revealed_seed = None
        for seed, hash_val, revealed_at in revealed_seeds:
            if hash_val == seed_hash:
                revealed_seed = seed
                break
        
        if revealed_seed:
            # Verify the bet
            modulo = 2 if game_type == "coinflip" else 100
            is_valid = provably_fair.verify_bet(revealed_seed, client_seed, nonce, result, modulo)
            
            embed.add_field(
                name="✅ Server Seed Revealed",
                value=f"`{revealed_seed[:32]}...`",
                inline=False
            )
            
            embed.add_field(
                name="Verification Result",
                value=f"{'✅ **VERIFIED** - Result is correct!' if is_valid else '❌ **FAILED** - Result mismatch!'}",
                inline=False
            )
        else:
            embed.add_field(
                name="⏳ Server Seed Not Yet Revealed",
                value="The server seed will be revealed after rotation. Check back later with `!revealedseed`",
                inline=False
            )
        
        embed.set_footer(text=f"Showing bet {bet_number} of {len(history)}")
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="revealedseed")
async def revealedseed(ctx):
    """View revealed server seeds."""
    try:
        revealed = provably_fair.get_revealed_seeds(limit=5)
        
        if not revealed:
            await ctx.send("❌ No server seeds have been revealed yet!")
            return
        
        embed = discord.Embed(
            title="🔓 Revealed Server Seeds",
            description="These seeds were previously used and can now be used to verify past bets.",
            color=discord.Color.gold()
        )
        
        for i, (seed, seed_hash, revealed_at) in enumerate(revealed, 1):
            timestamp = revealed_at[:19].replace('T', ' ') if revealed_at else "Unknown"
            embed.add_field(
                name=f"Seed #{i}",
                value=f"**Seed**: `{seed[:32]}...`\n**Hash**: `{seed_hash[:32]}...`\n**Revealed**: {timestamp} UTC",
                inline=False
            )
        
        embed.set_footer(text="Use !verify to verify your bets with these seeds")
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="rotateseed")
@commands.check(is_owner)
async def rotateseed(ctx):
    """[OWNER] Rotate the server seed."""
    try:
        old_seed, new_hash = provably_fair.rotate_server_seed()
        
        embed = discord.Embed(
            title="🔄 Server Seed Rotated",
            description="The server seed has been rotated. The old seed is now revealed.",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Old Server Seed (Revealed)",
            value=f"`{old_seed}`",
            inline=False
        )
        
        embed.add_field(
            name="New Server Seed Hash",
            value=f"`{new_hash[:32]}...`",
            inline=False
        )
        
        embed.add_field(
            name="Impact",
            value="All users can now verify their past bets using the revealed seed.",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
        # Log the rotation
        if AUDIT_LOG_CHANNEL:
            log_channel = bot.get_channel(AUDIT_LOG_CHANNEL)
            if log_channel:
                log_embed = discord.Embed(
                    title="🔄 Provably Fair Seed Rotation",
                    description=f"Server seed rotated by {ctx.author.mention}",
                    color=discord.Color.blue()
                )
                log_embed.add_field(name="Old Seed", value=f"`{old_seed[:32]}...`", inline=False)
                log_embed.add_field(name="New Hash", value=f"`{new_hash[:32]}...`", inline=False)
                log_embed.timestamp = datetime.utcnow()
                await log_channel.send(embed=log_embed)
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="donate")
async def donate(ctx, user: discord.Member = None, amount: str = None):
    """Donate balance to another user."""
    if user is None or amount is None:
        await ctx.send("❌ Usage: `!donate @user <amount>`")
        return
    
    # Can't donate to yourself
    if user.id == ctx.author.id:
        await ctx.send("❌ You cannot donate to yourself!")
        return
    
    # Can't donate to bots
    if user.bot:
        await ctx.send("❌ You cannot donate to bots!")
        return
    
    # Check cooldown
    current_time = datetime.utcnow()
    
    # Initialize donation data for user if not exists
    if ctx.author.id not in donation_data:
        donation_data[ctx.author.id] = {'cooldown_until': None, 'donations': []}
    
    user_donation_data = donation_data[ctx.author.id]
    
    # Check if user is on cooldown
    if user_donation_data['cooldown_until'] is not None:
        if current_time < user_donation_data['cooldown_until']:
            time_remaining = user_donation_data['cooldown_until'] - current_time
            minutes_remaining = int(time_remaining.total_seconds() / 60)
            seconds_remaining = int(time_remaining.total_seconds() % 60)
            await ctx.send(f"❌ **Donation Cooldown Active**\nYou can donate again in **{minutes_remaining}m {seconds_remaining}s**\nYou've reached the 250M donation limit.")
            return
        else:
            # Cooldown expired, reset
            user_donation_data['cooldown_until'] = None
            user_donation_data['donations'] = []
    
    try:
        # Parse donation amount
        value = parse_money(amount)
        
        # Minimum donation amount
        if value < 1000000:  # 1M minimum
            await ctx.send("❌ Minimum donation amount is 1,000,000$")
            return
        
        # Calculate total donations in current period (before cooldown was triggered)
        total_donated = sum(amt for amt, _ in user_donation_data['donations'])
        
        # Check if this donation would exceed threshold
        if total_donated + value > DONATION_THRESHOLD:
            remaining_allowance = DONATION_THRESHOLD - total_donated
            if remaining_allowance > 0:
                await ctx.send(f"❌ This donation would exceed your 250M limit!\nYou've donated: {total_donated:,}$\nRemaining allowance: {remaining_allowance:,}$\nRequested: {value:,}$")
            else:
                await ctx.send(f"❌ You've reached your 250M donation limit!\nPlease wait for cooldown to reset.")
            return
        
        # Get donor's balance
        donor_id, donor_bal, donor_req, donor_gambled, _, _, _ = get_user(ctx.author.id)
        
        # Check if donor has enough balance
        if donor_bal < value:
            await ctx.send(f"❌ Insufficient balance! You have {donor_bal:,}$ but tried to donate {value:,}$")
            return
        
        # Get recipient's info (ensure they exist in database)
        recipient_id, recipient_bal, recipient_req, recipient_gambled, _, _, _ = get_user(user.id)
        
        # Additional validation: Verify balances haven't changed during processing
        donor_id_check, donor_bal_check, _, _, _, _ = get_user(ctx.author.id)
        if donor_bal_check != donor_bal:
            await ctx.send("❌ Your balance changed during processing. Please try again.")
            return
        
        # Perform the transaction with atomic operations
        # Deduct from donor
        update_balance(ctx.author.id, -value)
        
        # Add to recipient
        update_balance(user.id, value)
        
        # Verify the transaction completed correctly
        _, donor_new_bal, _, _, _, _ = get_user(ctx.author.id)
        _, recipient_new_bal, _, _, _, _ = get_user(user.id)
        
        # Verify transaction integrity for BOTH donor and recipient
        expected_donor_bal = donor_bal - value
        expected_recipient_bal = recipient_bal + value
        
        if donor_new_bal != expected_donor_bal or recipient_new_bal != expected_recipient_bal:
            # Rollback by reversing operations
            update_balance(ctx.author.id, value)
            update_balance(user.id, -value)
            await ctx.send(f"❌ Transaction failed verification. Operation rolled back.\nExpected: Donor={expected_donor_bal:,}, Recipient={expected_recipient_bal:,}\nActual: Donor={donor_new_bal:,}, Recipient={recipient_new_bal:,}")
            return
        
        # Record this donation
        user_donation_data['donations'].append((value, current_time))
        total_donated_now = sum(amt for amt, _ in user_donation_data['donations'])
        
        # Check if threshold reached - trigger cooldown
        if total_donated_now >= DONATION_THRESHOLD:
            user_donation_data['cooldown_until'] = current_time + timedelta(hours=DONATION_COOLDOWN_HOURS)
            cooldown_triggered = True
        else:
            cooldown_triggered = False
        
        # Log transaction for donor
        await log_transaction(
            ctx.author.id,
            "DONATION_SENT",
            value,
            donor_bal,
            donor_new_bal,
            f"Donated to {user.name} ({user.id})"
        )
        
        # Log transaction for recipient
        await log_transaction(
            user.id,
            "DONATION_RECEIVED",
            value,
            recipient_bal,
            recipient_new_bal,
            f"Received from {ctx.author.name} ({ctx.author.id})"
        )
        
        # Log to audit channel
        await log_user_activity(
            bot,
            ctx.author,
            "Donation Sent",
            f"Amount: {value:,}$\nRecipient: {user.mention}\nDonor Balance: {donor_bal:,}$ → {donor_new_bal:,}$\nRecipient Balance: {recipient_bal:,}$ → {recipient_new_bal:,}$"
        )
        
        # Success message
        embed = discord.Embed(
            title="💝 Donation Successful!",
            description=f"{ctx.author.mention} donated **{value:,}$** to {user.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="📤 Your New Balance", value=f"{donor_new_bal:,}$", inline=True)
        embed.add_field(name="📥 Recipient's New Balance", value=f"{recipient_new_bal:,}$", inline=True)
        embed.add_field(name="💰 Total Donated", value=f"{total_donated_now:,}$ / 250M", inline=False)
        
        if cooldown_triggered:
            embed.set_footer(text="⚠️ You've reached 250M donated! 1-hour cooldown activated.")
            embed.color = discord.Color.orange()
        else:
            remaining = DONATION_THRESHOLD - total_donated_now
            embed.set_footer(text=f"Remaining donation allowance: {remaining:,}$")
        
        await ctx.send(embed=embed)
        
        # Notify recipient
        try:
            recipient_embed = discord.Embed(
                title="💰 You Received a Donation!",
                description=f"{ctx.author.mention} donated **{value:,}$** to you!",
                color=discord.Color.gold()
            )
            recipient_embed.add_field(name="Your New Balance", value=f"{recipient_new_bal:,}$", inline=False)
            await user.send(embed=recipient_embed)
        except:
            # If DM fails, that's okay
            pass
            
    except ValueError:
        await ctx.send("❌ Invalid amount format! Use formats like: `10m`, `1.5m`, `500k`, or `1000000`")
    except Exception as e:
        await ctx.send(f"❌ Error processing donation: {str(e)}")

@bot.command(name="withdraw")
async def withdraw(ctx):
    """Request a full withdrawal. Owners must approve the request."""
    try:
        user_id, bal, req, gambled, _, _, _ = get_user(ctx.author.id)
        remaining_gamble = max(req - gambled, 0)
        
        # Check if user has a balance
        if bal <= 0:
            await ctx.send("❌ You must make a deposit in order to withdraw.")
            return
        
        # Check if gambling requirement is met
        if remaining_gamble > 0:
            await ctx.send(f"❌ You must gamble {remaining_gamble:,}$ before withdrawing.")
            return
        
        # Withdraw full balance only
        withdraw_amount = bal
        
        # Create withdrawal request embed
        embed = discord.Embed(
            title="💸 Withdrawal Request",
            description=f"{ctx.author.mention} has requested a full withdrawal.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Withdrawal Amount", value=f"{withdraw_amount:,}$", inline=True)
        embed.add_field(name="Current Balance", value=f"{bal:,}$", inline=True)
        embed.add_field(name="Remaining After", value="0$", inline=True)
        embed.set_footer(text="Owners: Click a button to approve or decline this withdrawal.")
        
        # Create the view with confirm/decline buttons
        view = WithdrawalConfirmView(ctx.author, withdraw_amount, ctx.channel)
        
        # Send the embed with buttons
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Error processing withdrawal request: {str(e)}")

# -----------------------------
# 🪙 COINFLIP GAMBLING GAME
# -----------------------------
# Global dictionary to track active coinflip games
active_coinflip = {}

class CoinflipStartView(View):
    """View for starting a coinflip game."""
    
    def __init__(self, user_id, amount, choice):
        super().__init__(timeout=120)  # Increased from 60 to 120 seconds
        self.user_id = user_id
        self.amount = amount
        self.choice = choice  # "heads" or "tails"
    
    @discord.ui.button(label="Start CF", style=discord.ButtonStyle.green, emoji="🪙")
    async def start_cf(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start the coinflip game."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your coinflip game!", ephemeral=True)
            return
        
        try:
            # Use provably fair system to determine outcome
            result, client_seed, nonce, seed_hash = provably_fair.place_bet(
                self.user_id,
                "coinflip",
                self.amount,
                2  # modulo 2 for coinflip: 0=heads, 1=tails
            )
            
            # Convert result to outcome
            outcome = "heads" if result == 0 else "tails"
            won = self.choice == outcome
            
            # Get user data
            user_id, balance, required_gamble, gambled, total_gambled, _ = get_user(self.user_id)
            
            if won:
                # Player won
                winnings = int(self.amount * 1.95)  # 1.95x payout (5% house edge)
                balance += winnings
                gambled += self.amount
                total_gambled += self.amount
                
                # Update database
                c.execute(
                    "UPDATE users SET balance=?, gambled=?, total_gambled=? WHERE user_id=?",
                    (balance, gambled, total_gambled, self.user_id)
                )
                conn.commit()
                
                # Log the win
                await log_bet_activity(self.user_id, self.amount, "coinflip", "win")
                
                remaining = max(required_gamble - gambled, 0)
                
                # Create win embed
                embed = discord.Embed(
                    title="🎉 Coinflip Won!",
                    description=f"**You won!** The coin landed on **{outcome}**!",
                    color=discord.Color.green()
                )
                embed.add_field(name="Your Choice", value=f"**{self.choice.upper()}**", inline=True)
                embed.add_field(name="Result", value=f"**{outcome.upper()}**", inline=True)
                embed.add_field(name="Winnings", value=f"{format_money(winnings)}", inline=True)
                embed.add_field(name="New Balance", value=f"{format_money(balance)}", inline=True)
                embed.add_field(name="Bet Amount", value=f"{format_money(self.amount)}", inline=True)
                embed.add_field(name="Remaining Required", value=f"{format_money(remaining)}", inline=True)
                
                # Add provably fair info
                embed.add_field(
                    name="🔐 Provably Fair",
                    value=f"Client Seed: `{client_seed[:16]}...`\nNonce: `{nonce}`\nServer Hash: `{seed_hash[:16]}...`",
                    inline=False
                )
                embed.set_footer(text="Use !verify to verify this bet • !fairinfo for details")
                
                # Add flip again button
                view = CoinflipAgainView(self.user_id, self.amount, self.choice)
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                # Player lost
                gambled += self.amount
                total_gambled += self.amount
                
                # Update database
                c.execute(
                    "UPDATE users SET gambled=?, total_gambled=? WHERE user_id=?",
                    (gambled, total_gambled, self.user_id)
                )
                conn.commit()
                
                # Log the loss
                await log_bet_activity(self.user_id, self.amount, "coinflip", "loss")
                
                remaining = max(required_gamble - gambled, 0)
                
                # Create loss embed
                embed = discord.Embed(
                    title="💀 Coinflip Lost!",
                    description=f"**You lost!** The coin landed on **{outcome}**.",
                    color=discord.Color.red()
                )
                embed.add_field(name="Your Choice", value=f"**{self.choice.upper()}**", inline=True)
                embed.add_field(name="Result", value=f"**{outcome.upper()}**", inline=True)
                embed.add_field(name="Lost Amount", value=f"{format_money(self.amount)}", inline=True)
                embed.add_field(name="New Balance", value=f"{format_money(balance)}", inline=True)
                embed.add_field(name="Required Gamble", value=f"{format_money(required_gamble)}", inline=True)
                embed.add_field(name="Remaining", value=f"{format_money(remaining)}", inline=True)
                
                # Add provably fair info
                embed.add_field(
                    name="🔐 Provably Fair",
                    value=f"Client Seed: `{client_seed[:16]}...`\nNonce: `{nonce}`\nServer Hash: `{seed_hash[:16]}...`",
                    inline=False
                )
                embed.set_footer(text="Use !verify to verify this bet • !fairinfo for details")
                
                # Add flip again button
                view = CoinflipAgainView(self.user_id, self.amount, self.choice)
                await interaction.response.edit_message(embed=embed, view=view)
            
            # Remove from active games
            if self.user_id in active_coinflip:
                del active_coinflip[self.user_id]
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Error during coinflip: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="End Game", style=discord.ButtonStyle.red, emoji="💰")
    async def end_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cash out and end the game without flipping."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your coinflip game!", ephemeral=True)
            return
        
        try:
            # Get user data
            user_id, balance, required_gamble, gambled, total_gambled, _ = get_user(self.user_id)
            
            # Return the bet to the player
            balance += self.amount
            c.execute("UPDATE users SET balance=? WHERE user_id=?", (balance, self.user_id))
            conn.commit()
            
            # Create cashout embed
            embed = discord.Embed(
                title="💰 Coinflip Ended!",
                description=f"You cashed out before flipping!",
                color=discord.Color.gold()
            )
            embed.add_field(name="Returned Amount", value=f"{format_money(self.amount)}", inline=True)
            embed.add_field(name="New Balance", value=f"{format_money(balance)}", inline=True)
            embed.set_footer(text="Your bet has been returned to your balance.")
            
            await interaction.response.edit_message(embed=embed, view=None)
            
            # Remove from active games
            if self.user_id in active_coinflip:
                del active_coinflip[self.user_id]
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Error ending game: {str(e)}", ephemeral=True)

class CoinflipAgainView(View):
    """View for flipping again with the same bet and choice."""
    
    def __init__(self, user_id, amount, choice):
        super().__init__(timeout=120)  # Increased from 60 to 120 seconds
        self.user_id = user_id
        self.amount = amount
        self.choice = choice
    
    @discord.ui.button(label="Flip Again", style=discord.ButtonStyle.blurple, emoji="🔄")
    async def flip_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Flip again with the same bet and choice."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your coinflip game!", ephemeral=True)
            return
        
        try:
            # Get user data
            user_id, balance, required_gamble, gambled, total_gambled, _ = get_user(self.user_id)
            
            # Check if user has enough balance
            if balance < self.amount:
                await interaction.response.send_message("❌ You don't have enough balance to flip again!", ephemeral=True)
                return
            
            # Deduct bet
            balance -= self.amount
            c.execute("UPDATE users SET balance=? WHERE user_id=?", (balance, self.user_id))
            conn.commit()
            
            # Create new start view
            embed = discord.Embed(
                title="🪙 Coinflip Ready!",
                description=f"**Your Choice:** {self.choice.upper()}\n\n⚠️ Using the flip again button will use the same side of the coin you originally picked.",
                color=discord.Color.blue()
            )
            embed.add_field(name="Bet Amount", value=f"{format_money(self.amount)}", inline=True)
            embed.add_field(name="Potential Win", value=f"{format_money(int(self.amount * 1.95))}", inline=True)
            embed.add_field(name="New Balance", value=f"{format_money(balance)}", inline=True)
            embed.set_footer(text="Click 'Start CF' to flip the coin!")
            
            view = CoinflipStartView(self.user_id, self.amount, self.choice)
            await interaction.response.edit_message(embed=embed, view=view)
            
            # Mark as active
            active_coinflip[self.user_id] = True
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error flipping again: {str(e)}", ephemeral=True)

@bot.command(name="cf")
async def coinflip(ctx, amount: str = None, choice: str = None):
    """Simple coinflip game - bet on heads or tails!"""
    try:
        if amount is None or choice is None:
            await ctx.send("❌ Usage: `!cf <amount> <heads/tails>`\nExample: `!cf 200m heads`")
            return
        
        # Validate choice
        choice = choice.lower()
        if choice not in ["heads", "tails"]:
            await ctx.send("❌ Invalid choice! Use `heads` or `tails`.")
            return
        
        # Check if user already has an active coinflip
        if ctx.author.id in active_coinflip:
            await ctx.send("❌ You already have an active coinflip game!")
            return
        
        value = parse_money(amount)
        if value <= 0:
            await ctx.send("❌ Invalid amount format! Use k, m, or b (e.g., 10m, 5k).")
            return
        
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(ctx.author.id)
        
        if value > balance:
            await ctx.send("❌ You cannot gamble more than your balance.")
            return
        
        # Check for rapid betting (fraud detection)
        is_rapid = await check_rapid_betting(ctx.author.id)
        if is_rapid:
            await send_fraud_alert(
                bot,
                ctx.author,
                "Rapid Betting Detected",
                f"User placed {RAPID_BET_THRESHOLD}+ bets in 60 seconds\nBet Amount: {value:,}$\nGame: Coinflip"
            )
        
        # Check for high bet (fraud detection)
        if value >= HIGH_BET_THRESHOLD:
            await log_user_activity(
                bot,
                ctx.author,
                "High Value Bet",
                f"Amount: {value:,}$\nGame: Coinflip\nBalance: {balance:,}$"
            )
        
        # Deduct initial bet from balance
        balance -= value
        c.execute("UPDATE users SET balance=? WHERE user_id=?", (balance, ctx.author.id))
        conn.commit()
        
        # Mark as active
        active_coinflip[ctx.author.id] = True
        
        # Create embed
        embed = discord.Embed(
            title="🪙 Coinflip Ready!",
            description=f"**Your Choice:** {choice.upper()}\n\n⚠️ Using the flip again button will use the same side of the coin you originally picked.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Bet Amount", value=f"{format_money(value)}", inline=True)
        embed.add_field(name="Potential Win", value=f"{format_money(int(value * 1.95))}", inline=True)
        embed.add_field(name="Your Balance", value=f"{format_money(balance)}", inline=True)
        embed.set_footer(text="Click 'Start CF' to flip the coin!")
        
        view = CoinflipStartView(ctx.author.id, value, choice)
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Error starting coinflip: {str(e)}")

# -----------------------------
# ✅ FLIP & CHASE GAMBLING GAME
# -----------------------------
# Global dictionary to track active flip & chase games
active_flip_chase = {}

# Global dictionary to track donation data per user
# Structure: {user_id: {'cooldown_until': datetime, 'donations': [(amount, timestamp), ...]}}
donation_data = {}
# Maximum cumulative donation before cooldown
DONATION_THRESHOLD = 250_000_000  # 250M total
# Cooldown duration
DONATION_COOLDOWN_HOURS = 1

class FlipChaseView(View):
    def __init__(self, user_id, current_winnings, initial_bet, rounds_won):
        super().__init__(timeout=180)  # Increased from 60 to 180 seconds (3 minutes)
        self.user_id = user_id
        self.current_winnings = current_winnings
        self.initial_bet = initial_bet
        self.rounds_won = rounds_won
        self.game_resolved = False  # Track if game has been banked or lost
        
    @discord.ui.button(label="🎲 Chase (Double or Nothing)", style=discord.ButtonStyle.green)
    async def chase_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        # Flip the coin using provably fair
        result, client_seed, nonce, seed_hash = provably_fair.place_bet(
            self.user_id,
            "flipchase",
            self.current_winnings,
            2  # modulo 2 for coinflip: 0=heads, 1=tails
        )
        
        outcome = "heads" if result == 0 else "tails"
        player_choice = random.choice(["heads", "tails"])
        won = player_choice == outcome
        
        if won:
            # Double winnings and offer to chase again
            self.current_winnings *= 2
            self.rounds_won += 1
            
            # Mark this view as resolved since we're creating a new one
            self.game_resolved = True
            
            embed = discord.Embed(
                title="🎉 Chase Successful!",
                description=f"**You won!** The coin landed on **{outcome}**!",
                color=discord.Color.green()
            )
            embed.add_field(name="Current Winnings", value=f"{format_money(self.current_winnings)}", inline=True)
            embed.add_field(name="Rounds Won", value=f"{self.rounds_won}", inline=True)
            embed.add_field(name="Initial Bet", value=f"{format_money(self.initial_bet)}", inline=True)
            embed.set_footer(text="Chase again to double your winnings or Bank to keep them!")
            
            # Update view with new winnings
            new_view = FlipChaseView(self.user_id, self.current_winnings, self.initial_bet, self.rounds_won)
            await interaction.message.edit(embed=embed, view=new_view)
        else:
            # Lost everything
            self.game_resolved = True  # Mark game as resolved
            embed = discord.Embed(
                title="💀 Chase Failed!",
                description=f"**You lost!** The coin landed on **{outcome}**.\nYou lost all your winnings!",
                color=discord.Color.red()
            )
            embed.add_field(name="Lost Winnings", value=f"{format_money(self.current_winnings)}", inline=True)
            embed.add_field(name="Rounds Won", value=f"{self.rounds_won}", inline=True)
            embed.add_field(name="Initial Bet", value=f"{format_money(self.initial_bet)}", inline=True)
            
            # Update database - user loses everything (already deducted initial bet)
            user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.user_id)
            
            # Log the loss
            await log_bet_activity(self.user_id, self.initial_bet, "flipchase", "loss")
            
            # Remove from active games
            if self.user_id in active_flip_chase:
                del active_flip_chase[self.user_id]
            
            # Disable buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.message.edit(embed=embed, view=self)
            
    @discord.ui.button(label="💰 Bank (Keep Winnings)", style=discord.ButtonStyle.primary)
    async def bank_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        try:
            # Mark game as resolved immediately to prevent double-refund on timeout
            self.game_resolved = True
            
            # Get user data
            user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.user_id)
            
            # Add winnings to balance
            profit = self.current_winnings - self.initial_bet
            balance += self.current_winnings
            gambled += self.initial_bet
            total_gambled += self.initial_bet
            
            # Update database with explicit commit
            c.execute(
                "UPDATE users SET balance=?, gambled=?, total_gambled=? WHERE user_id=?",
                (balance, gambled, total_gambled, self.user_id)
            )
            conn.commit()
            
            # Log the win
            await log_bet_activity(self.user_id, self.initial_bet, "flipchase", "win")
            
            # Calculate remaining requirement
            remaining = max(required_gamble - gambled, 0)
            
            embed = discord.Embed(
                title="💰 Winnings Banked!",
                description=f"You successfully banked your winnings!",
                color=discord.Color.gold()
            )
            embed.add_field(name="Total Winnings", value=f"{format_money(self.current_winnings)}", inline=True)
            embed.add_field(name="Profit", value=f"+{format_money(profit)}", inline=True)
            embed.add_field(name="Rounds Won", value=f"{self.rounds_won}", inline=True)
            embed.add_field(name="New Balance", value=f"{format_money(balance)}", inline=False)
            embed.add_field(name="Required Gamble", value=f"{format_money(required_gamble)}", inline=True)
            embed.add_field(name="Remaining", value=f"{format_money(remaining)}", inline=True)
            
            # Remove from active games
            if self.user_id in active_flip_chase:
                del active_flip_chase[self.user_id]
            
            # Disable buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.message.edit(embed=embed, view=self)
            
        except Exception as e:
            # If banking fails, try to refund the user
            try:
                user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.user_id)
                balance += self.current_winnings
                c.execute("UPDATE users SET balance=? WHERE user_id=?", (balance, self.user_id))
                conn.commit()
                await interaction.followup.send(f"❌ Error banking winnings, but your balance has been updated: {format_money(balance)}", ephemeral=True)
            except:
                await interaction.followup.send(f"❌ Critical error banking winnings: {str(e)}\nPlease contact an admin with your game details.", ephemeral=True)
    
    async def on_timeout(self):
        """Called when the view times out - refund ONLY the initial bet if game was not resolved."""
        try:
            # Only refund if the game was not already resolved (banked or lost)
            if self.game_resolved:
                print(f"⏰ FlipChase timeout: Game already resolved for user {self.user_id}, no refund needed")
                return
            
            # Get user data and refund their INITIAL BET only (not winnings)
            user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.user_id)
            
            # Only refund the initial bet (player forfeits potential winnings on timeout)
            balance += self.initial_bet
            # Do NOT add to gambled stats since they timed out without completing the game
            
            # Update database
            c.execute(
                "UPDATE users SET balance=? WHERE user_id=?",
                (balance, self.user_id)
            )
            conn.commit()
            
            # Remove from active games
            if self.user_id in active_flip_chase:
                del active_flip_chase[self.user_id]
                
            print(f"⏰ FlipChase timeout: Refunded initial bet {format_money(self.initial_bet)} to user {self.user_id} (forfeited {format_money(self.current_winnings - self.initial_bet)} in winnings)")
        except Exception as e:
            print(f"❌ Error in FlipChase timeout handler: {str(e)}")
            item.disabled = True
        
        await interaction.message.edit(embed=embed, view=self)

@bot.command(name="flipchase")
async def flipchase(ctx, amount: str = None):
    """Flip & Chase: Win and chase to double, or bank your winnings anytime!"""
    try:
        if amount is None:
            await ctx.send("❌ Usage: `!flipchase <amount>`\nExample: `!flipchase 10m`")
            return

        # Check if user already has an active game
        if ctx.author.id in active_flip_chase:
            await ctx.send("❌ You already have an active Flip & Chase game! Bank or chase your current winnings first.")
            return

        value = parse_money(amount)
        if value <= 0:
            await ctx.send("❌ Invalid amount format! Use k, m, or b (e.g., 10m, 5k).")
            return

        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(ctx.author.id)

        if value > balance:
            await ctx.send("❌ You cannot gamble more than your balance.")
            return
        
        # Check for rapid betting (fraud detection)
        is_rapid = await check_rapid_betting(ctx.author.id)
        if is_rapid:
            await send_fraud_alert(
                bot,
                ctx.author,
                "Rapid Betting Detected",
                f"User placed {RAPID_BET_THRESHOLD}+ bets in 60 seconds\nBet Amount: {value:,}$\nGame: Flip & Chase"
            )
        
        # Check for high bet (fraud detection)
        if value >= HIGH_BET_THRESHOLD:
            await log_user_activity(
                bot,
                ctx.author,
                "High Value Bet",
                f"Amount: {value:,}$\nGame: Flip & Chase\nBalance: {balance:,}$"
            )

        # Deduct initial bet from balance
        balance -= value
        
        # Update database
        c.execute(
            "UPDATE users SET balance=? WHERE user_id=?",
            (balance, ctx.author.id)
        )
        conn.commit()
        
        # First flip to start the game using provably fair
        result, client_seed, nonce, seed_hash = provably_fair.place_bet(
            ctx.author.id,
            "flipchase",
            value,
            2  # modulo 2 for coinflip: 0=heads, 1=tails
        )
        
        outcome = "heads" if result == 0 else "tails"
        player_choice = "heads" if result == 0 else "tails"  # In flipchase, we always match the outcome for first flip
        won = True  # First flip always wins to start the chase
        
        if won:
            # Won first flip - offer to chase or bank
            current_winnings = value * 2
            active_flip_chase[ctx.author.id] = True
            
            embed = discord.Embed(
                title="🎉 First Flip Won!",
                description=f"**You won!** The coin landed on **{outcome}**!",
                color=discord.Color.green()
            )
            embed.add_field(name="Current Winnings", value=f"{format_money(current_winnings)}", inline=True)
            embed.add_field(name="Initial Bet", value=f"{format_money(value)}", inline=True)
            embed.add_field(name="Potential Next Win", value=f"{format_money(current_winnings * 2)}", inline=True)
            embed.set_footer(text="Chase to double your winnings or Bank to keep them safe!")
            
            view = FlipChaseView(ctx.author.id, current_winnings, value, 1)
            await ctx.send(embed=embed, view=view)
        else:
            # Lost first flip - game over immediately
            gambled += value
            total_gambled += value
            
            # Update database
            c.execute(
                "UPDATE users SET gambled=?, total_gambled=? WHERE user_id=?",
                (gambled, total_gambled, ctx.author.id)
            )
            conn.commit()
            
            # Log the loss
            await log_bet_activity(ctx.author.id, value, "flipchase", "loss")
            
            remaining = max(required_gamble - gambled, 0)
            
            embed = discord.Embed(
                title="💀 First Flip Lost!",
                description=f"**You lost!** The coin landed on **{outcome}**.",
                color=discord.Color.red()
            )
            embed.add_field(name="Lost Amount", value=f"{format_money(value)}", inline=True)
            embed.add_field(name="New Balance", value=f"{format_money(balance)}", inline=True)
            embed.add_field(name="Required Gamble", value=f"{format_money(required_gamble)}", inline=True)
            embed.add_field(name="Remaining", value=f"{format_money(remaining)}", inline=True)
            
            await ctx.send(embed=embed)
            
    except Exception as e:
        await ctx.send(f"❌ Error during flip & chase: {str(e)}")

# -----------------------------
# 🎰 SLOTS GAMBLING GAME
# -----------------------------
class SlotsView(View):
    def __init__(self, user_id, bet_amount, ctx):
        super().__init__(timeout=120)  # Increased from 60 to 120 seconds
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.ctx = ctx
        self.spun = False
    
    async def perform_spin(self, interaction: discord.Interaction):
        """Perform the slot machine spin logic."""
        try:
            # Slot symbols with weights for balanced gameplay
            symbols = ["🍒", "🍋", "🍊", "🍇", "💎", "⭐", "7️⃣"]
            
            # Generate 3x3 grid using provably fair
            results, client_seed, nonce, seed_hash = provably_fair.place_bet_multiple(
                self.user_id,
                "slots",
                self.bet_amount,
                9,  # 9 results for 3x3 grid
                7   # modulo 7 for symbol selection
            )
            
            # Map results to symbols and create grid
            grid = [
                [symbols[results[0]], symbols[results[1]], symbols[results[2]]],
                [symbols[results[3]], symbols[results[4]], symbols[results[5]]],
                [symbols[results[6]], symbols[results[7]], symbols[results[8]]]
            ]
            
            # Check for winning patterns and calculate multiplier
            win_multiplier = 0
            win_patterns = []
            
            # Check horizontal lines
            for i, row in enumerate(grid):
                if row[0] == row[1] == row[2]:
                    multiplier = get_symbol_multiplier(row[0])
                    win_multiplier = max(win_multiplier, multiplier)
                    win_patterns.append(f"Row {i+1}: {row[0]}{row[1]}{row[2]}")
            
            # Check vertical lines
            for col in range(3):
                if grid[0][col] == grid[1][col] == grid[2][col]:
                    multiplier = get_symbol_multiplier(grid[0][col])
                    win_multiplier = max(win_multiplier, multiplier)
                    win_patterns.append(f"Column {col+1}: {grid[0][col]}{grid[1][col]}{grid[2][col]}")
            
            # Check diagonal (top-left to bottom-right)
            if grid[0][0] == grid[1][1] == grid[2][2]:
                multiplier = get_symbol_multiplier(grid[0][0])
                win_multiplier = max(win_multiplier, multiplier)
                win_patterns.append(f"Diagonal \\: {grid[0][0]}{grid[1][1]}{grid[2][2]}")
            
            # Check diagonal (top-right to bottom-left)
            if grid[0][2] == grid[1][1] == grid[2][0]:
                multiplier = get_symbol_multiplier(grid[0][2])
                win_multiplier = max(win_multiplier, multiplier)
                win_patterns.append(f"Diagonal /: {grid[0][2]}{grid[1][1]}{grid[2][0]}")
            
            # Calculate winnings
            user_id_db, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(self.user_id)
            
            # Check if user has enough balance
            if self.bet_amount > balance:
                await interaction.response.send_message(f"❌ Insufficient balance! You have {balance:,}$ but need {self.bet_amount:,}$", ephemeral=True)
                return None
            
            if win_multiplier > 0:
                # Winner!
                winnings = int(self.bet_amount * win_multiplier)
                balance += winnings
                result_emoji = "🎉"
                result_text = f"**WINNER!** x{win_multiplier:.1f} multiplier\nYou won {winnings:,}$!"
                color = discord.Color.gold()
            else:
                # Lost
                balance -= self.bet_amount
                result_emoji = "💀"
                result_text = f"No matches. You lost {self.bet_amount:,}$"
                color = discord.Color.red()
            
            # Update gambling stats
            gambled += self.bet_amount
            total_gambled += self.bet_amount
            
            c.execute(
                "UPDATE users SET balance=?, gambled=?, total_gambled=? WHERE user_id=?",
                (balance, gambled, total_gambled, self.user_id)
            )
            conn.commit()
            
            remaining = max(required_gamble - gambled, 0)
            
            # Create result embed
            grid_display = "\n".join([" ".join(row) for row in grid])
            
            embed = discord.Embed(
                title=f"{result_emoji} Slots Result {result_emoji}",
                description=f"```\n{grid_display}\n```\n{result_text}",
                color=color
            )
            
            if win_patterns:
                embed.add_field(name="💰 Winning Patterns", value="\n".join(win_patterns), inline=False)
            
            embed.add_field(name="Balance", value=f"{balance:,}$", inline=True)
            embed.add_field(name="Bet Amount", value=f"{self.bet_amount:,}$", inline=True)
            embed.add_field(name="Remaining Gamble", value=f"{remaining:,}$", inline=True)
            
            # Add provably fair info
            embed.add_field(
                name="🔐 Provably Fair",
                value=f"Nonce: `{nonce}` | Client: `{client_seed[:16]}...`\nSeed Hash: `{seed_hash[:16]}...`",
                inline=False
            )
            embed.set_footer(text=f"Click 'Spin Again' to play another round! Use !verify to verify fairness.")
            
            return embed
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error during spin: {str(e)}", ephemeral=True)
            return None
    
    @discord.ui.button(label="🎰 Spin", style=discord.ButtonStyle.green, custom_id="spin_slots")
    async def spin_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your slot machine!", ephemeral=True)
            return
        
        if self.spun:
            await interaction.response.send_message("❌ You already spun! Click 'Spin Again' to play another round.", ephemeral=True)
            return
        
        # Disable the spin button and enable spin again button
        button.disabled = True
        self.spun = True
        
        # Perform the spin
        embed = await self.perform_spin(interaction)
        if embed:
            # Enable the Spin Again button
            for item in self.children:
                if isinstance(item, Button) and item.custom_id == "spin_again_slots":
                    item.disabled = False
            
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="🔄 Spin Again", style=discord.ButtonStyle.blurple, custom_id="spin_again_slots", disabled=True)
    async def spin_again_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your slot machine!", ephemeral=True)
            return
        
        # Perform another spin with the same bet
        embed = await self.perform_spin(interaction)
        if embed:
            await interaction.response.edit_message(embed=embed, view=self)
    
    async def on_timeout(self):
        """Called when the view times out."""
        # Disable all buttons
        for item in self.children:
            item.disabled = True

def get_symbol_multiplier(symbol):
    """Return the multiplier for a given symbol."""
    multipliers = {
        "7️⃣": 5.0,    # Jackpot!
        "💎": 3.0,    # Diamond
        "⭐": 2.5,    # Star
        "🍇": 2.0,    # Grape
        "🍊": 1.8,    # Orange
        "🍋": 1.5,    # Lemon
        "🍒": 1.2,    # Cherry
    }
    return multipliers.get(symbol, 0)

# Rock Paper Scissors View with buttons
class RPSView(discord.ui.View):
    def __init__(self, user_id, bet_amount, house_choice, client_seed, nonce, seed_hash):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.house_choice = house_choice
        self.client_seed = client_seed
        self.nonce = nonce
        self.seed_hash = seed_hash
        self.responded = False
        
    async def on_timeout(self):
        # Disable all buttons on timeout
        for item in self.children:
            item.disabled = True
        
    @discord.ui.button(label="🪨 Rock", style=discord.ButtonStyle.primary, custom_id="rps_rock")
    async def rock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_choice(interaction, 0, "🪨 Rock")
    
    @discord.ui.button(label="📄 Paper", style=discord.ButtonStyle.primary, custom_id="rps_paper")
    async def paper_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_choice(interaction, 1, "📄 Paper")
    
    @discord.ui.button(label="✂️ Scissors", style=discord.ButtonStyle.primary, custom_id="rps_scissors")
    async def scissors_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_choice(interaction, 2, "✂️ Scissors")
    
    async def handle_choice(self, interaction: discord.Interaction, player_choice, player_choice_text):
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
                return
            
            if self.responded:
                await interaction.response.send_message("❌ You already made your choice!", ephemeral=True)
                return
            
            self.responded = True
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            # Determine winner
            choices_text = ["🪨 Rock", "📄 Paper", "✂️ Scissors"]
            house_choice_text = choices_text[self.house_choice]
            
            # 0 = Rock, 1 = Paper, 2 = Scissors
            # Rock beats Scissors, Paper beats Rock, Scissors beats Paper
            if player_choice == self.house_choice:
                result = "tie"
                result_text = "🤝 It's a Tie!"
                result_color = discord.Color.yellow()
                payout = self.bet_amount  # Get bet back
                net_profit = self.bet_amount  # Return the bet to player
            elif (player_choice == 0 and self.house_choice == 2) or \
                 (player_choice == 1 and self.house_choice == 0) or \
                 (player_choice == 2 and self.house_choice == 1):
                result = "win"
                result_text = "🎉 You Win!"
                result_color = discord.Color.green()
                payout = self.bet_amount * 2
                net_profit = self.bet_amount
            else:
                result = "loss"
                result_text = "😢 You Lose!"
                result_color = discord.Color.red()
                payout = 0
                net_profit = 0  # Bet already deducted, so no additional loss
            
            # Get current balance (after bet was already deducted)
            user = get_user(self.user_id)
            current_balance = user[1]
            new_balance = current_balance + net_profit
            
            # Update balance for win or tie (but not loss since bet already deducted)
            if result != "loss":
                update_balance(self.user_id, net_profit)
            
            # Create result embed
            result_embed = discord.Embed(
                title="🎮 Rock Paper Scissors - Result",
                description=result_text,
                color=result_color
            )
            
            result_embed.add_field(
                name="Your Choice",
                value=player_choice_text,
                inline=True
            )
            
            result_embed.add_field(
                name="House Choice",
                value=house_choice_text,
                inline=True
            )
            
            result_embed.add_field(
                name="\u200b",
                value="\u200b",
                inline=True
            )
            
            result_embed.add_field(
                name="Bet Amount",
                value=format_money(self.bet_amount),
                inline=True
            )
            
            result_embed.add_field(
                name="Payout",
                value=format_money(payout),
                inline=True
            )
            
            result_embed.add_field(
                name="Net Profit",
                value=format_money(net_profit),
                inline=True
            )
            
            result_embed.add_field(
                name="New Balance",
                value=format_money(new_balance),
                inline=False
            )
            
            # Add provably fair info
            result_embed.add_field(
                name="🔐 Provably Fair",
                value=f"Nonce: `{self.nonce}` | Client: `{self.client_seed[:16]}...`\n"
                      f"Seed Hash: `{self.seed_hash[:32]}...`\n"
                      f"Use `!verify` to verify fairness",
                inline=False
            )
            
            result_embed.set_footer(text=f"Eli's MM Service• Today at {datetime.now().strftime('%I:%M %p')}")
            
            await interaction.response.edit_message(embed=result_embed, view=self)
            
        except Exception as e:
            print(f"❌ Error in RPS button handler: {str(e)}")
            await interaction.response.send_message(f"❌ Error processing your choice: {str(e)}", ephemeral=True)

@bot.command(name="rps")
async def rockpaperscissors(ctx, amount: str = None):
    """Play Rock Paper Scissors against the house! Choose wisely."""
    try:
        if amount is None:
            await ctx.send("❌ Usage: `!rps <amount>`\nExample: `!rps 10m`")
            return
        
        # Parse bet amount
        bet = parse_money(amount)
        if bet is None:
            await ctx.send("❌ Invalid amount! Use formats like: `10k`, `5m`, `1b`")
            return
        
        min_bet = 100
        if bet < min_bet:
            await ctx.send(f"❌ Minimum bet is {format_money(min_bet)}!")
            return
        
        # Check balance
        user = get_user(ctx.author.id)
        if user[1] < bet:
            await ctx.send(f"❌ Insufficient balance! You have {format_money(user[1])}, but need {format_money(bet)}")
            return
        
        # Deduct bet
        new_balance = user[1] - bet
        set_balance(ctx.author.id, new_balance)
        
        # Track gambled amount
        add_gambled(ctx.author.id, bet)
        
        # Generate provably fair result
        result, client_seed, nonce, seed_hash = provably_fair.place_bet(
            ctx.author.id,
            "rps",
            bet,
            modulo=3  # 0 = Rock, 1 = Paper, 2 = Scissors
        )
        
        house_choice = result  # This is the house's choice (0, 1, or 2)
        
        # Create initial embed
        embed = discord.Embed(
            title="🎮 Rock Paper Scissors",
            description=f"Place your bet: **{format_money(bet)}**\n\n"
                       f"Choose your move below! (60 seconds)\n"
                       f"House will reveal their choice after you pick",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🪨 Rock vs 📄 Paper",
            value="Paper wins",
            inline=True
        )
        
        embed.add_field(
            name="📄 Paper vs ✂️ Scissors",
            value="Scissors wins",
            inline=True
        )
        
        embed.add_field(
            name="✂️ Scissors vs 🪨 Rock",
            value="Rock wins",
            inline=True
        )
        
        embed.add_field(
            name="Win",
            value=f"2x payout ({format_money(bet * 2)})",
            inline=True
        )
        
        embed.add_field(
            name="Tie",
            value=f"Get bet back ({format_money(bet)})",
            inline=True
        )
        
        embed.add_field(
            name="Lose",
            value=f"Lose bet ({format_money(bet)})",
            inline=True
        )
        
        # Add provably fair info
        embed.add_field(
            name="🔐 Provably Fair",
            value=f"Nonce: `{nonce}` | Client: `{client_seed[:16]}...`\n"
                  f"Seed Hash: `{seed_hash[:32]}...`\n"
                  f"Use `!verify` to verify fairness",
            inline=False
        )
        
        embed.set_footer(text=f"Eli's MM Service• Today at {datetime.now().strftime('%I:%M %p')}")
        
        # Create view with buttons
        view = RPSView(ctx.author.id, bet, house_choice, client_seed, nonce, seed_hash)
        
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        print(f"❌ Error in RPS command: {str(e)}")
        await ctx.send(f"❌ Error starting Rock Paper Scissors: {str(e)}")

@bot.command(name="slots")
async def slots(ctx, amount: str = None):
    """Play the slots machine! Match 3 symbols in a row, column, or diagonal to win."""
    try:
        if amount is None:
            await ctx.send("❌ Usage: `!slots <amount>`\nExample: `!slots 10m`")
            return
        
        value = parse_money(amount)
        if value <= 0:
            await ctx.send("❌ Invalid amount format! Use k, m, or b (e.g., 10m, 5k).")
            return
        
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(ctx.author.id)
        
        if value > balance:
            await ctx.send("❌ You cannot gamble more than your balance.")
            return
        
        # Create initial embed
        embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            description=f"**Bet Amount:** {value:,}$\n\n**Symbols:**\n"
                       f"7️⃣ = x5.0 (Jackpot!)\n💎 = x3.0\n⭐ = x2.5\n🍇 = x2.0\n"
                       f"🍊 = x1.8\n🍋 = x1.5\n🍒 = x1.2\n\n"
                       f"**How to Win:**\nMatch 3 symbols in a row, column, or diagonal!\n\n"
                       f"Click the button below to spin!",
            color=discord.Color.purple()
        )
        embed.add_field(name="Current Balance", value=f"{balance:,}$", inline=True)
        embed.add_field(name="Remaining Gamble", value=f"{max(required_gamble - gambled, 0):,}$", inline=True)
        embed.set_footer(text="Good luck! 🍀")
        
        view = SlotsView(ctx.author.id, value, ctx)
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Error starting slots: {str(e)}")

@bot.command(name="deposit")
async def deposit(ctx, user: discord.Member = None, amount: str = None):
    """Owner command to deposit funds to a user."""
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can deposit.")
        return
    
    if user is None or amount is None:
        await ctx.send("❌ Usage: `!deposit @user <amount>`")
        return
    
    try:
        value = parse_money(amount)
        if value < MIN_DEPOSIT:
            await ctx.send(f"❌ Minimum deposit is {MIN_DEPOSIT:,}$")
            return
        
        # Get balance before deposit
        user_id, bal_before, req, gambled, _, _, _ = get_user(user.id)
        
        # Update balance
        update_balance(user.id, value)
        user_id, bal, req, gambled, _, _, _ = get_user(user.id)
        remaining = max(req - gambled, 0)
        
        # Log transaction
        await log_transaction(
            user.id,
            "DEPOSIT",
            value,
            bal_before,
            bal,
            f"Deposited by owner {ctx.author.name} ({ctx.author.id})"
        )
        
        # Log to audit channel
        await log_user_activity(
            bot,
            user,
            "Deposit Received",
            f"Amount: {value:,}$\nDeposited by: {ctx.author.mention}\nPrevious Balance: {bal_before:,}$\nNew Balance: {bal:,}$\nRequired Gamble: {req:,}$"
        )
        
        await ctx.send(f"✅ Added {value:,}$ to {user.mention}\nBalance: {bal:,}$ | Required Gamble: {req:,}$ | Remaining: {remaining:,}$")
    except Exception as e:
        await ctx.send(f"❌ Error depositing funds: {str(e)}")

@bot.command(name="viewamount")
async def viewamount(ctx, user: discord.Member = None):
    """Owner command to view a user's balance."""
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can use this.")
        return
    
    if user is None:
        await ctx.send("❌ Usage: `!viewamount @user`")
        return
    
    try:
        user_id, bal, req, gambled, _, _, _ = get_user(user.id)
        remaining = max(req - gambled, 0)
        await ctx.send(f"💰 **{user.display_name}'s Gambling Amount**\nBalance: `{bal:,}$`\nRequired Gamble: `{req:,}$`\nRemaining: `{remaining:,}$`")
    except Exception as e:
        await ctx.send(f"❌ Error fetching user balance: {str(e)}")

@bot.command(name="amountall")
async def amountall(ctx, page: int = 1):
    """Owner command to view all user balances."""
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can use this.")
        return
    
    try:
        c.execute("SELECT user_id, balance FROM users ORDER BY user_id")
        users = c.fetchall()
        
        if not users:
            await ctx.send("❌ No users found in database.")
            return
        
        total_pages = calculate_total_pages(len(users), USERS_PER_PAGE)
        page = max(1, min(page, total_pages))
        start = (page - 1) * USERS_PER_PAGE
        end = start + USERS_PER_PAGE
        user_list = users[start:end]
        description = "\n".join(f"<@{uid}>: {bal:,}$" for uid, bal in user_list) if user_list else "No users on this page."
        await ctx.send(embed=discord.Embed(
            title=f"💰 Gambling Balances - Page {page}/{total_pages}",
            description=description,
            color=discord.Color.green()
        ))
    except Exception as e:
        await ctx.send(f"❌ Error fetching balances: {str(e)}")

@bot.command(name="gambledall")
async def gambledall(ctx):
    """Owner command to view total gambling statistics across all players."""
    if not is_owner(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        return
    
    try:
        # Get total gambled statistics
        c.execute("SELECT SUM(total_gambled), SUM(gambled) FROM users")
        result = c.fetchone()
        total_gambled_alltime = result[0] if result[0] is not None else 0
        current_session_gambled = result[1] if result[1] is not None else 0
        
        # Get count of active gamblers (players who have gambled at least once)
        c.execute("SELECT COUNT(*) FROM users WHERE total_gambled > 0")
        active_gamblers = c.fetchone()[0]
        
        # Get total registered players
        c.execute("SELECT COUNT(*) FROM users")
        total_players = c.fetchone()[0]
        
        # Get top gambler
        c.execute("SELECT user_id, total_gambled FROM users ORDER BY total_gambled DESC LIMIT 1")
        top_result = c.fetchone()
        top_gambler_id = top_result[0] if top_result else None
        top_gambled_amount = top_result[1] if top_result else 0
        
        # Try to fetch top gambler username
        top_gambler_display = "N/A"
        if top_gambler_id and top_gambled_amount > 0:
            try:
                top_user = await bot.fetch_user(top_gambler_id)
                top_gambler_display = f"{top_user.mention} - {format_money(top_gambled_amount)}"
            except:
                top_gambler_display = f"<@{top_gambler_id}> - {format_money(top_gambled_amount)}"
        
        # Calculate average gambled per active gambler
        avg_gambled = total_gambled_alltime // active_gamblers if active_gamblers > 0 else 0
        
        # Create embed
        embed = discord.Embed(
            title="💰 Total Gambling Statistics",
            description="Gambling activity across all players",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📊 Total Gambled (All-Time)",
            value=format_money(total_gambled_alltime),
            inline=False
        )
        
        embed.add_field(
            name="🎲 Active Gamblers",
            value=f"{active_gamblers} players have gambled",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Top Gambler",
            value=top_gambler_display,
            inline=True
        )
        
        embed.add_field(
            name="📈 Total Players",
            value=f"{total_players} registered users",
            inline=True
        )
        
        embed.add_field(
            name="💵 Average Gambled per Player",
            value=format_money(avg_gambled),
            inline=False
        )
        
        embed.add_field(
            name="📊 Current Session Gambled",
            value=format_money(current_session_gambled),
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error fetching gambling statistics: {str(e)}")
        print(f"Error in gambledall command: {e}")

@bot.command(name="resetgamblingall")
async def resetgamblingall(ctx):
    """Owner command to reset all gambling statistics (total_gambled and gambled) for all users."""
    if not is_owner(ctx.author):
        await ctx.send("❌ You don't have permission to use this command.")
        return
    
    try:
        # Get count before reset
        c.execute("SELECT COUNT(*) FROM users WHERE total_gambled > 0 OR gambled > 0")
        affected_users = c.fetchone()[0]
        
        # Reset all gambling statistics
        c.execute("UPDATE users SET total_gambled = 0, gambled = 0")
        conn.commit()
        
        # Create confirmation embed
        embed = discord.Embed(
            title="🔄 Gambling Statistics Reset",
            description="All gambling statistics have been successfully reset.",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="✅ Reset Complete",
            value=f"Reset gambling stats for {affected_users} users",
            inline=False
        )
        
        embed.add_field(
            name="📊 What was reset:",
            value="• Total Gambled (All-Time): Set to 0\n• Current Session Gambled: Set to 0",
            inline=False
        )
        
        await ctx.send(embed=embed)
        print(f"Owner {ctx.author} reset all gambling statistics for {affected_users} users")
        
    except Exception as e:
        await ctx.send(f"❌ Error resetting gambling statistics: {str(e)}")
        print(f"Error in resetgamblingall command: {e}")

@bot.command(name="leaderboards", aliases=["lb"])
async def leaderboards(ctx):
    """Display the top 10 players by balance for competitive ranking."""
    try:
        # Get top 10 players by balance
        c.execute("""
            SELECT user_id, balance, total_gambled 
            FROM users 
            WHERE balance > 0 
            ORDER BY balance DESC 
            LIMIT 10
        """)
        top_players = c.fetchall()
        
        if not top_players:
            await ctx.send("📊 No players with balance found yet!")
            return
        
        # Create embed
        embed = discord.Embed(
            title="🏆 Gambling Leaderboard",
            description="Top 10 players by balance",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        # Build leaderboard text
        leaderboard_text = ""
        medals = ["🥇", "🥈", "🥉"]
        
        for idx, (user_id, balance, total_gambled) in enumerate(top_players, 1):
            # Try to fetch username
            try:
                user = await bot.fetch_user(user_id)
                username = user.name
            except:
                username = f"User {user_id}"
            
            # Add medal for top 3
            if idx <= 3:
                medal = medals[idx - 1]
            else:
                medal = f"#{idx}"
            
            # Format the entry
            leaderboard_text += f"{medal} **{username}**\n"
            leaderboard_text += f"   💰 Balance: {format_money(balance)}\n"
            leaderboard_text += f"   🎲 Gambled: {format_money(total_gambled)}\n\n"
        
        embed.add_field(
            name="🎯 Top Players",
            value=leaderboard_text,
            inline=False
        )
        
        embed.set_footer(text="Compete to reach the top! Use gambling games to climb the ranks.")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error fetching leaderboard: {str(e)}")
        print(f"Error in leaderboard command: {e}")

@bot.command(name="wipeamount")
async def wipeamount(ctx, user: discord.Member = None):
    """Owner command to wipe a user's balance."""
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can use this.")
        return
    
    if user is None:
        await ctx.send("❌ Usage: `!wipeamount @user`")
        return
    
    try:
        c.execute("UPDATE users SET balance=0, required_gamble=0, gambled=0 WHERE user_id=?", (user.id,))
        conn.commit()
        await ctx.send(f"✅ {user.mention}'s balance wiped.")
    except Exception as e:
        await ctx.send(f"❌ Error wiping balance: {str(e)}")

@bot.command(name="trackpet")
async def trackpet(ctx, pet_id=None):
    """Owner command to look up a pet by its ID from stock."""
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can use this.")
        return
    
    if pet_id is None:
        await ctx.send("❌ Usage: `!trackpet <pet_id>` or `!trackpet #<pet_id>`")
        return
    
    try:
        # Handle both formats: "7" and "#7"
        pet_id_str = str(pet_id).lstrip('#')
        
        # Convert pet_id to integer
        try:
            pet_id_int = int(pet_id_str)
        except (ValueError, TypeError):
            await ctx.send(f"❌ Invalid pet ID. Please provide a valid number.")
            return
        
        # Query stock_items table for the pet
        c.execute("SELECT pet_name, account_stored FROM stock_items WHERE id=?", (pet_id_int,))
        result = c.fetchone()
        if result is None:
            await ctx.send(f"❌ Pet with ID #{pet_id_int} not found in stock.")
            return
        pet_name, account = result
        await ctx.send(f"🐾 **Pet ID #{pet_id_int}:** {pet_name} is in **{account}**")
    except Exception as e:
        await ctx.send(f"❌ Error tracking pet: {str(e)}")

@bot.command(name="petids")
async def petids(ctx):
    """Owner command to list all pets in stock and current wheel prize."""
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can use this.")
        return
    
    try:
        # Show current wheel prize first if set
        global current_special_prize
        if current_special_prize:
            wheel_embed = discord.Embed(
                title="🎰 Current Wheel Prize",
                description=f"**{current_special_prize['pet_name']}**\n"
                           f"Account: {current_special_prize.get('account', 'N/A')}\n"
                           f"Wheel Prize ID: #{current_special_prize['pet_id']}",
                color=discord.Color.gold()
            )
            wheel_embed.set_footer(text="This prize is separate from stock items and cannot be purchased")
            await ctx.send(embed=wheel_embed)
        
        # Query stock_items table for all pets
        c.execute("SELECT id, pet_name, account_stored FROM stock_items ORDER BY id")
        pets = c.fetchall()
        if not pets:
            if not current_special_prize:
                await ctx.send("📦 No pets currently in stock and no wheel prize set.")
            return
        
        embed = discord.Embed(
            title="🐾 Pets in Stock",
            color=discord.Color.purple()
        )
        
        # Add pets to embed, handling pagination if needed
        description_lines = []
        for pet_id, pet_name, account in pets:
            description_lines.append(f"**Pet ID #{pet_id}:** {pet_name} | Account: {account}")
        
        # Discord embed description limit is 4096 characters
        description = "\n".join(description_lines)
        if len(description) > 4096:
            # Split into multiple embeds if too large
            chunks = []
            current_chunk = []
            current_length = 0
            for line in description_lines:
                # Calculate the length this line would add (including newline separator if not first)
                if current_chunk:
                    line_length = len(line) + 1  # +1 for newline separator
                else:
                    line_length = len(line)  # First line, no separator
                
                if current_length + line_length > 4096:
                    # Would exceed limit, save current chunk and start new one
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [line]
                    current_length = len(line)
                else:
                    current_chunk.append(line)
                    current_length += line_length
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            
            # Send first embed with title
            embed.description = chunks[0]
            await ctx.send(embed=embed)
            
            # Send remaining chunks as continuation embeds
            for i, chunk in enumerate(chunks[1:], 2):
                continuation_embed = discord.Embed(
                    title=f"🐾 Pets in Stock (continued {i})",
                    description=chunk,
                    color=discord.Color.purple()
                )
                await ctx.send(embed=continuation_embed)
        else:
            embed.description = description
            await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error fetching pets: {str(e)}")

# -----------------------------
# STOCK MARKET COMMANDS
# -----------------------------
@bot.command(name="stocks")
async def stocks(ctx, category: str = None):
    """List all available stocks or stocks in a specific category."""
    try:
        if category:
            # Show stocks in specific category
            c.execute("""
                SELECT ticker, name, category, current_price, base_price 
                FROM stocks 
                WHERE LOWER(category) = LOWER(?)
                ORDER BY ticker
            """, (category,))
            stocks_data = c.fetchall()
            
            if not stocks_data:
                await ctx.send(f"❌ No stocks found in category '{category}'. Use `!stocks` to see all categories.")
                return
            
            title = f"📈 {category} Stocks"
        else:
            # Show all stocks grouped by category
            stocks_data = get_all_stocks()
            title = "📈 Stock Market"
        
        if not stocks_data:
            await ctx.send("❌ No stocks available in the market.")
            return
        
        # Group stocks by category for better display
        categories = {}
        for stock in stocks_data:
            stock_id, ticker, name, cat, base_price, current_price, total_shares, available_shares = stock
            if cat not in categories:
                categories[cat] = []
            
            # Calculate price change percentage
            price_change = ((current_price - base_price) / base_price) * 100
            change_emoji = "📈" if price_change > 0 else "📉" if price_change < 0 else "➡️"
            
            categories[cat].append(
                f"**{ticker}** - {name}\n"
                f"💰 Price: {format_money(int(current_price))} {change_emoji} {price_change:+.2f}%"
            )
        
        # Create embed
        embed = discord.Embed(
            title=title,
            description="Use `!buy <ticker> <quantity>` to purchase stocks\n"
                       "Use `!sell <ticker> <quantity>` to sell stocks\n"
                       "Use `!portfolio` to view your holdings",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Add fields for each category
        for cat, stock_list in categories.items():
            field_value = "\n\n".join(stock_list)
            # Split if too long
            if len(field_value) > 1024:
                # Split into multiple fields
                chunks = []
                current_chunk = []
                current_length = 0
                for stock_info in stock_list:
                    if current_length + len(stock_info) + 2 > 1024:
                        chunks.append("\n\n".join(current_chunk))
                        current_chunk = [stock_info]
                        current_length = len(stock_info)
                    else:
                        current_chunk.append(stock_info)
                        current_length += len(stock_info) + 2
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                
                for i, chunk in enumerate(chunks):
                    field_name = f"📊 {cat}" if i == 0 else f"📊 {cat} (cont.)"
                    embed.add_field(name=field_name, value=chunk, inline=False)
            else:
                embed.add_field(name=f"📊 {cat}", value=field_value, inline=False)
        
        embed.set_footer(text="Prices update every hour | Virtual stock market system")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error fetching stocks: {str(e)}")
        print(f"Error in stocks command: {e}")

@bot.command(name="buy")
async def buy_stock(ctx, ticker: str = None, quantity: str = None):
    """Buy stocks from the market."""
    if ticker is None or quantity is None:
        await ctx.send("❌ Usage: `!buy <ticker> <quantity>`\nExample: `!buy TECH 10`")
        return
    
    try:
        # Parse quantity
        qty = parse_money(quantity)
        if qty <= 0:
            await ctx.send("❌ Invalid quantity. Please enter a positive number.")
            return
        
        # Get stock data
        stock = get_stock_by_ticker(ticker)
        if not stock:
            await ctx.send(f"❌ Stock '{ticker.upper()}' not found. Use `!stocks` to see available stocks.")
            return
        
        stock_id, ticker_db, name, category, base_price, current_price, total_shares, available_shares = stock
        
        # Check if enough shares available
        if qty > available_shares:
            await ctx.send(f"❌ Not enough shares available. Only {available_shares:,} shares of {ticker.upper()} are available.")
            return
        
        # Calculate total cost
        total_cost = int(current_price * qty)
        
        # Check user balance
        user_data = get_user(ctx.author.id)
        user_id, balance, req, gambled, total_gambled, total_withdrawn = user_data
        
        if balance < total_cost:
            await ctx.send(f"❌ Insufficient funds! You need {format_money(total_cost)} but only have {format_money(balance)}.")
            return
        
        # Execute purchase
        # Update user balance
        update_balance(ctx.author.id, -total_cost)
        
        # Update or create holding
        c.execute("SELECT * FROM holdings WHERE user_id=? AND stock_id=?", (ctx.author.id, stock_id))
        existing_holding = c.fetchone()
        
        if existing_holding:
            # Update existing holding
            holding_id, _, _, old_qty, old_avg_price = existing_holding
            new_qty = old_qty + qty
            # Calculate new average purchase price
            new_avg_price = ((old_avg_price * old_qty) + (current_price * qty)) / new_qty
            c.execute("""
                UPDATE holdings 
                SET quantity=?, avg_purchase_price=?
                WHERE id=?
            """, (new_qty, new_avg_price, holding_id))
        else:
            # Create new holding
            c.execute("""
                INSERT INTO holdings (user_id, stock_id, quantity, avg_purchase_price)
                VALUES (?, ?, ?, ?)
            """, (ctx.author.id, stock_id, qty, current_price))
        
        # Update available shares
        c.execute("""
            UPDATE stocks 
            SET available_shares = available_shares - ?
            WHERE id=?
        """, (qty, stock_id))
        
        conn.commit()
        
        # Apply demand-based price increase
        new_price = apply_demand_price_change(stock_id, True)
        
        # Log transaction
        await log_transaction(
            ctx.author.id, "STOCK_PURCHASE", total_cost, balance, balance - total_cost,
            f"Bought {qty} shares of {ticker.upper()} at {format_money(int(current_price))} per share"
        )
        
        # Create success embed
        embed = discord.Embed(
            title="✅ Stock Purchase Successful",
            description=f"You purchased **{qty:,}** shares of **{ticker.upper()}**",
            color=discord.Color.green()
        )
        embed.add_field(name="Stock", value=f"{ticker.upper()} - {name}", inline=True)
        embed.add_field(name="Quantity", value=f"{qty:,} shares", inline=True)
        embed.add_field(name="Price per Share", value=format_money(int(current_price)), inline=True)
        embed.add_field(name="Total Cost", value=format_money(total_cost), inline=True)
        embed.add_field(name="New Balance", value=format_money(balance - total_cost), inline=True)
        embed.add_field(name="New Stock Price", value=f"{format_money(int(new_price))} (+0.5%)", inline=True)
        embed.set_footer(text="Use !portfolio to view all your holdings")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error processing purchase: {str(e)}")
        print(f"Error in buy command: {e}")

@bot.command(name="sell")
async def sell_stock(ctx, ticker: str = None, quantity: str = None):
    """Sell stocks from your portfolio."""
    if ticker is None or quantity is None:
        await ctx.send("❌ Usage: `!sell <ticker> <quantity>`\nExample: `!sell TECH 10`\nUse `!sell <ticker> all` to sell all shares.")
        return
    
    try:
        # Get stock data
        stock = get_stock_by_ticker(ticker)
        if not stock:
            await ctx.send(f"❌ Stock '{ticker.upper()}' not found. Use `!stocks` to see available stocks.")
            return
        
        stock_id, ticker_db, name, category, base_price, current_price, total_shares, available_shares = stock
        
        # Get user's holding
        c.execute("SELECT * FROM holdings WHERE user_id=? AND stock_id=?", (ctx.author.id, stock_id))
        holding = c.fetchone()
        
        if not holding:
            await ctx.send(f"❌ You don't own any shares of {ticker.upper()}. Use `!portfolio` to view your holdings.")
            return
        
        holding_id, _, _, owned_qty, avg_purchase_price = holding
        
        # Parse quantity
        if quantity.lower() == "all":
            qty = owned_qty
        else:
            qty = parse_money(quantity)
            if qty <= 0:
                await ctx.send("❌ Invalid quantity. Please enter a positive number or 'all'.")
                return
        
        # Check if user owns enough shares
        if qty > owned_qty:
            await ctx.send(f"❌ You only own {owned_qty:,} shares of {ticker.upper()}. Cannot sell {qty:,} shares.")
            return
        
        # Calculate total revenue
        total_revenue = int(current_price * qty)
        
        # Calculate profit/loss
        total_cost = avg_purchase_price * qty
        profit_loss = total_revenue - int(total_cost)
        
        # Get user balance
        user_data = get_user(ctx.author.id)
        user_id, balance, req, gambled, total_gambled, total_withdrawn = user_data
        
        # Execute sale
        # Update user balance
        update_balance(ctx.author.id, total_revenue)
        
        # Update holding
        if qty == owned_qty:
            # Sell all shares, delete holding
            c.execute("DELETE FROM holdings WHERE id=?", (holding_id,))
        else:
            # Sell partial shares, update quantity
            c.execute("""
                UPDATE holdings 
                SET quantity=?
                WHERE id=?
            """, (owned_qty - qty, holding_id))
        
        # Update available shares
        c.execute("""
            UPDATE stocks 
            SET available_shares = available_shares + ?
            WHERE id=?
        """, (qty, stock_id))
        
        conn.commit()
        
        # Apply demand-based price decrease
        new_price = apply_demand_price_change(stock_id, False)
        
        # Log transaction
        await log_transaction(
            ctx.author.id, "STOCK_SALE", total_revenue, balance, balance + total_revenue,
            f"Sold {qty} shares of {ticker.upper()} at {format_money(int(current_price))} per share"
        )
        
        # Create success embed
        profit_loss_emoji = "📈" if profit_loss > 0 else "📉" if profit_loss < 0 else "➡️"
        embed_color = discord.Color.green() if profit_loss >= 0 else discord.Color.red()
        
        embed = discord.Embed(
            title="✅ Stock Sale Successful",
            description=f"You sold **{qty:,}** shares of **{ticker.upper()}**",
            color=embed_color
        )
        embed.add_field(name="Stock", value=f"{ticker.upper()} - {name}", inline=True)
        embed.add_field(name="Quantity", value=f"{qty:,} shares", inline=True)
        embed.add_field(name="Price per Share", value=format_money(int(current_price)), inline=True)
        embed.add_field(name="Total Revenue", value=format_money(total_revenue), inline=True)
        embed.add_field(name="Profit/Loss", value=f"{profit_loss_emoji} {format_money(abs(profit_loss))}", inline=True)
        embed.add_field(name="New Balance", value=format_money(balance + total_revenue), inline=True)
        embed.add_field(name="New Stock Price", value=f"{format_money(int(new_price))} (-0.5%)", inline=True)
        
        if qty < owned_qty:
            embed.add_field(name="Remaining Shares", value=f"{owned_qty - qty:,} shares", inline=True)
        
        embed.set_footer(text="Use !portfolio to view all your holdings")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error processing sale: {str(e)}")
        print(f"Error in sell command: {e}")

@bot.command(name="portfolio")
async def portfolio(ctx, user: discord.Member = None):
    """View your stock portfolio or another user's portfolio."""
    try:
        target_user = user if user else ctx.author
        
        # Get user's holdings
        holdings = get_user_holdings(target_user.id)
        
        if not holdings:
            if target_user == ctx.author:
                await ctx.send("📊 You don't have any stocks yet. Use `!stocks` to see available stocks and `!buy` to purchase.")
            else:
                await ctx.send(f"📊 {target_user.display_name} doesn't have any stocks.")
            return
        
        # Calculate portfolio statistics
        total_value = 0
        total_invested = 0
        
        embed = discord.Embed(
            title=f"📊 {target_user.display_name}'s Stock Portfolio",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        # Add holdings
        holdings_text = []
        for holding in holdings:
            holding_id, user_id, stock_id, quantity, avg_purchase_price, ticker, name, current_price, category = holding
            
            current_value = current_price * quantity
            invested_value = avg_purchase_price * quantity
            profit_loss = current_value - invested_value
            profit_loss_pct = (profit_loss / invested_value) * 100 if invested_value > 0 else 0
            
            total_value += current_value
            total_invested += invested_value
            
            pl_emoji = "📈" if profit_loss > 0 else "📉" if profit_loss < 0 else "➡️"
            
            holdings_text.append(
                f"**{ticker}** - {name}\n"
                f"📦 Quantity: {quantity:,} shares\n"
                f"💰 Current Value: {format_money(int(current_value))}\n"
                f"{pl_emoji} P/L: {format_money(int(abs(profit_loss)))} ({profit_loss_pct:+.2f}%)"
            )
        
        # Add holdings to embed
        for i, holding_text in enumerate(holdings_text):
            embed.add_field(name=f"#{i+1}", value=holding_text, inline=True)
        
        # Calculate total profit/loss
        total_pl = total_value - total_invested
        total_pl_pct = (total_pl / total_invested) * 100 if total_invested > 0 else 0
        pl_emoji = "📈" if total_pl > 0 else "📉" if total_pl < 0 else "➡️"
        
        # Add summary
        summary = (
            f"**Total Portfolio Value:** {format_money(int(total_value))}\n"
            f"**Total Invested:** {format_money(int(total_invested))}\n"
            f"**{pl_emoji} Total P/L:** {format_money(int(abs(total_pl)))} ({total_pl_pct:+.2f}%)"
        )
        embed.add_field(name="📈 Summary", value=summary, inline=False)
        
        embed.set_footer(text="Prices update every hour | Use !stocks to see current prices")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error fetching portfolio: {str(e)}")
        print(f"Error in portfolio command: {e}")

@bot.command(name="ticketclose")
async def ticketclose(ctx, *, reason: str = "No reason provided."):
    """Close a ticket with an optional reason. Only usable by owners in ticket channels."""
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can close tickets.")
        return
    
    try:
        # Check if this is a buy ticket (channel name starts with "buy-")
        is_buy_ticket = ctx.channel.name.startswith("buy-")
        
        # Get ticket metadata from database
        c.execute("SELECT user_id, panel_name, ticket_name, open_date FROM ticket_metadata WHERE channel_id=?", (ctx.channel.id,))
        ticket_data = c.fetchone()
        
        if not ticket_data and not is_buy_ticket:
            await ctx.send("❌ This command can only be used in ticket channels.")
            return
        
        # Handle buy tickets differently
        if is_buy_ticket:
            # For buy tickets, we don't have metadata in the database
            # Extract user info from channel name pattern: buy-username-number
            try:
                # Get the channel creator from permissions (the user who has read access besides owners/bot)
                ticket_creator = None
                for member, overwrite in ctx.channel.overwrites.items():
                    if isinstance(member, discord.Member) and member.id not in OWNER_IDS and member != ctx.guild.me:
                        if overwrite.read_messages:
                            ticket_creator = member
                            break
                
                if not ticket_creator:
                    await ctx.send("⚠️ Could not identify the ticket creator. Closing anyway...")
                
                # Create the close notification embed for buy ticket
                close_embed = discord.Embed(
                    title="🎫 Purchase Ticket Closed",
                    description=f"Your purchase ticket has been closed in **Eli's MM & Gambling!**",
                    color=discord.Color.red()
                )
                close_embed.add_field(
                    name="📋 Ticket Information",
                    value=f"**Ticket Name:** {ctx.channel.name}\n**Ticket ID:** {ctx.channel.id}",
                    inline=False
                )
                close_embed.add_field(
                    name="🔒 Close Information",
                    value=f"**Closed By:** {ctx.author.mention}\n**Close Date:** {datetime.utcnow().strftime('%B %d, %Y %I:%M %p')}\n**Close Reason:** {reason}",
                    inline=False
                )
                close_embed.set_footer(text="If you have any further questions, feel free to open another ticket.")
                
                # Try to DM the ticket creator
                if ticket_creator:
                    try:
                        await ticket_creator.send(embed=close_embed)
                    except discord.Forbidden:
                        await ctx.send(f"{ticket_creator.mention}, your ticket is being closed but I couldn't DM you:", embed=close_embed)
                    except Exception as e:
                        await ctx.send(f"⚠️ Could not notify {ticket_creator.mention}: {str(e)}")
                
                # Create transcript for buy ticket
                try:
                    messages = []
                    async for m in ctx.channel.history(limit=None, oldest_first=True):
                        timestamp = m.created_at.strftime("%Y-%m-%d %H:%M")
                        messages.append(f"**[{timestamp}] {m.author.display_name}:** {m.content}")
                    
                    transcript_channel = ctx.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
                    if transcript_channel:
                        embed = discord.Embed(title="📄 Purchase Ticket Transcript", color=discord.Color.blue())
                        embed.add_field(
                            name="Ticket Information",
                            value=f"**Ticket Name:** {ctx.channel.name}\n**Ticket ID:** {ctx.channel.id}\n**Closed By:** {ctx.author.mention}\n**Close Reason:** {reason}",
                            inline=False
                        )
                        await transcript_channel.send(embed=embed)
                        
                        # Split messages into chunks
                        for i in range(0, len(messages), 10):
                            chunk = "\n".join(messages[i:i+10])
                            if len(chunk) > 4096:
                                await transcript_channel.send(embed=discord.Embed(
                                    description=chunk[:4096],
                                    color=discord.Color.blue()
                                ))
                            else:
                                await transcript_channel.send(embed=discord.Embed(
                                    description=chunk,
                                    color=discord.Color.blue()
                                ))
                except Exception as e:
                    await ctx.send(f"⚠️ Error creating transcript: {str(e)}")
                
                # Notify channel and delete
                await ctx.send(f"✅ Ticket closed by {ctx.author.mention}. Deleting channel in 3 seconds...")
                await asyncio.sleep(3)
                await ctx.channel.delete()
                return
                
            except Exception as e:
                await ctx.send(f"❌ Error closing buy ticket: {str(e)}")
                return
        
        # Original logic for regular tickets with metadata
        user_id, panel_name, ticket_name, open_date = ticket_data
        ticket_creator = await bot.fetch_user(user_id)
        
        if not ticket_creator:
            await ctx.send("❌ Could not find the ticket creator.")
            return
        
        # Get current timestamp
        close_date = datetime.utcnow().strftime("%B %d, %Y %I:%M %p")
        
        # Create the close notification embed
        close_embed = discord.Embed(
            title="🎫 Ticket Closed",
            description=f"Your ticket has been closed in **Eli's MM!**",
            color=discord.Color.red()
        )
        close_embed.add_field(
            name="📋 Ticket Information",
            value=f"**Open Date:** {open_date}\n**Panel Name:** {panel_name}\n**Ticket Name:** {ticket_name}",
            inline=False
        )
        close_embed.add_field(
            name="🔒 Close Information",
            value=f"**Closed By:** {ctx.author.mention}\n**Close Date:** {close_date}\n**Close Reason:** {reason}",
            inline=False
        )
        close_embed.set_footer(text="If you have any further questions or concerns, feel free to open a new ticket.")
        
        # Try to DM the ticket creator
        try:
            await ticket_creator.send(embed=close_embed)
        except discord.Forbidden:
            # If DMs are closed, send in the channel before deletion
            await ctx.send(f"{ticket_creator.mention}, your ticket is being closed but I couldn't DM you:", embed=close_embed)
        except Exception as e:
            await ctx.send(f"⚠️ Could not notify {ticket_creator.mention}: {str(e)}")
        
        # Create transcript
        try:
            messages = []
            async for m in ctx.channel.history(limit=None, oldest_first=True):
                timestamp = m.created_at.strftime("%Y-%m-%d %H:%M")
                messages.append(f"**[{timestamp}] {m.author.display_name}:** {m.content}")
            
            transcript_channel = ctx.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
            if transcript_channel:
                embed = discord.Embed(title="📄 Ticket Transcript", color=discord.Color.blue())
                embed.add_field(
                    name="Ticket Information",
                    value=f"**Ticket Name:** {ticket_name}\n**Ticket ID:** {ctx.channel.id}\n**Closed By:** {ctx.author.mention}\n**Close Reason:** {reason}",
                    inline=False
                )
                await transcript_channel.send(embed=embed)
                
                # Split messages into chunks
                for i in range(0, len(messages), 10):
                    chunk = "\n".join(messages[i:i+10])
                    if len(chunk) > 4096:
                        await transcript_channel.send(embed=discord.Embed(
                            description=chunk[:4096],
                            color=discord.Color.blue()
                        ))
                    else:
                        await transcript_channel.send(embed=discord.Embed(
                            description=chunk,
                            color=discord.Color.blue()
                        ))
        except Exception as e:
            await ctx.send(f"⚠️ Error creating transcript: {str(e)}")
        
        # Delete ticket metadata from database
        c.execute("DELETE FROM ticket_metadata WHERE channel_id=?", (ctx.channel.id,))
        conn.commit()
        
        # Delete the channel
        await ctx.send("✅ Closing ticket in 3 seconds...")
        await asyncio.sleep(3)
        
        try:
            await ctx.channel.delete()
        except discord.Forbidden:
            await ctx.send("❌ Missing permissions to delete this channel.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error deleting channel: {str(e)}")
            
    except Exception as e:
        await ctx.send(f"❌ Error closing ticket: {str(e)}")


@bot.command(name="stick")
async def stick(ctx, *, message: str):
    """
    Create a sticky message that stays at the bottom of the channel.
    The message will automatically repost when other messages are sent.
    
    Usage: !stick <message>
    Example: !stick Please refer to deposit channel to deposit!
    
    Owner only command.
    """
    # Check if user is owner
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("❌ Only bot owners can use this command.")
        return
    
    try:
        channel_id = ctx.channel.id
        
        # Delete the command message
        try:
            await ctx.message.delete()
        except:
            pass
        
        # If there's an existing stick message in this channel, delete it
        if channel_id in stick_messages:
            try:
                old_msg = await ctx.channel.fetch_message(stick_messages[channel_id]["message_id"])
                await old_msg.delete()
            except:
                pass
        
        # Post the new stick message
        stick_msg = await ctx.send(f"📌 {message}")
        
        # Store the stick message data
        stick_messages[channel_id] = {
            "message_id": stick_msg.id,
            "content": message,
            "last_update": datetime.now()
        }
        
    except Exception as e:
        await ctx.send(f"❌ Error creating stick message: {str(e)}")


@bot.command(name="unstick")
async def unstick(ctx):
    """
    Remove the sticky message from the current channel.
    
    Usage: !unstick
    
    Owner only command.
    """
    # Check if user is owner
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("❌ Only bot owners can use this command.")
        return
    
    try:
        channel_id = ctx.channel.id
        
        # Delete the command message
        try:
            await ctx.message.delete()
        except:
            pass
        
        # Check if there's a stick message in this channel
        if channel_id not in stick_messages:
            await ctx.send("❌ No stick message found in this channel.", delete_after=5)
            return
        
        # Delete the stick message
        try:
            stick_msg = await ctx.channel.fetch_message(stick_messages[channel_id]["message_id"])
            await stick_msg.delete()
        except:
            pass
        
        # Remove from tracking
        del stick_messages[channel_id]
        
        confirm = await ctx.send("✅ Stick message removed.", delete_after=5)
        
    except Exception as e:
        await ctx.send(f"❌ Error removing stick message: {str(e)}")

# -----------------------------
# 🎲 LUCKY NUMBER GAME
# -----------------------------
# Store active lucky number games: {user_id: {"bet": amount, "range": max_num, "lucky_num": num, "timestamp": datetime}}
lucky_number_games = {}

# Store active crash games: {user_id: {"bet": amount, "crash_point": float, "timestamp": datetime, "message": Message}}
crash_games = {}

def calculate_lucky_number_multiplier(max_range):
    """Calculate fair multiplier based on risk (odds of winning) - NERFED."""
    if max_range <= 50:
        return 25.0  # 1/50 = 2% chance → 25x return (50% RTP)
    elif max_range <= 100:
        return 50.0  # 1/100 = 1% chance → 50x return (50% RTP)
    elif max_range <= 500:
        return 250.0  # 1/500 = 0.2% chance → 250x return (50% RTP)
    elif max_range <= 1000:
        return 500.0  # 1/1000 = 0.1% chance → 500x return (50% RTP)
    elif max_range <= 2500:
        return 1250.0  # 1/2500 = 0.04% chance → 1250x return (50% RTP)
    elif max_range <= 5000:
        return 2500.0  # 1/5000 = 0.02% chance → 2500x return (50% RTP)
    else:
        return 2500.0  # Cap at 5000

@bot.command(name="luckynumber")
async def luckynumber(ctx, amount: str = None, max_number: str = None):
    """
    Start a lucky number game - guess the lucky number to win big!
    
    Usage: !luckynumber <amount> <max_number>
    Example: !luckynumber 10m 100
    
    After starting, use !pick <your_number> to make your guess.
    
    Risk levels:
    - 50-50: Medium risk, 25x multiplier
    - 51-100: High risk, 50x multiplier
    - 101-500: Very high risk, 250x multiplier
    - 501-1000: Extreme risk, 500x multiplier
    - 1001-2500: Ultra risk, 1250x multiplier
    - 2501-5000: Maximum risk, 2500x multiplier
    """
    try:
        if amount is None or max_number is None:
            await ctx.send("❌ Usage: `!luckynumber <amount> <50-5000>`\nExample: `!luckynumber 10m 100`")
            return

        # Parse bet amount
        value = parse_money(amount)
        if value <= 0:
            await ctx.send("❌ Invalid amount format! Use k, m, or b (e.g., 10m, 5k).")
            return

        # Parse max number
        try:
            max_num = int(max_number)
        except:
            await ctx.send("❌ Invalid number range! Must be a number between 1-5000.")
            return

        if max_num < 50 or max_num > 5000:
            await ctx.send("❌ Number range must be between 50-5000! Minimum is 50.")
            return

        # Get user data
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(ctx.author.id)

        if value > balance:
            await ctx.send("❌ You cannot gamble more than your balance.")
            return
        
        # Check for rapid betting (fraud detection)
        is_rapid = await check_rapid_betting(ctx.author.id)
        if is_rapid:
            await send_fraud_alert(
                bot,
                ctx.author,
                "Rapid Betting Detected",
                f"User placed {RAPID_BET_THRESHOLD}+ bets in 60 seconds\nBet Amount: {value:,}$\nGame: Lucky Number"
            )
        
        # Check for high bet (fraud detection)
        if value >= HIGH_BET_THRESHOLD:
            await log_user_activity(
                bot,
                ctx.author,
                "High Value Bet",
                f"Amount: {value:,}$\nGame: Lucky Number\nRange: 1-{max_num}\nBalance: {balance:,}$"
            )

        # Generate lucky number using provably fair (no bet deduction yet, only at !pick)
        result, client_seed, nonce, seed_hash = provably_fair.place_bet(
            ctx.author.id, "luckynumber", 0, max_num  # amount=0 since we deduct at !pick
        )
        lucky_num = result + 1  # Convert 0-based to 1-based (1 to max_num)
        multiplier = calculate_lucky_number_multiplier(max_num)
        
        # Store game state
        lucky_number_games[ctx.author.id] = {
            "bet": value,
            "range": max_num,
            "lucky_num": lucky_num,
            "timestamp": datetime.now(),
            "multiplier": multiplier,
            "client_seed": client_seed,
            "nonce": nonce,
            "seed_hash": seed_hash
        }

        # Create embed
        embed = discord.Embed(
            title="🎲 Lucky Number Game Started!",
            description=f"**Bet Amount:** {value:,}$\n**Range:** 1-{max_num}\n**Multiplier:** {multiplier}x\n\n💡 Use `!pick <number>` to make your guess!",
            color=discord.Color.purple()
        )
        embed.add_field(name="💰 Potential Win", value=f"{int(value * multiplier):,}$", inline=True)
        embed.add_field(name="🎯 Win Chance", value=f"{(1/max_num)*100:.2f}%", inline=True)
        embed.add_field(name="⏰ Time Limit", value="60 seconds", inline=True)
        embed.set_footer(text=f"Good luck, {ctx.author.display_name}!")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error starting lucky number game: {str(e)}")

@bot.command(name="pick")
async def pick(ctx, number: str = None):
    """
    Pick your lucky number!
    
    Usage: !pick <number>
    Example: !pick 42
    
    Must have an active lucky number game started with !luckynumber
    """
    try:
        if number is None:
            await ctx.send("❌ Usage: `!pick <number>`\nExample: `!pick 42`")
            return

        # Check if user has an active game
        if ctx.author.id not in lucky_number_games:
            await ctx.send("❌ You don't have an active lucky number game!\nStart one with `!luckynumber <amount> <max_number>`")
            return

        game = lucky_number_games[ctx.author.id]
        
        # Check if game expired (60 second timeout)
        if datetime.now() - game["timestamp"] > timedelta(seconds=60):
            del lucky_number_games[ctx.author.id]
            await ctx.send("❌ Your lucky number game expired! Start a new one with `!luckynumber`")
            return

        # Parse picked number
        try:
            picked_num = int(number)
        except:
            await ctx.send(f"❌ Invalid number! Must be between 1-{game['range']}")
            return

        if picked_num < 1 or picked_num > game["range"]:
            await ctx.send(f"❌ Number must be between 1-{game['range']}!")
            return

        # Get user data
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(ctx.author.id)
        
        bet_amount = game["bet"]
        lucky_num = game["lucky_num"]
        multiplier = game["multiplier"]
        max_range = game["range"]
        
        # Deduct bet from balance
        balance -= bet_amount
        
        # Check if won
        won = (picked_num == lucky_num)
        
        if won:
            winnings = int(bet_amount * multiplier)
            balance += winnings
            result_msg = f"🎉 **JACKPOT!** You guessed the lucky number!\n\n🎲 Lucky Number: **{lucky_num}**\n💰 You won: **{winnings:,}$**"
            color = discord.Color.gold()
        else:
            result_msg = f"💀 Not quite! Better luck next time.\n\n🎲 Lucky Number: **{lucky_num}**\n🎯 Your Pick: **{picked_num}**\n💸 You lost: **{bet_amount:,}$**"
            color = discord.Color.red()
        
        # Update gambled amount
        gambled += bet_amount
        total_gambled += bet_amount
        
        c.execute(
            "UPDATE users SET balance=?, gambled=?, total_gambled=? WHERE user_id=?",
            (balance, gambled, total_gambled, ctx.author.id)
        )
        conn.commit()
        
        # Log bet activity
        await log_bet_activity(ctx.author.id, bet_amount, "luckynumber", "win" if won else "loss")
        
        # Log transaction
        await log_transaction(
            ctx.author.id,
            "luckynumber_bet",
            bet_amount,
            balance + bet_amount,
            balance,
            f"Lucky Number: Range 1-{max_range}, Picked {picked_num}, Lucky {lucky_num}, {'WON' if won else 'LOST'}"
        )
        
        remaining = max(required_gamble - gambled, 0)
        
        # Create result embed
        embed = discord.Embed(title="🎲 Lucky Number Result", description=result_msg, color=color)
        embed.add_field(name="💵 Balance", value=f"{balance:,}$", inline=True)
        embed.add_field(name="📊 Required Gamble", value=f"{required_gamble:,}$", inline=True)
        embed.add_field(name="⏳ Remaining", value=f"{remaining:,}$", inline=True)
        embed.add_field(name="🎰 Multiplier", value=f"{multiplier}x", inline=True)
        embed.add_field(name="🎯 Range", value=f"1-{max_range}", inline=True)
        embed.add_field(name="📈 Win Chance", value=f"{(1/max_range)*100:.2f}%", inline=True)
        
        # Add provably fair information
        embed.add_field(
            name="🔐 Provably Fair",
            value=f"Nonce: {game['nonce']} | Client: {game['client_seed'][:8]}...\nSeed Hash: {game['seed_hash'][:16]}...\nUse `!verify` to verify fairness",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
        # Remove game from active games
        del lucky_number_games[ctx.author.id]
        
    except Exception as e:
        await ctx.send(f"❌ Error picking number: {str(e)}")

# -----------------------------
# 🚀 CRASH GAME
# -----------------------------
class CrashView(View):
    """Interactive view for the Crash gambling game."""
    def __init__(self, user_id, bet_amount, crash_point, ctx):
        super().__init__(timeout=180)  # Increased from 120 to 180 seconds (3 minutes)
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.crash_point = crash_point
        self.ctx = ctx
        self.current_multiplier = 1.0  # Start at 1.0x
        self.cashed_out = False
        self.crashed = False
        self.task = None
    
    async def start_crash_animation(self, message):
        """Animate the multiplier increasing until crash."""
        try:
            while not self.cashed_out and not self.crashed:
                # Increase multiplier (starts at 1.0x, increases by 0.05-0.1x each tick)
                increment = round(random.uniform(0.05, 0.1), 2)
                self.current_multiplier += increment
                self.current_multiplier = round(self.current_multiplier, 2)
                
                # Check if we've reached the crash point
                if self.current_multiplier >= self.crash_point:
                    self.crashed = True
                    self.current_multiplier = self.crash_point
                    
                    # Disable the cash out button
                    for item in self.children:
                        item.disabled = True
                    
                    # Get game data for provably fair info
                    game_data = crash_games.get(self.user_id, {})
                    client_seed = game_data.get("client_seed", "")
                    nonce = game_data.get("nonce", 0)
                    seed_hash = game_data.get("seed_hash", "")
                    
                    # Update to crash embed
                    embed = discord.Embed(
                        title="💥 CRASH!",
                        description=f"The multiplier crashed at **{self.crash_point}x**!",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="💸 Final Multiplier", value=f"**{self.crash_point}x**", inline=True)
                    embed.add_field(name="💔 You Lost", value=f"{self.bet_amount:,}$", inline=True)
                    embed.add_field(name="🎲 Result", value="**CRASHED**", inline=True)
                    
                    # Add provably fair information
                    if client_seed:
                        embed.add_field(
                            name="🔐 Provably Fair",
                            value=f"Nonce: {nonce} | Client: {client_seed[:8]}...\nSeed Hash: {seed_hash[:16]}...\nUse `!verify` to verify fairness",
                            inline=False
                        )
                    
                    embed.set_footer(text="Better luck next time! Try !crash <amount> to play again.")
                    
                    await message.edit(embed=embed, view=self)
                    
                    # Update user balance (loss)
                    user_id_db, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(self.user_id)
                    balance -= self.bet_amount
                    gambled += self.bet_amount
                    total_gambled += self.bet_amount
                    
                    c.execute(
                        "UPDATE users SET balance=?, gambled=?, total_gambled=? WHERE user_id=?",
                        (balance, gambled, total_gambled, self.user_id)
                    )
                    conn.commit()
                    
                    # Log activity
                    await log_bet_activity(self.user_id, self.bet_amount, "crash", "loss")
                    await log_transaction(
                        self.user_id,
                        "crash_bet",
                        self.bet_amount,
                        balance + self.bet_amount,
                        balance,
                        f"Crash: Crashed at {self.crash_point}x, LOST"
                    )
                    
                    # Remove from active games
                    if self.user_id in crash_games:
                        del crash_games[self.user_id]
                    
                    break
                
                # Update embed with current multiplier
                potential_win = int(self.bet_amount * self.current_multiplier)
                
                embed = discord.Embed(
                    title="🚀 Crash Game - IN PROGRESS",
                    description=f"The multiplier is climbing! Cash out before it crashes!",
                    color=discord.Color.green()
                )
                embed.add_field(name="📈 Current Multiplier", value=f"**{self.current_multiplier}x**", inline=True)
                embed.add_field(name="💰 Potential Win", value=f"**{potential_win:,}$**", inline=True)
                embed.add_field(name="🎲 Bet Amount", value=f"{self.bet_amount:,}$", inline=True)
                embed.set_footer(text="Click 'Cash Out' to secure your winnings before the crash!")
                
                try:
                    await message.edit(embed=embed, view=self)
                except discord.errors.NotFound:
                    # Message was deleted
                    break
                
                # Wait before next update (dynamic speed based on multiplier)
                # Starts slower (1.5s), speeds up gradually, caps at 0.6s
                if self.current_multiplier < 1.79:
                    wait_time = 1.5
                elif self.current_multiplier < 3.0:
                    wait_time = 1.2
                elif self.current_multiplier < 5.0:
                    wait_time = 0.9
                else:
                    wait_time = 0.6
                await asyncio.sleep(wait_time)
                
        except Exception as e:
            print(f"Error in crash animation: {e}")
    
    @discord.ui.button(label="💵 Cash Out", style=discord.ButtonStyle.success, custom_id="crash_cashout")
    async def cashout_button(self, interaction: discord.Interaction, button: Button):
        """Handle the cash out button click."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your crash game!", ephemeral=True)
            return
        
        if self.cashed_out:
            await interaction.response.send_message("❌ You already cashed out!", ephemeral=True)
            return
        
        if self.crashed:
            await interaction.response.send_message("❌ Too late! The game already crashed!", ephemeral=True)
            return
        
        # Minimum cashout multiplier is 1.79x to make the game much harder
        if self.current_multiplier < 1.79:
            await interaction.response.send_message(
                f"❌ Minimum cashout is **1.79x**! Current: **{self.current_multiplier}x**\n"
                "Wait for the multiplier to increase before cashing out.",
                ephemeral=True
            )
            return
        
        # Cash out successfully
        self.cashed_out = True
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        
        # Calculate winnings
        winnings = int(self.bet_amount * self.current_multiplier)
        profit = winnings - self.bet_amount
        
        # Get game data for provably fair info
        game_data = crash_games.get(self.user_id, {})
        client_seed = game_data.get("client_seed", "")
        nonce = game_data.get("nonce", 0)
        seed_hash = game_data.get("seed_hash", "")
        
        # Update user balance (win)
        user_id_db, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(self.user_id)
        balance += profit
        gambled += self.bet_amount
        total_gambled += self.bet_amount
        
        c.execute(
            "UPDATE users SET balance=?, gambled=?, total_gambled=? WHERE user_id=?",
            (balance, gambled, total_gambled, self.user_id)
        )
        conn.commit()
        
        remaining = max(required_gamble - gambled, 0)
        
        # Create success embed
        embed = discord.Embed(
            title="✅ Cashed Out Successfully!",
            description=f"You cashed out at **{self.current_multiplier}x** before the crash!",
            color=discord.Color.gold()
        )
        embed.add_field(name="💰 Total Winnings", value=f"**{winnings:,}$**", inline=True)
        embed.add_field(name="📈 Profit", value=f"+{profit:,}$", inline=True)
        embed.add_field(name="🎲 Multiplier", value=f"{self.current_multiplier}x", inline=True)
        embed.add_field(name="Balance", value=f"{balance:,}$", inline=True)
        embed.add_field(name="Remaining Gamble", value=f"{remaining:,}$", inline=True)
        embed.add_field(name="Crash Point", value=f"Would have crashed at {self.crash_point}x", inline=True)
        
        # Add provably fair information
        if client_seed:
            embed.add_field(
                name="🔐 Provably Fair",
                value=f"Nonce: {nonce} | Client: {client_seed[:8]}...\nSeed Hash: {seed_hash[:16]}...\nUse `!verify` to verify fairness",
                inline=False
            )
        
        embed.set_footer(text=f"Great timing! • Use !crash <amount> to play again")
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Log activity
        await log_bet_activity(self.user_id, self.bet_amount, "crash", "win")
        await log_transaction(
            self.user_id,
            "crash_bet",
            self.bet_amount,
            balance - profit,
            balance,
            f"Crash: Cashed out at {self.current_multiplier}x, WON {profit:,}$"
        )
        
        # Remove from active games
        if self.user_id in crash_games:
            del crash_games[self.user_id]
    
    async def on_timeout(self):
        """Called when the view times out."""
        # If the game is still active, treat it as a crash
        if not self.cashed_out and not self.crashed:
            self.crashed = True
            # Remove from active games
            if self.user_id in crash_games:
                del crash_games[self.user_id]

@bot.command(name="crash")
async def crash(ctx, amount: str = None):
    """
    Play the Crash gambling game - cash out before the multiplier crashes!
    
    Usage: !crash <amount>
    Example: !crash 10m
    
    How it works:
    - A multiplier starts at 1.0x and increases steadily
    - The multiplier will crash at a random point (1.1x to 10x+)
    - You must cash out before it crashes to win
    - Your winnings = bet × multiplier at cash out
    - If you don't cash out before the crash, you lose your bet
    
    Strategy: Higher multipliers = higher risk/reward
    """
    try:
        if amount is None:
            await ctx.send("❌ Usage: `!crash <amount>`\nExample: `!crash 10m`")
            return
        
        # Parse bet amount
        value = parse_money(amount)
        if value <= 0:
            await ctx.send("❌ Invalid amount! Please provide a valid amount.\nExample: `!crash 10m` or `!crash 1000000`")
            return
        
        # Check if user already has an active crash game
        if ctx.author.id in crash_games:
            await ctx.send("❌ You already have an active crash game! Finish or wait for it to complete first.")
            return
        
        # Get user data
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(ctx.author.id)
        
        # Check balance
        if value > balance:
            await ctx.send(f"❌ Insufficient balance! You have {balance:,}$ but need {value:,}$")
            return
        
        # Generate crash point using provably fair system
        result, client_seed, nonce, seed_hash = provably_fair.place_bet(
            ctx.author.id, "crash", value, 10000
        )
        
        # Convert result (0-9999) to crash point distribution
        # Heavily weighted toward early crashes - much harder to win
        if result < 5500:  # 55% chance: crash between 1.15x and 1.5x
            crash_point = round(1.15 + (result / 5500) * 0.35, 2)
        elif result < 7800:  # 23% chance: crash between 1.5x and 2.0x
            crash_point = round(1.5 + ((result - 5500) / 2300) * 0.5, 2)
        elif result < 9000:  # 12% chance: crash between 2.0x and 3.0x
            crash_point = round(2.0 + ((result - 7800) / 1200) * 1.0, 2)
        elif result < 9700:  # 7% chance: crash between 3.0x and 5.0x
            crash_point = round(3.0 + ((result - 9000) / 700) * 2.0, 2)
        else:  # 3% chance: crash between 5.0x and 10.0x
            crash_point = round(5.0 + ((result - 9700) / 300) * 5.0, 2)
        
        # Create initial embed
        embed = discord.Embed(
            title="🚀 Crash Game Started!",
            description="The multiplier is starting to climb! Watch it go up and cash out before it crashes!",
            color=discord.Color.purple()
        )
        embed.add_field(name="💰 Bet Amount", value=f"{value:,}$", inline=True)
        embed.add_field(name="📈 Starting Multiplier", value="1.0x", inline=True)
        embed.add_field(name="🎯 Status", value="**READY**", inline=True)
        embed.set_footer(text="Multiplier starts at 1.0x - Cash out before it crashes!")
        
        # Create view with crash point
        view = CrashView(ctx.author.id, value, crash_point, ctx)
        
        # Send message
        message = await ctx.send(embed=embed, view=view)
        
        # Store game in active games
        crash_games[ctx.author.id] = {
            "bet": value,
            "crash_point": crash_point,
            "timestamp": datetime.now(),
            "message": message,
            "client_seed": client_seed,
            "nonce": nonce,
            "seed_hash": seed_hash
        }
        
        # Start the crash animation
        await asyncio.sleep(1)  # Brief pause before starting
        view.task = asyncio.create_task(view.start_crash_animation(message))
        
    except Exception as e:
        await ctx.send(f"❌ Error starting crash game: {str(e)}")

# -----------------------------
# ⚔️ GLADIATOR FIGHTS GAME
# -----------------------------

# Gladiator roster with unique stats
GLADIATORS = {
    "Maximus": {"hp": 100, "attack": (15, 25), "defense": 15, "dodge": 20, "icon": "⚔️"},
    "Spartacus": {"hp": 110, "attack": (18, 23), "defense": 12, "dodge": 15, "icon": "🗡️"},
    "Achilles": {"hp": 95, "attack": (20, 28), "defense": 10, "dodge": 25, "icon": "🏹"},
    "Leonidas": {"hp": 120, "attack": (12, 20), "defense": 20, "dodge": 10, "icon": "🛡️"},
    "Hercules": {"hp": 130, "attack": (10, 22), "defense": 18, "dodge": 8, "icon": "💪"},
    "Thor": {"hp": 105, "attack": (16, 26), "defense": 14, "dodge": 18, "icon": "⚡"},
    "Atlas": {"hp": 125, "attack": (14, 18), "defense": 22, "dodge": 5, "icon": "🗿"},
    "Perseus": {"hp": 100, "attack": (17, 24), "defense": 13, "dodge": 22, "icon": "⚔️"},
}

# Active gladiator fights
gladiator_fights = {}  # {challenge_id: {players, bets, gladiators, etc}}

class GladiatorConfirmView(View):
    """View for confirming gladiator fight participation."""
    
    def __init__(self, challenger_id, opponent_id, bet_amount, challenge_id):
        super().__init__(timeout=60)
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.bet_amount = bet_amount
        self.challenge_id = challenge_id
    
    @discord.ui.button(label="✅ Accept Fight", style=discord.ButtonStyle.green)
    async def accept_fight(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message("❌ Only the challenged player can accept this fight!", ephemeral=True)
            return
        
        # Check if opponent has enough balance
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.opponent_id)
        
        if balance < self.bet_amount:
            await interaction.response.send_message(
                f"❌ Insufficient balance! You need {self.bet_amount:,}$ but only have {balance:,}$",
                ephemeral=True
            )
            return
        
        # Update fight data
        if self.challenge_id in gladiator_fights:
            gladiator_fights[self.challenge_id]["accepted"] = True
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        # Show gladiator selection to opponent
        embed = discord.Embed(
            title="⚔️ Fight Accepted!",
            description=f"<@{self.opponent_id}>, choose your gladiator!",
            color=discord.Color.green()
        )
        embed.add_field(name="💰 Wager", value=f"{self.bet_amount:,}$ each", inline=True)
        embed.add_field(name="🏆 Winner Takes", value=f"{self.bet_amount * 2:,}$", inline=True)
        embed.set_footer(text="Use !pickgladiator <gladiator_name> to select your fighter")
        
        # List available gladiators
        glad_list = "\n".join([f"{data['icon']} **{name}** - HP: {data['hp']}, ATK: {data['attack'][0]}-{data['attack'][1]}, DEF: {data['defense']}%, Dodge: {data['dodge']}%" 
                               for name, data in GLADIATORS.items()])
        embed.add_field(name="🏛️ Available Gladiators", value=glad_list, inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="❌ Decline Fight", style=discord.ButtonStyle.red)
    async def decline_fight(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message("❌ Only the challenged player can decline this fight!", ephemeral=True)
            return
        
        # Remove from active fights
        if self.challenge_id in gladiator_fights:
            del gladiator_fights[self.challenge_id]
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        embed = discord.Embed(
            title="❌ Fight Declined",
            description=f"<@{self.opponent_id}> has declined the gladiator fight.",
            color=discord.Color.red()
        )
        
        await interaction.response.edit_message(embed=embed, view=self)

class GladiatorRematchConfirmView(View):
    """View for confirming gladiator rematch - both players must confirm."""
    
    def __init__(self, player1_id, player2_id, bet_amount, challenge_id):
        super().__init__(timeout=60)  # 60 second timeout for confirmation
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.bet_amount = bet_amount
        self.challenge_id = challenge_id
        self.confirmed_players = set()
    
    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm_rematch(self, interaction: discord.Interaction, button: Button):
        # Check if it's one of the fighters
        if interaction.user.id not in [self.player1_id, self.player2_id]:
            await interaction.response.send_message("❌ Only the fighters can confirm!", ephemeral=True)
            return
        
        # Check if already confirmed
        if interaction.user.id in self.confirmed_players:
            await interaction.response.send_message("✅ You already confirmed!", ephemeral=True)
            return
        
        # Add to confirmed set
        self.confirmed_players.add(interaction.user.id)
        
        # Update message
        if len(self.confirmed_players) == 1:
            await interaction.response.send_message(f"✅ <@{interaction.user.id}> confirmed! Waiting for the other player...", ephemeral=False)
        elif len(self.confirmed_players) == 2:
            # Both confirmed - start the fight
            await interaction.response.send_message("✅ Both players confirmed! Starting the rematch...", ephemeral=False)
            
            # Disable buttons
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
            
            # Start the fight
            if self.challenge_id in gladiator_fights:
                fight_data = gladiator_fights[self.challenge_id]
                
                # Check both players still have balance
                p1_data = get_user(self.player1_id)
                p2_data = get_user(self.player2_id)
                
                if p1_data[1] < self.bet_amount:
                    await interaction.followup.send(f"❌ <@{self.player1_id}> has insufficient balance for another round!")
                    del gladiator_fights[self.challenge_id]
                    return
                
                if p2_data[1] < self.bet_amount:
                    await interaction.followup.send(f"❌ <@{self.player2_id}> has insufficient balance for another round!")
                    del gladiator_fights[self.challenge_id]
                    return
                
                # Reset HP for new round
                fight_data['p1_hp'] = GLADIATORS[fight_data['p1_gladiator']]["hp"]
                fight_data['p2_hp'] = GLADIATORS[fight_data['p2_gladiator']]["hp"]
                
                # Create new fight view
                fight_view = GladiatorFightView(self.player1_id, self.player2_id, self.bet_amount, self.challenge_id)
                
                # Start the fight animation
                await fight_view.run_fight_animation(interaction.channel, fight_data)
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel_rematch(self, interaction: discord.Interaction, button: Button):
        # Check if it's one of the fighters
        if interaction.user.id not in [self.player1_id, self.player2_id]:
            await interaction.response.send_message("❌ Only the fighters can cancel!", ephemeral=True)
            return
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        
        embed = discord.Embed(
            title="❌ Rematch Cancelled",
            description=f"<@{interaction.user.id}> cancelled the rematch.",
            color=discord.Color.red()
        )
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Clean up
        if self.challenge_id in gladiator_fights:
            del gladiator_fights[self.challenge_id]

class GladiatorFightView(View):
    """View for active gladiator fight with next round button."""
    
    def __init__(self, player1_id, player2_id, bet_amount, challenge_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.bet_amount = bet_amount
        self.challenge_id = challenge_id
    
    @discord.ui.button(label="🔄 Next Round", style=discord.ButtonStyle.blurple, disabled=True)
    async def next_round(self, interaction: discord.Interaction, button: Button):
        # Check if either player clicked
        if interaction.user.id not in [self.player1_id, self.player2_id]:
            await interaction.response.send_message("❌ Only the fighters can start the next round!", ephemeral=True)
            return
        
        # Create confirmation embed
        confirm_embed = discord.Embed(
            title="⚔️ Confirm Next Round?",
            description=f"<@{self.player1_id}> and <@{self.player2_id}>, both players must confirm to start the next round!\n\n**Bet Amount:** {self.bet_amount:,}$\n**Prize:** {self.bet_amount * 2:,}$",
            color=discord.Color.orange()
        )
        confirm_embed.set_footer(text="Both players must click '✅ Confirm' to start the fight!")
        
        # Create confirmation view
        confirm_view = GladiatorRematchConfirmView(self.player1_id, self.player2_id, self.bet_amount, self.challenge_id)
        
        # Disable next round button
        button.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Send confirmation message
        await interaction.followup.send(embed=confirm_embed, view=confirm_view)

    async def run_fight_animation(self, channel, fight_data):
        """Run the animated fight sequence."""
        p1_name = fight_data["p1_gladiator"]
        p2_name = fight_data["p2_gladiator"]
        p1_stats = GLADIATORS[p1_name]
        p2_stats = GLADIATORS[p2_name]
        
        round_num = 1
        fight_message = None
        action_log = []  # Keep last 3 actions
        
        while fight_data["p1_hp"] > 0 and fight_data["p2_hp"] > 0:
            # Player 1 attacks Player 2
            action_result = self.process_attack(fight_data, "p1", "p2", p1_stats, p2_stats, p1_name, p2_name)
            action_log.append(action_result["message"])
            fight_data["p2_hp"] = action_result["defender_hp"]
            
            # Create battle embed
            embed = discord.Embed(
                title=f"⚔️ GLADIATOR ARENA",
                description=f"**Round {round_num}** | 💰 Prize: {self.bet_amount * 2:,}$",
                color=discord.Color.orange()
            )
            
            # Player 1 info with health bar
            p1_health_bar = self.create_health_bar(fight_data["p1_hp"], p1_stats["hp"])
            embed.add_field(
                name=f"{p1_stats['icon']} {p1_name}",
                value=f"<@{fight_data['player1']}>\n{p1_health_bar}\n**HP: {fight_data['p1_hp']}/{p1_stats['hp']}**",
                inline=True
            )
            
            # VS separator
            embed.add_field(
                name="⚔️",
                value="**VS**",
                inline=True
            )
            
            # Player 2 info with health bar
            p2_health_bar = self.create_health_bar(fight_data["p2_hp"], p2_stats["hp"])
            embed.add_field(
                name=f"{p2_stats['icon']} {p2_name}",
                value=f"<@{fight_data['player2']}>\n{p2_health_bar}\n**HP: {fight_data['p2_hp']}/{p2_stats['hp']}**",
                inline=True
            )
            
            # Show recent actions (last 3)
            if action_log:
                recent_actions = "\n".join(action_log[-3:])
                embed.add_field(
                    name="⚡ Battle Log",
                    value=recent_actions,
                    inline=False
                )
            
            embed.set_footer(text=f"Round {round_num} • The battle rages on!")
            
            # Send or update embed
            if fight_message is None:
                fight_message = await channel.send(embed=embed)
            else:
                await fight_message.edit(embed=embed)
            
            # Check if P2 died
            if fight_data["p2_hp"] <= 0:
                break
            
            await asyncio.sleep(3.5)  # Pause between actions for readability
            
            # Player 2 attacks Player 1
            action_result = self.process_attack(fight_data, "p2", "p1", p2_stats, p1_stats, p2_name, p1_name)
            action_log.append(action_result["message"])
            fight_data["p1_hp"] = action_result["defender_hp"]
            
            # Update embed with P2's attack
            p1_health_bar = self.create_health_bar(fight_data["p1_hp"], p1_stats["hp"])
            embed.set_field_at(
                0,
                name=f"{p1_stats['icon']} {p1_name}",
                value=f"<@{fight_data['player1']}>\n{p1_health_bar}\n**HP: {fight_data['p1_hp']}/{p1_stats['hp']}**",
                inline=True
            )
            
            # Update battle log
            recent_actions = "\n".join(action_log[-3:])
            # Find the battle log field index (should be field 3)
            for i, field in enumerate(embed.fields):
                if field.name == "⚡ Battle Log":
                    embed.set_field_at(i, name="⚡ Battle Log", value=recent_actions, inline=False)
                    break
            
            await fight_message.edit(embed=embed)
            await asyncio.sleep(3.5)
            
            # Check if P1 died
            if fight_data["p1_hp"] <= 0:
                break
            
            round_num += 1
        
        # Determine winner
        if fight_data["p1_hp"] > 0:
            winner_id = fight_data["player1"]
            winner_name = p1_name
            winner_icon = p1_stats["icon"]
            loser_id = fight_data["player2"]
            loser_name = p2_name
        else:
            winner_id = fight_data["player2"]
            winner_name = p2_name
            winner_icon = p2_stats["icon"]
            loser_id = fight_data["player1"]
            loser_name = p1_name
        
        # Update balances
        winner_data = get_user(winner_id)
        loser_data = get_user(loser_id)
        
        # Winner gets both bets
        new_winner_balance = winner_data[1] + self.bet_amount
        new_loser_balance = loser_data[1] - self.bet_amount
        
        # Update winner
        c.execute("UPDATE users SET balance = ?, gambled = gambled + ?, total_gambled = total_gambled + ? WHERE user_id = ?",
                  (new_winner_balance, self.bet_amount, self.bet_amount, winner_id))
        
        # Update loser
        c.execute("UPDATE users SET balance = ?, gambled = gambled + ?, total_gambled = total_gambled + ? WHERE user_id = ?",
                  (new_loser_balance, self.bet_amount, self.bet_amount, loser_id))
        
        conn.commit()
        
        # Log transactions
        log_transaction(winner_id, "gladiator_win", self.bet_amount, winner_data[1], new_winner_balance, 
                       f"Won gladiator fight against {loser_name}")
        log_transaction(loser_id, "gladiator_loss", self.bet_amount, loser_data[1], new_loser_balance,
                       f"Lost gladiator fight against {winner_name}")
        
        # Log bet activity for fraud detection
        await log_bet_activity(winner_id, self.bet_amount, "gladiator", "win")
        await log_bet_activity(loser_id, self.bet_amount, "gladiator", "loss")
        
        # Get winner's remaining HP
        winner_hp = fight_data['p1_hp'] if winner_id == fight_data['player1'] else fight_data['p2_hp']
        winner_max_hp = GLADIATORS[winner_name]["hp"]
        winner_health_bar = self.create_health_bar(winner_hp, winner_max_hp)
        
        # Create victory embed
        victory_embed = discord.Embed(
            title=f"🏆 VICTORY!",
            description=f"**{winner_icon} {winner_name}** defeats **{loser_name}** in an epic battle!",
            color=discord.Color.gold()
        )
        
        # Winner info
        victory_embed.add_field(
            name=f"👑 Champion",
            value=f"<@{winner_id}>\n{winner_health_bar}\n**Remaining HP: {winner_hp}/{winner_max_hp}**",
            inline=True
        )
        
        # Loser info
        victory_embed.add_field(
            name=f"💀 Defeated",
            value=f"<@{loser_id}>\n💀 `░░░░░░░░░░` 0%\n**HP: 0/{GLADIATORS[loser_name]['hp']}**",
            inline=True
        )
        
        # Financial summary
        victory_embed.add_field(
            name="💰 Prize Money",
            value=f"**Winner:** +{self.bet_amount:,}$\n**Loser:** -{self.bet_amount:,}$",
            inline=False
        )
        
        # Battle statistics
        battle_stats = f"⚔️ **Rounds Fought:** {round_num}\n"
        battle_stats += f"💪 **Total Actions:** {len(action_log)}\n"
        battle_stats += f"🎯 **Last 3 Actions:**\n"
        battle_stats += "\n".join(f"• {action}" for action in action_log[-3:])
        
        victory_embed.add_field(
            name="📊 Battle Summary",
            value=battle_stats,
            inline=False
        )
        
        victory_embed.set_footer(text="🔄 Click 'Next Round' for a rematch with the same gladiators!")
        
        # Enable next round button
        for child in self.children:
            if isinstance(child, Button) and "Next Round" in child.label:
                child.disabled = False
        
        await fight_message.edit(embed=victory_embed, view=self)
    
    def process_attack(self, fight_data, attacker_key, defender_key, attacker_stats, defender_stats, attacker_name, defender_name):
        """Process a single attack action."""
        # Check for dodge
        dodge_roll = random.randint(1, 100)
        if dodge_roll <= defender_stats["dodge"]:
            # Defender dodges - regenerate some HP
            regen_amount = random.randint(5, 15)
            max_hp = GLADIATORS[defender_name]["hp"]
            old_hp = fight_data[f"{defender_key}_hp"]
            fight_data[f"{defender_key}_hp"] = min(fight_data[f"{defender_key}_hp"] + regen_amount, max_hp)
            actual_regen = fight_data[f"{defender_key}_hp"] - old_hp
            
            return {
                "message": f"💨 **{defender_name} DODGED!** Agile movement regenerated {actual_regen} HP!",
                "defender_hp": fight_data[f"{defender_key}_hp"]
            }
        
        # Calculate base damage
        base_damage = random.randint(attacker_stats["attack"][0], attacker_stats["attack"][1])
        
        # Check for block
        block_roll = random.randint(1, 100)
        if block_roll <= defender_stats["defense"]:
            # Defender blocks - reduced damage and HP regen
            reduced_damage = max(1, base_damage // 3)
            regen_amount = random.randint(3, 10)
            max_hp = GLADIATORS[defender_name]["hp"]
            old_hp = fight_data[f"{defender_key}_hp"]
            fight_data[f"{defender_key}_hp"] = min(fight_data[f"{defender_key}_hp"] - reduced_damage + regen_amount, max_hp)
            actual_regen = (fight_data[f"{defender_key}_hp"] + reduced_damage) - old_hp
            
            return {
                "message": f"🛡️ **{defender_name} BLOCKED!** Reduced damage to {reduced_damage} and regenerated {actual_regen} HP!",
                "defender_hp": fight_data[f"{defender_key}_hp"]
            }
        
        # Normal hit
        fight_data[f"{defender_key}_hp"] -= base_damage
        
        # Determine hit quality
        if base_damage >= attacker_stats["attack"][1] - 2:
            hit_type = "💥 **CRITICAL HIT!**"
        elif base_damage <= attacker_stats["attack"][0] + 2:
            hit_type = "⚔️"
        else:
            hit_type = "⚔️ **SOLID HIT!**"
        
        return {
            "message": f"{hit_type} {attacker_name} deals {base_damage} damage to {defender_name}!",
            "defender_hp": fight_data[f"{defender_key}_hp"]
        }
    
    def create_health_bar(self, current_hp, max_hp):
        """Create a visual health bar."""
        if current_hp <= 0:
            return "💀 `░░░░░░░░░░` 0%"
        
        percentage = (current_hp / max_hp) * 100
        filled = int(percentage / 10)
        empty = 10 - filled
        
        if percentage >= 70:
            color = "🟩"
        elif percentage >= 40:
            color = "🟨"
        else:
            color = "🟥"
        
        bar = "█" * filled + "░" * empty
        
        return f"{color} `{bar}` {percentage:.0f}%"

# -----------------------------
# 🎴 BLACKJACK GAMBLING GAME
# -----------------------------

# Active blackjack games
active_blackjack = {}

class BlackjackGame:
    """Blackjack game state tracker"""
    def __init__(self, user_id, bet_amount, ctx):
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.ctx = ctx
        
        # Generate provably fair deck order
        results, self.client_seed, self.nonce, self.seed_hash = provably_fair.place_bet_multiple(
            user_id,
            "blackjack",
            bet_amount,
            52,  # 52 cards in deck
            104  # modulo 104 for 2-deck system
        )
        
        # Create and shuffle deck using provably fair results
        self.deck = self.create_shuffled_deck(results)
        self.player_hand = []
        self.dealer_hand = []
        self.game_over = False
        self.player_stood = False
    
    def create_shuffled_deck(self, results):
        """Create a deterministic shuffled deck from provably fair results"""
        suits = ['♠️', '♥️', '♣️', '♦️']
        ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        
        # Create ordered deck (2 decks for blackjack)
        ordered_deck = []
        for _ in range(2):
            for suit in suits:
                for rank in ranks:
                    ordered_deck.append(f"{rank}{suit}")
        
        # Shuffle using provably fair results
        shuffled_deck = []
        remaining_cards = ordered_deck.copy()
        
        for result in results:
            if remaining_cards:
                # Use result to pick from remaining cards
                index = result % len(remaining_cards)
                shuffled_deck.append(remaining_cards.pop(index))
        
        return shuffled_deck
    
    def card_value(self, card):
        """Get numerical value of a card"""
        # Remove emoji suit (last 2 characters for emojis like ♠️)
        rank = card[:-2]
        if rank in ['J', 'Q', 'K']:
            return 10
        elif rank == 'A':
            return 11  # Aces are initially 11, adjusted later if needed
        else:
            return int(rank)
    
    def hand_value(self, hand):
        """Calculate total value of a hand, adjusting for Aces"""
        total = sum(self.card_value(card) for card in hand)
        aces = sum(1 for card in hand if card[0] == 'A')
        
        # Adjust for Aces if over 21
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        
        return total
    
    def deal_card(self):
        """Deal a card from the deck"""
        if not self.deck:
            # If deck runs out (shouldn't happen with 104 cards), recreate with new provably fair shuffle
            results, self.client_seed, self.nonce, self.seed_hash = provably_fair.place_bet_multiple(
                self.user_id,
                "blackjack_reshuffle",
                0,
                52,
                104
            )
            self.deck = self.create_shuffled_deck(results)
        return self.deck.pop()
    
    def format_hand(self, hand, hide_first=False):
        """Format hand for display"""
        if hide_first:
            return f"🎴 {' '.join(hand[1:])} (? + {self.hand_value(hand[1:])})"
        return f"🎴 {' '.join(hand)} ({self.hand_value(hand)})"

class BlackjackView(View):
    """Interactive buttons for Blackjack game"""
    def __init__(self, game):
        super().__init__(timeout=180)  # Increased from 120 to 180 seconds (3 minutes)
        self.game = game
    
    async def update_game_display(self, interaction: discord.Interaction, result=None):
        """Update the game display"""
        dealer_hand_str = self.game.format_hand(
            self.game.dealer_hand, 
            hide_first=(not self.game.game_over)
        )
        player_hand_str = self.game.format_hand(self.game.player_hand)
        player_value = self.game.hand_value(self.game.player_hand)
        
        if result:
            # Game over - show results
            dealer_value = self.game.hand_value(self.game.dealer_hand)
            
            if result == "win":
                color = discord.Color.green()
                title = "🎉 BLACKJACK - YOU WIN!"
            elif result == "lose":
                color = discord.Color.red()
                title = "💀 BLACKJACK - YOU LOSE!"
            elif result == "push":
                color = discord.Color.gold()
                title = "🤝 BLACKJACK - PUSH!"
            elif result == "blackjack":
                color = discord.Color.green()
                title = "🎰 BLACKJACK! YOU WIN!"
            
            embed = discord.Embed(title=title, color=color)
            embed.add_field(
                name="🎩 Dealer's Hand",
                value=f"{' '.join(self.game.dealer_hand)}\n**Total: {dealer_value}**",
                inline=False
            )
            embed.add_field(
                name="👤 Your Hand",
                value=f"{' '.join(self.game.player_hand)}\n**Total: {player_value}**",
                inline=False
            )
            
            if result == "win" or result == "blackjack":
                payout = self.game.bet_amount * 2 if result == "win" else int(self.game.bet_amount * 2.5)
                embed.add_field(name="💰 Winnings", value=f"{format_money(payout)}", inline=True)
            elif result == "push":
                embed.add_field(name="💰 Returned", value=f"{format_money(self.game.bet_amount)}", inline=True)
            else:
                embed.add_field(name="💸 Lost", value=f"{format_money(self.game.bet_amount)}", inline=True)
            
            # Add provably fair info
            embed.add_field(
                name="🔐 Provably Fair",
                value=f"Nonce: `{self.game.nonce}` | Client: `{self.game.client_seed[:16]}...`\nSeed Hash: `{self.game.seed_hash[:16]}...`",
                inline=False
            )
            embed.set_footer(text="Play again with !blackjack <amount> | Use !verify to verify fairness")
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            # Game in progress
            embed = discord.Embed(
                title="🎴 BLACKJACK",
                description="Hit to draw a card, Stand to end your turn, or Double Down to double your bet and draw one final card!",
                color=discord.Color.blue()
            )
            embed.add_field(name="🎩 Dealer's Hand", value=dealer_hand_str, inline=False)
            embed.add_field(name="👤 Your Hand", value=player_hand_str, inline=False)
            embed.add_field(name="💰 Bet", value=format_money(self.game.bet_amount), inline=True)
            embed.set_footer(text="Make your move!")
            
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🎴")
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.user_id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return
        
        # Draw a card
        self.game.player_hand.append(self.game.deal_card())
        player_value = self.game.hand_value(self.game.player_hand)
        
        if player_value > 21:
            # Player busts
            self.game.game_over = True
            await self.finish_game(interaction, "lose", "You busted!")
        else:
            # Update display
            await self.update_game_display(interaction)
    
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success, emoji="🛑")
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.user_id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return
        
        self.game.player_stood = True
        await self.dealer_turn(interaction)
    
    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.danger, emoji="💰")
    async def double_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.user_id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return
        
        # Check if player has enough balance to double
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.game.user_id)
        
        if balance < self.game.bet_amount:
            await interaction.response.send_message("❌ Insufficient balance to double down!", ephemeral=True)
            return
        
        # Deduct additional bet
        balance -= self.game.bet_amount
        c.execute("UPDATE users SET balance=? WHERE user_id=?", (balance, self.game.user_id))
        conn.commit()
        
        # Double the bet
        self.game.bet_amount *= 2
        
        # Draw exactly one more card
        self.game.player_hand.append(self.game.deal_card())
        player_value = self.game.hand_value(self.game.player_hand)
        
        if player_value > 21:
            # Player busts
            self.game.game_over = True
            await self.finish_game(interaction, "lose", "You busted after doubling down!")
        else:
            # Automatically stand after double down
            self.game.player_stood = True
            await self.dealer_turn(interaction)
    
    async def dealer_turn(self, interaction: discord.Interaction):
        """Dealer draws until 17 or higher"""
        dealer_value = self.game.hand_value(self.game.dealer_hand)
        
        # Dealer must hit on 16 or less, stand on 17 or more
        while dealer_value < 17:
            self.game.dealer_hand.append(self.game.deal_card())
            dealer_value = self.game.hand_value(self.game.dealer_hand)
        
        self.game.game_over = True
        
        # Determine winner
        player_value = self.game.hand_value(self.game.player_hand)
        
        if dealer_value > 21:
            # Dealer busts - player wins
            await self.finish_game(interaction, "win", "Dealer busted!")
        elif player_value > dealer_value:
            # Player wins
            await self.finish_game(interaction, "win", "You have the higher hand!")
        elif player_value < dealer_value:
            # Dealer wins
            await self.finish_game(interaction, "lose", "Dealer has the higher hand!")
        else:
            # Push
            await self.finish_game(interaction, "push", "It's a tie!")
    
    async def finish_game(self, interaction: discord.Interaction, result, message):
        """Finish the game and update database"""
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.game.user_id)
        
        if result == "win":
            winnings = self.game.bet_amount * 2
            balance += winnings
            gambled += self.game.bet_amount
            total_gambled += self.game.bet_amount
            await log_bet_activity(self.game.user_id, self.game.bet_amount, "blackjack", "win")
        elif result == "blackjack":
            winnings = int(self.game.bet_amount * 2.5)
            balance += winnings
            gambled += self.game.bet_amount
            total_gambled += self.game.bet_amount
            await log_bet_activity(self.game.user_id, self.game.bet_amount, "blackjack", "win")
        elif result == "push":
            balance += self.game.bet_amount
            gambled += self.game.bet_amount
            total_gambled += self.game.bet_amount
            await log_bet_activity(self.game.user_id, self.game.bet_amount, "blackjack", "push")
        else:  # lose
            gambled += self.game.bet_amount
            total_gambled += self.game.bet_amount
            await log_bet_activity(self.game.user_id, self.game.bet_amount, "blackjack", "loss")
        
        # Update database
        c.execute(
            "UPDATE users SET balance=?, gambled=?, total_gambled=? WHERE user_id=?",
            (balance, gambled, total_gambled, self.game.user_id)
        )
        conn.commit()
        
        # Remove from active games
        if self.game.user_id in active_blackjack:
            del active_blackjack[self.game.user_id]
        
        # Show final result
        await self.update_game_display(interaction, result)

@bot.command(name="blackjack")
async def blackjack(ctx, amount: str = None):
    """Play Blackjack! Try to beat the dealer without going over 21!"""
    try:
        if amount is None:
            await ctx.send("❌ Usage: `!blackjack <amount>`\nExample: `!blackjack 10m`")
            return
        
        # Check if user already has an active game
        if ctx.author.id in active_blackjack:
            await ctx.send("❌ You already have an active Blackjack game! Finish it first.")
            return
        
        value = parse_money(amount)
        if value <= 0:
            await ctx.send("❌ Invalid amount format! Use k, m, or b (e.g., 10m, 5k).")
            return
        
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(ctx.author.id)
        
        if value > balance:
            await ctx.send("❌ You cannot bet more than your balance.")
            return
        
        # Check for rapid betting (fraud detection)
        is_rapid = await check_rapid_betting(ctx.author.id)
        if is_rapid:
            await send_fraud_alert(
                bot,
                ctx.author,
                "Rapid Betting Detected",
                f"User placed {RAPID_BET_THRESHOLD}+ bets in 60 seconds\nBet Amount: {value:,}$\nGame: Blackjack"
            )
        
        # Check for high bet (fraud detection)
        if value >= HIGH_BET_THRESHOLD:
            await log_user_activity(
                bot,
                ctx.author,
                "High Value Bet",
                f"Amount: {value:,}$\nGame: Blackjack\nBalance: {balance:,}$"
            )
        
        # Deduct bet from balance
        balance -= value
        c.execute("UPDATE users SET balance=? WHERE user_id=?", (balance, ctx.author.id))
        conn.commit()
        
        # Create game
        game = BlackjackGame(ctx.author.id, value, ctx)
        active_blackjack[ctx.author.id] = game
        
        # Deal initial cards
        game.player_hand.append(game.deal_card())
        game.dealer_hand.append(game.deal_card())
        game.player_hand.append(game.deal_card())
        game.dealer_hand.append(game.deal_card())
        
        # Check for immediate Blackjack
        player_value = game.hand_value(game.player_hand)
        dealer_value = game.hand_value(game.dealer_hand)
        
        if player_value == 21 and len(game.player_hand) == 2:
            # Player has Blackjack!
            if dealer_value == 21 and len(game.dealer_hand) == 2:
                # Both have Blackjack - Push
                game.game_over = True
                balance += value
                gambled += value
                total_gambled += value
                c.execute(
                    "UPDATE users SET balance=?, gambled=?, total_gambled=? WHERE user_id=?",
                    (balance, gambled, total_gambled, ctx.author.id)
                )
                conn.commit()
                await log_bet_activity(ctx.author.id, value, "blackjack", "push")
                
                embed = discord.Embed(
                    title="🤝 BOTH BLACKJACK - PUSH!",
                    description="Both you and the dealer have Blackjack!",
                    color=discord.Color.gold()
                )
                embed.add_field(
                    name="🎩 Dealer's Hand",
                    value=f"{' '.join(game.dealer_hand)}\n**Total: 21**",
                    inline=False
                )
                embed.add_field(
                    name="👤 Your Hand",
                    value=f"{' '.join(game.player_hand)}\n**Total: 21**",
                    inline=False
                )
                embed.add_field(name="💰 Returned", value=format_money(value), inline=True)
                embed.set_footer(text="Play again with !blackjack <amount>")
                
                del active_blackjack[ctx.author.id]
                await ctx.send(embed=embed)
            else:
                # Player has Blackjack, dealer doesn't - Player wins 2.5x
                game.game_over = True
                winnings = int(value * 2.5)
                balance += winnings
                gambled += value
                total_gambled += value
                c.execute(
                    "UPDATE users SET balance=?, gambled=?, total_gambled=? WHERE user_id=?",
                    (balance, gambled, total_gambled, ctx.author.id)
                )
                conn.commit()
                await log_bet_activity(ctx.author.id, value, "blackjack", "win")
                
                embed = discord.Embed(
                    title="🎰 BLACKJACK! YOU WIN!",
                    description="You got Blackjack! You win 2.5x your bet!",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="🎩 Dealer's Hand",
                    value=f"{' '.join(game.dealer_hand)}\n**Total: {dealer_value}**",
                    inline=False
                )
                embed.add_field(
                    name="👤 Your Hand",
                    value=f"{' '.join(game.player_hand)}\n**Total: 21 (BLACKJACK!)**",
                    inline=False
                )
                embed.add_field(name="💰 Winnings", value=format_money(winnings), inline=True)
                embed.set_footer(text="Play again with !blackjack <amount>")
                
                del active_blackjack[ctx.author.id]
                await ctx.send(embed=embed)
        else:
            # Normal game - show initial state with buttons
            view = BlackjackView(game)
            
            dealer_hand_str = game.format_hand(game.dealer_hand, hide_first=True)
            player_hand_str = game.format_hand(game.player_hand)
            
            embed = discord.Embed(
                title="🎴 BLACKJACK",
                description="Hit to draw a card, Stand to end your turn, or Double Down to double your bet and draw one final card!",
                color=discord.Color.blue()
            )
            embed.add_field(name="🎩 Dealer's Hand", value=dealer_hand_str, inline=False)
            embed.add_field(name="👤 Your Hand", value=player_hand_str, inline=False)
            embed.add_field(name="💰 Bet", value=format_money(value), inline=True)
            embed.set_footer(text="Make your move!")
            
            await ctx.send(embed=embed, view=view)
    
    except Exception as e:
        if ctx.author.id in active_blackjack:
            del active_blackjack[ctx.author.id]
        await ctx.send(f"❌ Error starting Blackjack: {str(e)}")

@bot.command(name="fight")
async def fight(ctx, opponent: discord.Member, amount: str):
    """
    Challenge another player to a gladiator fight!
    
    Usage: !fight @user <amount>
    Example: !fight @John 50m
    
    Both players bet the same amount, winner takes all!
    """
    try:
        # Parse amount
        value = parse_money(amount)
        if value is None:
            await ctx.send("❌ Invalid amount format! Use formats like `10m`, `5k`, or `1000`")
            return
        
        # Check if challenging yourself
        if ctx.author.id == opponent.id:
            await ctx.send("❌ You can't challenge yourself to a fight!")
            return
        
        # Check if opponent is a bot
        if opponent.bot:
            await ctx.send("❌ You can't challenge bots to fights!")
            return
        
        # Check minimum bet
        if value < 1_000_000:
            await ctx.send("❌ Minimum bet for gladiator fights is 1M!")
            return
        
        # Get challenger's balance
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(ctx.author.id)
        
        if value > balance:
            await ctx.send(f"❌ Insufficient balance! You have {balance:,}$ but need {value:,}$")
            return
        
        # Create unique challenge ID
        challenge_id = f"{ctx.author.id}_{opponent.id}_{int(datetime.now().timestamp())}"
        
        # Store fight data
        gladiator_fights[challenge_id] = {
            "player1": ctx.author.id,
            "player2": opponent.id,
            "bet": value,
            "accepted": False,
            "p1_gladiator": None,
            "p2_gladiator": None,
            "p1_hp": 0,
            "p2_hp": 0
        }
        
        # Create challenge embed
        embed = discord.Embed(
            title="⚔️ Gladiator Fight Challenge!",
            description=f"{ctx.author.mention} challenges {opponent.mention} to a gladiator duel!",
            color=discord.Color.orange()
        )
        embed.add_field(name="💰 Wager", value=f"{value:,}$ each side", inline=True)
        embed.add_field(name="🏆 Winner Takes", value=f"{value * 2:,}$", inline=True)
        embed.add_field(name="🎮 How to Play", value="1. Accept the challenge\n2. Both pick a gladiator\n3. Watch the epic battle!\n4. Winner takes all!", inline=False)
        embed.set_footer(text=f"{opponent.display_name}, click Accept or Decline below")
        
        # Create view
        view = GladiatorConfirmView(ctx.author.id, opponent.id, value, challenge_id)
        
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Error creating fight challenge: {str(e)}")

@bot.command(name="pickgladiator")
async def pick_gladiator(ctx, *, gladiator_name: str):
    """
    Pick your gladiator for the fight.
    
    Usage: !pickgladiator <gladiator_name>
    Example: !pickgladiator Maximus
    """
    try:
        # Find user's active fight
        user_fight = None
        challenge_id = None
        
        for cid, fight_data in gladiator_fights.items():
            if not fight_data["accepted"]:
                continue
            
            if ctx.author.id == fight_data["player1"] and fight_data["p1_gladiator"] is None:
                user_fight = fight_data
                challenge_id = cid
                player_key = "p1"
                break
            elif ctx.author.id == fight_data["player2"] and fight_data["p2_gladiator"] is None:
                user_fight = fight_data
                challenge_id = cid
                player_key = "p2"
                break
        
        if user_fight is None:
            await ctx.send("❌ You don't have an active fight waiting for gladiator selection!")
            return
        
        # Find gladiator (case-insensitive)
        selected_gladiator = None
        for name in GLADIATORS.keys():
            if name.lower() == gladiator_name.lower():
                selected_gladiator = name
                break
        
        if selected_gladiator is None:
            available = ", ".join(GLADIATORS.keys())
            await ctx.send(f"❌ Unknown gladiator! Available fighters: {available}")
            return
        
        # Assign gladiator
        user_fight[f"{player_key}_gladiator"] = selected_gladiator
        user_fight[f"{player_key}_hp"] = GLADIATORS[selected_gladiator]["hp"]
        
        glad_stats = GLADIATORS[selected_gladiator]
        
        # Send confirmation
        embed = discord.Embed(
            title=f"{glad_stats['icon']} Gladiator Selected!",
            description=f"{ctx.author.mention} chose **{selected_gladiator}**!",
            color=discord.Color.green()
        )
        embed.add_field(name="❤️ Health", value=str(glad_stats["hp"]), inline=True)
        embed.add_field(name="⚔️ Attack", value=f"{glad_stats['attack'][0]}-{glad_stats['attack'][1]}", inline=True)
        embed.add_field(name="🛡️ Defense", value=f"{glad_stats['defense']}%", inline=True)
        embed.add_field(name="💨 Dodge", value=f"{glad_stats['dodge']}%", inline=True)
        
        # Check if both players have selected
        if user_fight["p1_gladiator"] and user_fight["p2_gladiator"]:
            embed.add_field(name="🎮 Fight Status", value="✅ **BOTH GLADIATORS READY!**\nStarting battle...", inline=False)
            await ctx.send(embed=embed)
            
            # Start the fight!
            await asyncio.sleep(2)
            
            # Create fight view
            fight_view = GladiatorFightView(user_fight["player1"], user_fight["player2"], user_fight["bet"], challenge_id)
            
            # Run fight animation
            await fight_view.run_fight_animation(ctx.channel, user_fight)
        else:
            waiting_player = "player1" if user_fight["p1_gladiator"] is None else "player2"
            embed.add_field(name="⏳ Waiting", value=f"Waiting for <@{user_fight[waiting_player]}> to pick their gladiator...", inline=False)
            await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error selecting gladiator: {str(e)}")

# -----------------------------
# 🪓 RISKY LUMBERJACK COMMAND
# -----------------------------
# Active lumberjack games storage
lumberjack_games = {}
word_chain_games = {}

@bot.command(name="choptree")
async def choptree(ctx, opponent: discord.Member, amount: str):
    """
    Challenge another player to Risky Lumberjack!
    
    Usage: !choptree @user <amount>
    Example: !choptree @John 25m
    
    Take turns cutting the tree. The player who makes it fall loses!
    """
    try:
        # Validate opponent
        if opponent.bot or opponent.id == ctx.author.id:
            return await ctx.send("❌ Cannot challenge bots or yourself!")
        
        # Parse bet amount
        bet_amount = parse_money(amount)
        if bet_amount < 10_000_000:
            return await ctx.send("❌ Minimum bet is 10M!")
        
        # Check if users already in a game
        if ctx.author.id in lumberjack_games or opponent.id in lumberjack_games:
            return await ctx.send("❌ One of you is already in a lumberjack game!")
        
        # Validate balances
        c.execute("SELECT balance FROM users WHERE user_id = ?", (ctx.author.id,))
        challenger_data = c.execute("SELECT balance FROM users WHERE user_id = ?", (ctx.author.id,)).fetchone()
        opponent_data = c.execute("SELECT balance FROM users WHERE user_id = ?", (opponent.id,)).fetchone()
        
        if not challenger_data or challenger_data[0] < bet_amount:
            return await ctx.send(f"❌ You need at least {format_money(bet_amount)} to play!")
        
        if not opponent_data or opponent_data[0] < bet_amount:
            return await ctx.send(f"❌ {opponent.mention} doesn't have enough balance!")
        
        # Create challenge embed
        embed = discord.Embed(
            title="🪓 Risky Lumberjack Challenge!",
            description=f"{ctx.author.mention} has challenged {opponent.mention} to a tree-cutting duel!",
            color=discord.Color.dark_green()
        )
        embed.add_field(name="💰 Bet Amount", value=f"{format_money(bet_amount)} each", inline=True)
        embed.add_field(name="🏆 Prize", value=f"{format_money(bet_amount * 2)}", inline=True)
        embed.add_field(
            name="🎮 How to Play",
            value="Take turns using `!chop` to cut sections of the tree. The player who makes the tree fall loses!\n⏰ **60 seconds per turn** or you forfeit!",
            inline=False
        )
        
        # Create accept/decline view
        view = LumberjackChallengeView(ctx.author, opponent, bet_amount)
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Error starting lumberjack game: {str(e)}")

class LumberjackChallengeView(discord.ui.View):
    """View for accepting/declining lumberjack challenge."""
    
    def __init__(self, challenger, opponent, bet_amount):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.bet_amount = bet_amount
        
    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Accept the challenge."""
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        # Initialize game
        tree_health = random.randint(15, 25)  # Random tree health
        game_data = {
            "player1": self.challenger.id,
            "player2": self.opponent.id,
            "bet": self.bet_amount,
            "tree_health": tree_health,
            "max_health": tree_health,
            "current_turn": self.challenger.id,
            "turns_taken": 0,
            "channel_id": interaction.channel.id,
            "turn_start_time": datetime.now()  # Track when turn started
        }
        
        lumberjack_games[self.challenger.id] = game_data
        lumberjack_games[self.opponent.id] = game_data
        
        # Show game started
        embed = discord.Embed(
            title="🪓 RISKY LUMBERJACK",
            description=f"The tree stands tall! Take turns chopping with `!chop`",
            color=discord.Color.dark_green()
        )
        embed.add_field(name="🌳 Tree Health", value=f"**{tree_health}/{tree_health}**", inline=True)
        embed.add_field(name="💰 Prize Pool", value=format_money(self.bet_amount * 2), inline=True)
        embed.add_field(
            name="⏳ Current Turn",
            value=f"<@{self.challenger.id}>",
            inline=False
        )
        embed.add_field(
            name="ℹ️ Game Rules",
            value=(
                "• Each chop removes 1-3 tree health\n"
                "• The player who reduces tree health to 0 loses!\n"
                "• You have 60 seconds per turn or you forfeit!\n"
                "• Think carefully about your timing!"
            ),
            inline=False
        )
        embed.set_footer(text=f"Turns: 0 • Use !chop to cut the tree")
        
        await interaction.response.edit_message(embed=embed, view=self)
        
    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Decline the challenge."""
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
        
        embed = discord.Embed(
            title="❌ Challenge Declined",
            description=f"{self.opponent.mention} declined the lumberjack challenge!",
            color=discord.Color.red()
        )
        
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command(name="chop")
async def chop(ctx):
    """
    Take your turn chopping the tree!
    
    Usage: !chop
    
    Each chop deals 1-3 damage to the tree. Make the tree fall and you lose!
    """
    try:
        # Check if user is in a game
        if ctx.author.id not in lumberjack_games:
            return await ctx.send("❌ You're not in a lumberjack game! Use `!choptree @user <amount>` to start one.")
        
        game_data = lumberjack_games[ctx.author.id]
        
        # Check if it's user's turn
        if game_data["current_turn"] != ctx.author.id:
            # Check if the current turn player has timed out (60 seconds)
            time_since_turn = datetime.now() - game_data["turn_start_time"]
            if time_since_turn.total_seconds() > 60:
                # Current player timed out - they forfeit
                forfeit_player_id = game_data["current_turn"]
                winner_id = game_data["player1"] if forfeit_player_id == game_data["player2"] else game_data["player2"]
                
                # Update balances
                c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (game_data["bet"], forfeit_player_id))
                c.execute("UPDATE users SET balance = balance + ?, total_gambled = total_gambled + ? WHERE user_id = ?", 
                         (game_data["bet"], game_data["bet"], winner_id))
                conn.commit()
                
                # Log transactions
                log_transaction(forfeit_player_id, "lumberjack_loss", game_data["bet"], 0, 0, f"Lost lumberjack game by timeout vs user {winner_id}")
                log_transaction(winner_id, "lumberjack_win", game_data["bet"], 0, 0, f"Won lumberjack game by opponent timeout vs user {forfeit_player_id}")
                await log_bet_activity(winner_id, game_data["bet"], "lumberjack", "win")
                await log_bet_activity(forfeit_player_id, game_data["bet"], "lumberjack", "loss")
                
                # Forfeit embed
                embed = discord.Embed(
                    title="⏰ FORFEIT - TIME RAN OUT!",
                    description=f"<@{forfeit_player_id}> took too long to chop (60 seconds)!",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="🏆 Winner by Forfeit",
                    value=f"<@{winner_id}>",
                    inline=True
                )
                embed.add_field(
                    name="💔 Loser",
                    value=f"<@{forfeit_player_id}>",
                    inline=True
                )
                embed.add_field(
                    name="💰 Winnings",
                    value=format_money(game_data["bet"] * 2),
                    inline=False
                )
                embed.set_footer(text=f"Game ended at turn {game_data['turns_taken']}")
                
                # Clean up game
                del lumberjack_games[game_data["player1"]]
                del lumberjack_games[game_data["player2"]]
                
                return await ctx.send(embed=embed)
            else:
                other_player = game_data["player1"] if game_data["current_turn"] == game_data["player1"] else game_data["player2"]
                return await ctx.send(f"❌ It's <@{other_player}>'s turn!")
        
        # Check if in correct channel
        if game_data["channel_id"] != ctx.channel.id:
            return await ctx.send("❌ You must chop in the channel where the game started!")
        
        # Calculate damage (1-3)
        damage = random.randint(1, 3)
        game_data["tree_health"] -= damage
        game_data["turns_taken"] += 1
        
        # Create action message
        action_messages = {
            1: f"🪓 {ctx.author.mention} carefully chips away at the tree... (-1 HP)",
            2: f"🪓🪓 {ctx.author.mention} takes a solid swing! (-2 HP)",
            3: f"🪓🪓🪓 {ctx.author.mention} lands a powerful chop! (-3 HP)"
        }
        
        # Check if tree fell (player loses)
        if game_data["tree_health"] <= 0:
            # Tree fell - current player loses!
            loser_id = ctx.author.id
            winner_id = game_data["player1"] if loser_id == game_data["player2"] else game_data["player2"]
            
            # Update balances
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (game_data["bet"], loser_id))
            c.execute("UPDATE users SET balance = balance + ?, total_gambled = total_gambled + ? WHERE user_id = ?", 
                     (game_data["bet"], game_data["bet"], winner_id))
            conn.commit()
            
            # Log transactions
            log_transaction(loser_id, "lumberjack_loss", game_data["bet"], 0, 0, f"Lost lumberjack game vs user {winner_id}")
            log_transaction(winner_id, "lumberjack_win", game_data["bet"], 0, 0, f"Won lumberjack game vs user {loser_id}")
            await log_bet_activity(winner_id, game_data["bet"], "lumberjack", "win")
            await log_bet_activity(loser_id, game_data["bet"], "lumberjack", "loss")
            
            # Victory embed
            embed = discord.Embed(
                title="💥 THE TREE HAS FALLEN!",
                description=f"The tree crashed down on {ctx.author.mention}!",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="🏆 Winner",
                value=f"<@{winner_id}>",
                inline=True
            )
            embed.add_field(
                name="💔 Loser",
                value=f"<@{loser_id}>",
                inline=True
            )
            embed.add_field(
                name="💰 Winnings",
                value=format_money(game_data["bet"] * 2),
                inline=False
            )
            embed.add_field(
                name="📊 Game Stats",
                value=f"Total Turns: {game_data['turns_taken']}\nFinal Damage: {abs(game_data['tree_health'])} HP overkill",
                inline=False
            )
            embed.set_footer(text=f"The tree stood for {game_data['turns_taken']} turns")
            
            # Clean up game
            del lumberjack_games[game_data["player1"]]
            del lumberjack_games[game_data["player2"]]
            
            await ctx.send(embed=embed)
            
        else:
            # Tree still standing - switch turns
            game_data["current_turn"] = game_data["player2"] if game_data["current_turn"] == game_data["player1"] else game_data["player1"]
            game_data["turn_start_time"] = datetime.now()  # Reset turn timer
            
            # Create health bar
            health_percent = (game_data["tree_health"] / game_data["max_health"]) * 100
            if health_percent > 60:
                bar_color = "🟩"
            elif health_percent > 30:
                bar_color = "🟨"
            else:
                bar_color = "🟥"
            
            filled = int((game_data["tree_health"] / game_data["max_health"]) * 10)
            empty = 10 - filled
            health_bar = bar_color + " " + "█" * filled + "░" * empty
            
            embed = discord.Embed(
                title="🪓 RISKY LUMBERJACK",
                description=action_messages[damage],
                color=discord.Color.dark_green() if health_percent > 30 else discord.Color.orange()
            )
            embed.add_field(
                name="🌳 Tree Health",
                value=f"{health_bar}\n**{game_data['tree_health']}/{game_data['max_health']} HP**",
                inline=False
            )
            embed.add_field(
                name="⏳ Next Turn",
                value=f"<@{game_data['current_turn']}>",
                inline=True
            )
            embed.add_field(
                name="💰 Prize Pool",
                value=format_money(game_data["bet"] * 2),
                inline=True
            )
            embed.set_footer(text=f"Turns: {game_data['turns_taken']} • Use !chop to cut the tree")
            
            if game_data["tree_health"] <= 3:
                embed.add_field(
                    name="⚠️ WARNING",
                    value="The tree is about to fall! Next chop could end the game!",
                    inline=False
                )
            
            await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error during chop: {str(e)}")

# -----------------------------
# 🔤 WORD CHAIN GAME
# -----------------------------

@bot.command(name="wordchain")
async def wordchain(ctx, opponent: discord.Member, amount: str):
    """
    Challenge another player to Word Chain!
    
    Usage: !wordchain @user <amount>
    Example: !wordchain @John 25m
    
    Take turns saying words that start with the last letter of the previous word.
    30 seconds per turn. Repeats or timeouts = loss!
    """
    try:
        # Validate opponent
        if opponent.bot or opponent.id == ctx.author.id:
            return await ctx.send("❌ Cannot challenge bots or yourself!")
        
        # Parse bet amount
        bet_amount = parse_money(amount)
        if bet_amount < 10_000_000:
            return await ctx.send("❌ Minimum bet is 10M!")
        
        # Check if users already in a game
        if ctx.author.id in word_chain_games or opponent.id in word_chain_games:
            return await ctx.send("❌ One of you is already in a word chain game!")
        
        # Validate balances
        challenger_data = c.execute("SELECT balance FROM users WHERE user_id = ?", (ctx.author.id,)).fetchone()
        opponent_data = c.execute("SELECT balance FROM users WHERE user_id = ?", (opponent.id,)).fetchone()
        
        if not challenger_data or challenger_data[0] < bet_amount:
            return await ctx.send(f"❌ You need at least {format_money(bet_amount)} to play!")
        
        if not opponent_data or opponent_data[0] < bet_amount:
            return await ctx.send(f"❌ {opponent.mention} doesn't have enough balance!")
        
        # Create challenge embed
        embed = discord.Embed(
            title="🔤 Word Chain Challenge!",
            description=f"{ctx.author.mention} has challenged {opponent.mention} to a word chain battle!",
            color=discord.Color.blue()
        )
        embed.add_field(name="💰 Bet Amount", value=f"{format_money(bet_amount)} each", inline=True)
        embed.add_field(name="🏆 Prize", value=f"{format_money(bet_amount * 2)}", inline=True)
        embed.add_field(
            name="🎮 How to Play",
            value=(
                "Take turns using `!word <your_word>` to continue the chain!\n"
                "• Each word must start with the last letter of the previous word\n"
                "• You have **30 seconds** per turn\n"
                "• No repeating words!\n"
                "• Timeout or invalid word = you lose!"
            ),
            inline=False
        )
        embed.add_field(
            name="📝 Example",
            value="Apple → **E**lephant → **T**urtle → **E**agle",
            inline=False
        )
        
        # Create accept/decline view
        view = WordChainChallengeView(ctx.author, opponent, bet_amount)
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Error starting word chain game: {str(e)}")

class WordChainChallengeView(discord.ui.View):
    """View for accepting/declining word chain challenge."""
    
    def __init__(self, challenger, opponent, bet_amount):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.bet_amount = bet_amount
        
    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Accept the challenge."""
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        # Initialize game
        game_data = {
            "player1": self.challenger.id,
            "player2": self.opponent.id,
            "bet": self.bet_amount,
            "current_turn": self.challenger.id,
            "last_word": None,
            "used_words": set(),
            "turns_taken": 0,
            "channel_id": interaction.channel.id,
            "turn_start_time": datetime.utcnow()
        }
        
        word_chain_games[self.challenger.id] = game_data
        word_chain_games[self.opponent.id] = game_data
        
        # Show game started
        embed = discord.Embed(
            title="🔤 WORD CHAIN",
            description=f"The word chain begins! {self.challenger.mention}, start us off!",
            color=discord.Color.blue()
        )
        embed.add_field(name="⏰ Time Limit", value="30 seconds per turn", inline=True)
        embed.add_field(name="💰 Prize Pool", value=format_money(self.bet_amount * 2), inline=True)
        embed.add_field(
            name="⏳ Current Turn",
            value=f"<@{self.challenger.id}>",
            inline=False
        )
        embed.add_field(
            name="📝 Instructions",
            value="Use `!word <your_word>` to play your word. It can be any word to start!",
            inline=False
        )
        embed.set_footer(text="Turns: 0 • No repeats allowed!")
        
        await interaction.response.edit_message(embed=embed, view=self)
        
    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Decline the challenge."""
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
        
        embed = discord.Embed(
            title="❌ Challenge Declined",
            description=f"{self.opponent.mention} declined the word chain challenge.",
            color=discord.Color.red()
        )
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command(name="word")
async def word(ctx, user_word: str = None):
    """
    Play your word in the word chain!
    
    Usage: !word <your_word>
    Example: !word elephant
    
    Your word must start with the last letter of the previous word!
    """
    try:
        # Check if word was provided
        if not user_word:
            return await ctx.send("❌ Please provide a word! Usage: `!word <your_word>`")
        
        # Clean and validate word
        user_word = user_word.lower().strip()
        if not user_word.isalpha():
            return await ctx.send("❌ Word must contain only letters!")
        
        # Check if user is in a game
        if ctx.author.id not in word_chain_games:
            return await ctx.send("❌ You're not in a word chain game! Use `!wordchain @user <amount>` to start one.")
        
        game_data = word_chain_games[ctx.author.id]
        
        # Check if it's user's turn
        if game_data["current_turn"] != ctx.author.id:
            other_player = game_data["player1"] if game_data["current_turn"] == game_data["player1"] else game_data["player2"]
            return await ctx.send(f"❌ It's <@{other_player}>'s turn!")
        
        # Check if in correct channel
        if game_data["channel_id"] != ctx.channel.id:
            return await ctx.send("❌ You must play in the channel where the game started!")
        
        # Check timeout (30 seconds)
        time_elapsed = (datetime.utcnow() - game_data["turn_start_time"]).total_seconds()
        if time_elapsed > 30:
            # Timeout - current player loses
            await handle_word_chain_loss(ctx, game_data, ctx.author.id, "⏰ Time's up!")
            return
        
        # Check if word was already used
        if user_word in game_data["used_words"]:
            await handle_word_chain_loss(ctx, game_data, ctx.author.id, f"❌ '{user_word}' was already used!")
            return
        
        # Check if word starts with correct letter
        if game_data["last_word"]:
            required_letter = game_data["last_word"][-1]
            if user_word[0] != required_letter:
                await handle_word_chain_loss(ctx, game_data, ctx.author.id, 
                    f"❌ Word must start with '{required_letter.upper()}'!")
                return
        
        # Valid word! Update game state
        game_data["last_word"] = user_word
        game_data["used_words"].add(user_word)
        game_data["turns_taken"] += 1
        game_data["current_turn"] = game_data["player2"] if game_data["current_turn"] == game_data["player1"] else game_data["player1"]
        game_data["turn_start_time"] = datetime.utcnow()
        
        next_letter = user_word[-1].upper()
        
        # Create update embed
        embed = discord.Embed(
            title="🔤 WORD CHAIN",
            description=f"✅ {ctx.author.mention} played: **{user_word.upper()}**",
            color=discord.Color.green()
        )
        embed.add_field(
            name="⏳ Next Turn",
            value=f"<@{game_data['current_turn']}>",
            inline=True
        )
        embed.add_field(
            name="🔤 Next Letter",
            value=f"Word must start with **{next_letter}**",
            inline=True
        )
        embed.add_field(
            name="💰 Prize Pool",
            value=format_money(game_data["bet"] * 2),
            inline=True
        )
        embed.add_field(
            name="📝 Word Chain",
            value=" → ".join([w.capitalize() for w in list(game_data["used_words"])[-5:]]),
            inline=False
        )
        embed.set_footer(text=f"Turns: {game_data['turns_taken']} • 30 seconds per turn • No repeats!")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error playing word: {str(e)}")

async def handle_word_chain_loss(ctx, game_data, loser_id, reason):
    """Handle word chain game loss."""
    winner_id = game_data["player1"] if loser_id == game_data["player2"] else game_data["player2"]
    
    # Update balances
    c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (game_data["bet"], loser_id))
    c.execute("UPDATE users SET balance = balance + ?, total_gambled = total_gambled + ? WHERE user_id = ?", 
             (game_data["bet"], game_data["bet"], winner_id))
    conn.commit()
    
    # Log transactions
    log_transaction(loser_id, "wordchain_loss", game_data["bet"], 0, 0, f"Lost word chain game vs user {winner_id}")
    log_transaction(winner_id, "wordchain_win", game_data["bet"], 0, 0, f"Won word chain game vs user {loser_id}")
    await log_bet_activity(winner_id, game_data["bet"], "wordchain", "win")
    await log_bet_activity(loser_id, game_data["bet"], "wordchain", "loss")
    
    # Victory embed
    embed = discord.Embed(
        title="🏆 WORD CHAIN COMPLETE!",
        description=reason,
        color=discord.Color.gold()
    )
    embed.add_field(
        name="🏆 Winner",
        value=f"<@{winner_id}>",
        inline=True
    )
    embed.add_field(
        name="💔 Loser",
        value=f"<@{loser_id}>",
        inline=True
    )
    embed.add_field(
        name="💰 Winnings",
        value=format_money(game_data["bet"] * 2),
        inline=False
    )
    embed.add_field(
        name="📊 Game Stats",
        value=f"Total Turns: {game_data['turns_taken']}\nWords Used: {len(game_data['used_words'])}",
        inline=False
    )
    if game_data["used_words"]:
        word_list = " → ".join([w.capitalize() for w in list(game_data["used_words"])])
        embed.add_field(
            name="📝 Complete Chain",
            value=word_list[:1024],  # Discord field limit
            inline=False
        )
    embed.set_footer(text=f"Game lasted {game_data['turns_taken']} turns")
    
    # Clean up game
    del word_chain_games[game_data["player1"]]
    del word_chain_games[game_data["player2"]]
    
    await ctx.send(embed=embed)

# -----------------------------
# 🎰 LIMBO GAME
# -----------------------------
limbo_games = {}  # {user_id: {"bet": int, "message_id": int, "channel_id": int}}

class LimboView(discord.ui.View):
    """View for Limbo game buttons."""
    
    def __init__(self, user_id, bet_amount):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bet_amount = bet_amount
    
    @discord.ui.button(label="⬆️ Above 50", style=discord.ButtonStyle.green, custom_id="limbo_above")
    async def above_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle Above 50 button click."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your game!", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self.resolve_limbo(interaction, "above")
    
    @discord.ui.button(label="⬇️ Below 50", style=discord.ButtonStyle.red, custom_id="limbo_below")
    async def below_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle Below 50 button click."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your game!", ephemeral=True)
            return
        
        await interaction.response.defer()
        await self.resolve_limbo(interaction, "below")
    
    async def resolve_limbo(self, interaction, choice):
        """Resolve the Limbo game."""
        try:
            # Clean up game tracking
            if self.user_id in limbo_games:
                del limbo_games[self.user_id]
            
            # Disable buttons
            for item in self.children:
                item.disabled = True
            
            # Generate provably fair number between 1-100
            result, client_seed, nonce, seed_hash = provably_fair.place_bet(
                self.user_id, "limbo", self.bet_amount, 100
            )
            roll = result + 1  # Convert 0-99 to 1-100
            
            # Determine if player wins
            if choice == "above":
                player_wins = roll > 50
                choice_text = "⬆️ **Above 50**"
            else:  # below
                player_wins = roll < 50
                choice_text = "⬇️ **Below 50**"
            
            # Calculate payout multiplier based on bet amount
            # Higher bets get slightly better multipliers (casino-style)
            # But keep house edge around 5-10%
            if self.bet_amount >= 100_000_000:  # 100M+
                base_multiplier = 1.90
            elif self.bet_amount >= 50_000_000:  # 50M+
                base_multiplier = 1.88
            elif self.bet_amount >= 25_000_000:  # 25M+
                base_multiplier = 1.86
            elif self.bet_amount >= 10_000_000:  # 10M+
                base_multiplier = 1.84
            else:  # Under 10M
                base_multiplier = 1.82
            
            if player_wins:
                # Player wins!
                winnings = int(self.bet_amount * base_multiplier)
                profit = winnings - self.bet_amount
                
                # Update balance
                c.execute("UPDATE users SET balance = balance + ?, gambled = gambled + ?, total_gambled = total_gambled + ? WHERE user_id = ?", 
                         (profit, self.bet_amount, self.bet_amount, self.user_id))
                conn.commit()
                
                # Log transaction
                log_transaction(self.user_id, "limbo_win", winnings, 0, 0, f"Won Limbo game - rolled {roll}, chose {choice}")
                await log_bet_activity(self.user_id, self.bet_amount, "limbo", "win")
                
                # Create win embed
                embed = discord.Embed(
                    title="🎉 LIMBO - YOU WIN!",
                    description=f"The number was **{roll}**!",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="🎲 Your Choice",
                    value=choice_text,
                    inline=True
                )
                embed.add_field(
                    name="🎯 Result",
                    value=f"**{roll}**",
                    inline=True
                )
                embed.add_field(
                    name="💰 Winnings",
                    value=f"{format_money(winnings)} ({base_multiplier}x)",
                    inline=False
                )
                embed.add_field(
                    name="📈 Profit",
                    value=f"+{format_money(profit)}",
                    inline=True
                )
                
                # Add provably fair information
                embed.add_field(
                    name="🔐 Provably Fair",
                    value=f"Nonce: {nonce} | Client: {client_seed[:8]}...\nSeed Hash: {seed_hash[:16]}...\nUse `!verify` to verify fairness",
                    inline=False
                )
                
                embed.set_footer(text=f"Bet: {format_money(self.bet_amount)} • Multiplier: {base_multiplier}x")
                
            else:
                # Player loses
                # Update balance
                c.execute("UPDATE users SET balance = balance - ?, gambled = gambled + ?, total_gambled = total_gambled + ? WHERE user_id = ?", 
                         (self.bet_amount, self.bet_amount, self.bet_amount, self.user_id))
                conn.commit()
                
                # Log transaction
                log_transaction(self.user_id, "limbo_loss", self.bet_amount, 0, 0, f"Lost Limbo game - rolled {roll}, chose {choice}")
                await log_bet_activity(self.user_id, self.bet_amount, "limbo", "loss")
                
                # Create loss embed
                embed = discord.Embed(
                    title="💀 LIMBO - YOU LOSE",
                    description=f"The number was **{roll}**!",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="🎲 Your Choice",
                    value=choice_text,
                    inline=True
                )
                embed.add_field(
                    name="🎯 Result",
                    value=f"**{roll}**",
                    inline=True
                )
                embed.add_field(
                    name="💸 Lost",
                    value=format_money(self.bet_amount),
                    inline=False
                )
                
                # Add provably fair information
                embed.add_field(
                    name="🔐 Provably Fair",
                    value=f"Nonce: {nonce} | Client: {client_seed[:8]}...\nSeed Hash: {seed_hash[:16]}...\nUse `!verify` to verify fairness",
                    inline=False
                )
                
                embed.set_footer(text=f"Better luck next time! • Try again with !limbo <amount>")
            
            await interaction.edit_original_response(embed=embed, view=self)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error resolving Limbo game: {str(e)}", ephemeral=True)

@bot.command(name="limbo")
async def limbo(ctx, amount: str):
    """
    Play Limbo! Will the number be above or below 50?
    
    Usage: !limbo <amount>
    Example: !limbo 10m
    
    Higher bets = higher multipliers!
    """
    try:
        # Check if user already has an active game
        if ctx.author.id in limbo_games:
            await ctx.send("❌ You already have an active Limbo game! Finish it first.")
            return
        
        # Parse bet amount
        bet_amount = parse_money(amount)
        if bet_amount <= 0:
            await ctx.send("❌ Invalid amount format! Use k, m, or b (e.g., 10m, 5k).")
            return
        
        if bet_amount < 1_000_000:
            await ctx.send("❌ Minimum bet is 1M!")
            return
        
        # Check user balance
        c.execute("SELECT balance FROM users WHERE user_id = ?", (ctx.author.id,))
        result = c.fetchone()
        
        if not result or result[0] < bet_amount:
            await ctx.send("❌ Insufficient balance!")
            return
        
        # Determine multiplier for display
        if bet_amount >= 100_000_000:
            multiplier = 1.90
        elif bet_amount >= 50_000_000:
            multiplier = 1.88
        elif bet_amount >= 25_000_000:
            multiplier = 1.86
        elif bet_amount >= 10_000_000:
            multiplier = 1.84
        else:
            multiplier = 1.82
        
        # Create game embed
        embed = discord.Embed(
            title="🎰 LIMBO",
            description="Will the number be **Above** or **Below** 50?",
            color=discord.Color.purple()
        )
        embed.add_field(
            name="💰 Your Bet",
            value=format_money(bet_amount),
            inline=True
        )
        embed.add_field(
            name="📊 Multiplier",
            value=f"**{multiplier}x**",
            inline=True
        )
        embed.add_field(
            name="🎯 Potential Win",
            value=format_money(int(bet_amount * multiplier)),
            inline=False
        )
        embed.add_field(
            name="🎲 Choose Your Bet",
            value="Click ⬆️ **Above 50** or ⬇️ **Below 50**",
            inline=False
        )
        embed.set_footer(text="Higher bets = higher multipliers! • 60 second timeout")
        
        # Create view
        view = LimboView(ctx.author.id, bet_amount)
        
        # Send message
        message = await ctx.send(embed=embed, view=view)
        
        # Track active game
        limbo_games[ctx.author.id] = {
            "bet": bet_amount,
            "message_id": message.id,
            "channel_id": ctx.channel.id
        }
        
    except ValueError:
        await ctx.send("❌ Invalid amount! Use formats like: 1m, 500k, 1000000")
    except Exception as e:
        await ctx.send(f"❌ Error starting Limbo: {str(e)}")

# -----------------------------
# 📜 RULES COMMAND
# -----------------------------
# Games Pagination View
class GamesView(discord.ui.View):
    """View for paginated games information."""
    
    def __init__(self, user_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user_id = user_id
        self.current_page = 0
        self.pages = self.create_pages()
        
    def create_pages(self):
        """Create all game information pages."""
        pages = []
        
        # Page 1: Daily Spin Wheel (REPLACING WORD CHAIN)
        embed0 = discord.Embed(
            title="🎰 Daily Spin Wheel",
            description="**Spin the mega wheel daily for amazing prizes!**",
            color=discord.Color.gold()
        )
        embed0.add_field(
            name="📋 Commands",
            value=(
                "`!spinwheel` - Spin the wheel\n"
                "`!buyspin` - Purchase spins (10M each, 3 for 30M)\n"
                "`!spincom` - View all spin commands\n"
                "`!wheelstats` - View your statistics"
            ),
            inline=False
        )
        embed0.add_field(
            name="💡 Example",
            value="`!spinwheel` then click **SPIN!**",
            inline=False
        )
        embed0.add_field(
            name="🎮 How It Works",
            value=(
                "• Get **1 free spin daily** (resets 24h after use)\n"
                "• **Purchase spins** with `!buyspin` (they stack!)\n"
                "• Free spins used first, then purchased spins\n"
                "• Click **SPIN!** button to spin the wheel\n"
                "• Interactive animation shows prize selection"
            ),
            inline=False
        )
        embed0.add_field(
            name="💰 FREE SPIN PRIZES",
            value=(
                "• **3M** (55%) - Most common\n"
                "• **10M** (34%) - Common\n"
                "• **25M** (2%) - Uncommon\n"
                "• **50M** (1%) - Rare\n"
                "• **Stock Pet** (0.5%) - Very rare!\n"
                "• **200M** (0.5%) - Jackpot!"
            ),
            inline=True
        )
        embed0.add_field(
            name="💎 PAID SPIN PRIZES (BETTER!)",
            value=(
                "• **6.5M** (55%) - Enhanced!\n"
                "• **20M** (34%) - 2x free!\n"
                "• **55M** (2%) - Over 2x!\n"
                "• **100M** (1%) - 2x jackpot!\n"
                "• **Stock Pet** (0.5%) - Very rare!\n"
                "• **300M** (0.5%) - MEGA JACKPOT!"
            ),
            inline=True
        )
        embed0.add_field(
            name="🎫 Spin Types",
            value=(
                "**Free Spins**: Daily refresh, non-stacking\n"
                "**Purchased Spins**: Stack unlimited, **HIGHER REWARDS!**"
            ),
            inline=False
        )
        embed0.add_field(
            name="✨ Features",
            value=(
                "• Beautiful animated spinning wheel\n"
                "• Two separate prize pools (free vs paid)\n"
                "• Buy multiple spins at once\n"
                "• Track statistics with `!wheelstats`\n"
                "• Owner can gift spins with `!addspin`"
            ),
            inline=False
        )
        embed0.set_footer(text="Page 1/12 • Use the buttons below to see other games")
        pages.append(embed0)
        
        # Page 2: Coinflip
        embed1 = discord.Embed(
            title="🪙 Coinflip",
            description="**Simple heads or tails - Classic coinflip betting!**",
            color=discord.Color.gold()
        )
        embed1.add_field(
            name="📋 Command",
            value="`!cf <amount> <heads/tails>`",
            inline=False
        )
        embed1.add_field(
            name="💡 Example",
            value="`!cf 200m heads`",
            inline=False
        )
        embed1.add_field(
            name="🎮 How to Play",
            value="1. Bet an amount and choose heads or tails\n2. Click **Start CF** to flip the coin\n3. Win if the coin lands on your choice!\n4. Click **Flip Again** to replay with same bet and choice",
            inline=False
        )
        embed1.add_field(
            name="💰 Payout",
            value="**Win**: 1.95x your bet (5% house edge)",
            inline=True
        )
        embed1.add_field(
            name="🎯 Win Chance",
            value="**50%** - Fair odds!",
            inline=True
        )
        embed1.add_field(
            name="✨ Features",
            value="• **Start CF** button to begin\n• **Flip Again** button to replay with same side\n• Simple, fast gameplay\n• Fair 50/50 odds",
            inline=False
        )
        embed1.add_field(
            name="⚠️ Note",
            value="Using the flip again button will use the same side of the coin you originally picked!",
            inline=False
        )
        embed1.set_footer(text="Page 2/12 • Use the buttons below to see other games")
        pages.append(embed1)
        
        # Page 3: FlipChase
        embed2 = discord.Embed(
            title="🎲 Flip & Chase",
            description="**Progressive double-or-nothing game - Chase for bigger wins or bank anytime!**",
            color=discord.Color.gold()
        )
        embed2.add_field(
            name="📋 Command",
            value="`!flipchase <amount>`",
            inline=False
        )
        embed2.add_field(
            name="💡 Example",
            value="`!flipchase 10m`",
            inline=False
        )
        embed2.add_field(
            name="🎮 How to Play",
            value="1. Bet an amount to start\n2. Win the first flip to start chasing\n3. **Chase**: Double your winnings (risk losing all)\n4. **Bank**: Keep your current winnings safe\n5. Lose any flip = lose everything!",
            inline=False
        )
        embed2.add_field(
            name="💰 Multipliers",
            value="**Round 1**: 2x\n**Round 2**: 4x\n**Round 3**: 8x\n**Round 4**: 16x\n**And so on...**",
            inline=True
        )
        embed2.add_field(
            name="🎯 Strategy",
            value="Balance risk vs reward!\nBank early for safe profit\nor chase for massive wins!",
            inline=True
        )
        embed2.add_field(
            name="⚠️ Warning",
            value="Losing ANY round means you lose ALL winnings! Bank wisely.",
            inline=False
        )
        embed2.set_footer(text="Page 3/12 • Use the buttons below to see other games")
        pages.append(embed2)
        
        # Page 4: Slots
        embed2 = discord.Embed(
            title="🎰 Slots",
            description="**3x3 slot machine with multiple winning patterns**",
            color=discord.Color.purple()
        )
        embed2.add_field(
            name="📋 Command",
            value="`!slots <amount>`",
            inline=False
        )
        embed2.add_field(
            name="💡 Example",
            value="`!slots 5m`",
            inline=False
        )
        embed2.add_field(
            name="🎮 How to Play",
            value="Spin a 3x3 slot machine! Match 3 symbols in a row, column, or diagonal to win.",
            inline=False
        )
        embed2.add_field(
            name="💎 Multipliers",
            value=(
                "• 7️⃣ **Jackpot** = 5.0x\n"
                "• 💎 **Diamond** = 3.0x\n"
                "• ⭐ **Star** = 2.5x\n"
                "• 🍇 **Grape** = 2.0x\n"
                "• 🍊 **Orange** = 1.8x\n"
                "• 🍋 **Lemon** = 1.5x\n"
                "• 🍒 **Cherry** = 1.2x"
            ),
            inline=False
        )
        embed2.add_field(
            name="✨ Features",
            value="Click 🔄 **Spin Again** to replay with same bet!",
            inline=False
        )
        embed2.set_footer(text="Page 4/12 • Use the buttons below to see other games")
        pages.append(embed2)
        
        # Page 5: Lucky Number
        embed3 = discord.Embed(
            title="🎲 Lucky Number",
            description="**Risk-based number guessing with massive multipliers**",
            color=discord.Color.blue()
        )
        embed3.add_field(
            name="📋 Commands",
            value=(
                "1. `!luckynumber <amount> <max_number>` - Start game\n"
                "2. `!pick <number>` - Make your guess"
            ),
            inline=False
        )
        embed3.add_field(
            name="💡 Example",
            value="`!luckynumber 1m 100` then `!pick 42`",
            inline=False
        )
        embed3.add_field(
            name="🎮 How to Play",
            value="Choose a number range (1-5000), then guess the lucky number!",
            inline=False
        )
        embed3.add_field(
            name="🎯 Risk Levels & Multipliers",
            value=(
                "• **1-10:** Low risk → **8x**\n"
                "• **1-50:** Medium risk → **40x**\n"
                "• **1-100:** High risk → **80x**\n"
                "• **1-500:** Very high risk → **400x**\n"
                "• **1-1000:** Extreme risk → **800x**\n"
                "• **1-2500:** Ultra risk → **2000x**\n"
                "• **1-5000:** Maximum risk → **4000x**"
            ),
            inline=False
        )
        embed3.add_field(
            name="⚠️ Note",
            value="Higher ranges = bigger multipliers but lower win chance!",
            inline=False
        )
        embed3.set_footer(text="Page 5/12 • Use the buttons below to see other games")
        pages.append(embed3)
        
        # Page 6: Crash
        embed4 = discord.Embed(
            title="🚀 Crash",
            description="**Real-time multiplier game with cash-out mechanic**",
            color=discord.Color.green()
        )
        embed4.add_field(
            name="📋 Command",
            value="`!crash <amount>`",
            inline=False
        )
        embed4.add_field(
            name="💡 Example",
            value="`!crash 10m`",
            inline=False
        )
        embed4.add_field(
            name="🎮 How to Play",
            value="A multiplier starts at 1.0x and climbs higher. Cash out before it crashes to win!",
            inline=False
        )
        embed4.add_field(
            name="📊 Crash Distribution",
            value=(
                "• **40%:** 1.2x-1.8x (most common)\n"
                "• **25%:** 1.8x-2.5x (common)\n"
                "• **17%:** 2.5x-4.0x (uncommon)\n"
                "• **10%:** 4.0x-8.0x (rare)\n"
                "• **8%:** 8.0x-30.0x (very rare jackpot!)"
            ),
            inline=False
        )
        embed4.add_field(
            name="💰 Winnings",
            value="Bet amount × multiplier when you cash out (minimum 1.79x)",
            inline=False
        )
        embed4.add_field(
            name="✨ Features",
            value=(
                "• Multiplier starts at **1.0x**\n"
                "• Minimum cashout: **1.79x** (game is very hard!)\n"
                "• Click 💵 **Cash Out** button to secure winnings!\n"
                "• Balanced distribution prevents exploitation"
            ),
            inline=False
        )
        embed4.add_field(
            name="⚠️ Risk",
            value="If you don't cash out before the crash, you lose your entire bet",
            inline=False
        )
        embed4.set_footer(text="Page 6/12 • Use the buttons below to see other games")
        pages.append(embed4)
        
        # Page 7: Blackjack
        embed5 = discord.Embed(
            title="🎴 Blackjack",
            description="**Classic casino card game - Beat the dealer without going over 21!**",
            color=discord.Color.dark_red()
        )
        embed5.add_field(
            name="📋 Command",
            value="`!blackjack <amount>`",
            inline=False
        )
        embed5.add_field(
            name="💡 Example",
            value="`!blackjack 15m`",
            inline=False
        )
        embed5.add_field(
            name="🎮 How to Play",
            value="Try to get as close to 21 as possible without going over! Beat the dealer's hand to win.",
            inline=False
        )
        embed5.add_field(
            name="🃏 Card Values",
            value=(
                "• **Number cards:** Face value (2-10)\n"
                "• **Face cards** (J, Q, K): Worth 10\n"
                "• **Aces:** Worth 11 or 1 (automatically adjusted)"
            ),
            inline=False
        )
        embed5.add_field(
            name="🎯 Actions",
            value=(
                "• **Hit:** Draw another card\n"
                "• **Stand:** End your turn and let dealer play\n"
                "• **Double Down:** Double your bet and draw one final card"
            ),
            inline=False
        )
        embed5.add_field(
            name="💰 Payouts",
            value=(
                "• **Win:** 2x your bet\n"
                "• **Blackjack** (21 with 2 cards): 2.5x your bet\n"
                "• **Push** (tie): Get your bet back"
            ),
            inline=False
        )
        embed5.add_field(
            name="📜 Dealer Rules",
            value="Dealer must hit on 16 or less, stand on 17 or more",
            inline=False
        )
        embed5.add_field(
            name="✨ Features",
            value="Professional embeds, interactive buttons, real-time gameplay!",
            inline=False
        )
        embed5.set_footer(text="Page 7/12 • Use the buttons below to see other games")
        pages.append(embed5)
        
        # Page 8: Risky Lumberjack (was Page 7)
        embed6 = discord.Embed(
            title="⚔️ Gladiator Fights",
            description="**Epic PvP battles with 8 unique gladiators**",
            color=discord.Color.orange()
        )
        embed6.add_field(
            name="📋 Commands",
            value=(
                "1. `!fight @user <amount>` - Challenge a player\n"
                "2. `!pickgladiator <gladiator>` - Select your fighter"
            ),
            inline=False
        )
        embed6.add_field(
            name="💡 Example",
            value="`!fight @John 50m` → `!pickgladiator Maximus`",
            inline=False
        )
        embed6.add_field(
            name="🎮 How to Play",
            value="Challenge another player to a 1v1 gladiator duel! Both bet the same amount, winner takes all!",
            inline=False
        )
        embed6.add_field(
            name="🏛️ Gladiators",
            value="8 unique fighters with different stats (HP, Attack, Defense, Dodge)",
            inline=False
        )
        embed6.add_field(
            name="⚔️ Combat Mechanics",
            value=(
                "• 💨 **Dodge:** Avoid damage + regenerate 5-15 HP\n"
                "• 🛡️ **Block:** Reduce damage by 66% + regenerate 3-10 HP\n"
                "• ⚔️ **Attack:** Deal damage based on your gladiator's power"
            ),
            inline=False
        )
        embed6.add_field(
            name="✨ Features",
            value="Real-time animated combat, health bars, 🔄 rematch button",
            inline=False
        )
        embed6.add_field(
            name="🏆 Winner Takes All",
            value="Winner gets both bets (2x your wager!)",
            inline=False
        )
        embed6.set_footer(text="Page 8/12 • Use the buttons below to see other games")
        pages.append(embed6)
        
        # Page 7: Risky Lumberjack
        embed7 = discord.Embed(
            title="🪓 Risky Lumberjack",
            description="**Turn-based tree cutting game - don't make it fall!**",
            color=discord.Color.dark_green()
        )
        embed7.add_field(
            name="📋 Commands",
            value=(
                "1. `!choptree @user <amount>` - Challenge a player\n"
                "2. `!chop` - Take your turn cutting"
            ),
            inline=False
        )
        embed7.add_field(
            name="💡 Example",
            value="`!choptree @Sarah 25m` → `!chop`",
            inline=False
        )
        embed7.add_field(
            name="🎮 How to Play",
            value="Take turns chopping a tree. Each chop removes 1-3 HP. The player who makes the tree fall (HP reaches 0) loses!",
            inline=False
        )
        embed7.add_field(
            name="🌳 Tree Health",
            value="Random starting health between 15-25 HP",
            inline=False
        )
        embed7.add_field(
            name="🪓 Chop Damage",
            value=(
                "• Light Chop: -1 HP\n"
                "• Medium Chop: -2 HP\n"
                "• Heavy Chop: -3 HP"
            ),
            inline=False
        )
        embed7.add_field(
            name="⚠️ Strategy",
            value="Plan your chops carefully! You don't want to be the one to fell the tree!",
            inline=False
        )
        embed7.add_field(
            name="🏆 Winner Takes All",
            value="Winner gets both bets (2x your wager!)",
            inline=False
        )
        embed7.set_footer(text="Page 8/12 • Use the buttons below to see other games")
        pages.append(embed7)
        
        # Page 9: Limbo (was Page 10, removed Word Chain)
        embed9 = discord.Embed(
            title="🎰 Limbo",
            description="**Will the number be above or below 50? Higher bets = higher multipliers!**",
            color=discord.Color.purple()
        )
        embed9.add_field(
            name="📋 Command",
            value="`!limbo <amount>`",
            inline=False
        )
        embed9.add_field(
            name="💡 Example",
            value="`!limbo 25m`",
            inline=False
        )
        embed9.add_field(
            name="🎮 How to Play",
            value="1. Bet an amount to start\n2. A random number between 1-100 is generated\n3. Choose **Above 50** or **Below 50**\n4. If you're correct, you win!\n5. Wrong guess = lose your bet",
            inline=False
        )
        embed9.add_field(
            name="💰 Multipliers (Bet-Based)",
            value=(
                "• **Under 10M:** 1.82x\n"
                "• **10M+:** 1.84x\n"
                "• **25M+:** 1.86x\n"
                "• **50M+:** 1.88x\n"
                "• **100M+:** 1.90x"
            ),
            inline=False
        )
        embed9.add_field(
            name="🎯 Strategy",
            value="Higher bets give better multipliers! But remember - house always has a slight edge.",
            inline=False
        )
        embed9.add_field(
            name="✨ Features",
            value="• Simple and fast gameplay\n• Interactive button interface\n• Bet-scaled multipliers\n• Casino-style odds",
            inline=False
        )
        embed9.add_field(
            name="⚠️ Note",
            value="50 is neither above nor below - rolling exactly 50 counts as a loss for both choices!",
            inline=False
        )
        embed9.set_footer(text="Page 9/12 • Use the buttons below to see other games")
        pages.append(embed9)
        
        # Page 10: Rock Paper Scissors
        embed10 = discord.Embed(
            title="✂️ Rock Paper Scissors",
            description="**Classic RPS with interactive buttons!**",
            color=discord.Color.blue()
        )
        embed10.add_field(
            name="📋 Command",
            value="`!rps <amount>`",
            inline=False
        )
        embed10.add_field(
            name="💡 Example",
            value="`!rps 10m`",
            inline=False
        )
        embed10.add_field(
            name="🎮 How to Play",
            value="1. Bet an amount\n2. Click one of three buttons: 🪨 Rock, 📄 Paper, or ✂️ Scissors\n3. House choice is pre-generated (provably fair)\n4. Winner determined instantly!",
            inline=False
        )
        embed10.add_field(
            name="🎯 Rules",
            value=(
                "• 🪨 Rock beats ✂️ Scissors\n"
                "• ✂️ Scissors beats 📄 Paper\n"
                "• 📄 Paper beats 🪨 Rock"
            ),
            inline=False
        )
        embed10.add_field(
            name="💰 Payouts",
            value=(
                "• **Win:** 2x your bet\n"
                "• **Tie:** Get your bet back\n"
                "• **Lose:** Lose your bet"
            ),
            inline=False
        )
        embed10.add_field(
            name="✨ Features",
            value="• Interactive Discord buttons\n• 60-second selection timer\n• Provably fair house choice\n• Instant results",
            inline=False
        )
        embed10.set_footer(text="Page 10/12 • Use the buttons below to see other games")
        pages.append(embed10)
        
        # Page 11: Baccarat
        embed11 = discord.Embed(
            title="🎴 Baccarat",
            description="**Classic casino card game with chip buttons!**",
            color=discord.Color.gold()
        )
        embed11.add_field(
            name="📋 Command",
            value="`!baccarat`",
            inline=False
        )
        embed11.add_field(
            name="💡 Example",
            value="`!baccarat` → Add chips → Choose side → Deal",
            inline=False
        )
        embed11.add_field(
            name="🎮 How to Play",
            value=(
                "1. Click chip buttons to build your bet (500K, 1M, 5M, 20M, 50M)\n"
                "2. Choose where to bet: Player, Banker, or Tie\n"
                "3. Click **Deal** to play the hand\n"
                "4. Closest to 9 wins!"
            ),
            inline=False
        )
        embed11.add_field(
            name="🃏 Card Values",
            value=(
                "• **Ace:** 1 point\n"
                "• **2-9:** Face value\n"
                "• **10, J, Q, K:** 0 points\n"
                "• Total is last digit (e.g., 15 = 5)"
            ),
            inline=False
        )
        embed11.add_field(
            name="💰 Payouts",
            value=(
                "• **Player:** 1:1 (2x your bet)\n"
                "• **Banker:** 0.95:1 (1.95x - 5% commission)\n"
                "• **Tie:** 8:1 (9x your bet)\n"
                "• Tie also returns Player/Banker bets"
            ),
            inline=False
        )
        embed11.add_field(
            name="✨ Features",
            value=(
                "• Interactive chip buttons\n"
                "• Professional dealer's table layout\n"
                "• Provably fair card dealing\n"
                "• Full baccarat rules (third card draws)"
            ),
            inline=False
        )
        embed11.add_field(
            name="🎯 Strategy",
            value="Banker has slightly better odds (lowest house edge), but pays 5% commission!",
            inline=False
        )
        embed11.set_footer(text="Page 11/12 • Use the buttons below to see other games")
        pages.append(embed11)
        
        # Page 12: General Rules
        embed12 = discord.Embed(
            title="📋 General Rules",
            description="**Important information about the gambling system**",
            color=discord.Color.red()
        )
        embed12.add_field(
            name="💵 Deposit Requirement",
            value="Minimum **10M** deposit required",
            inline=False
        )
        embed12.add_field(
            name="🎲 Gambling Requirement",
            value="Must gamble **30%** of your balance before withdrawing",
            inline=False
        )
        embed12.add_field(
            name="⚡ Balance Updates",
            value="All wins/losses update your balance instantly",
            inline=False
        )
        embed12.add_field(
            name="🛡️ Fraud Detection",
            value="Rapid betting and high-value bets are monitored",
            inline=False
        )
        embed12.add_field(
            name="💸 Withdrawals",
            value="Use `!withdraw` when you meet the gambling requirement",
            inline=False
        )
        embed12.add_field(
            name="ℹ️ More Commands",
            value="Use `!assist` to see all available commands",
            inline=False
        )
        embed12.add_field(
            name="🔐 Provably Fair",
            value="All gambling games use cryptographically secure RNG. Use `!fairinfo` to learn more!",
            inline=False
        )
        embed12.set_footer(text="Page 12/12 • Use the buttons below to see other games")
        pages.append(embed12)
        
        return pages
    
    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your games menu!", ephemeral=True)
            return
        
        self.current_page = (self.current_page - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your games menu!", ephemeral=True)
            return
        
        self.current_page = (self.current_page + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)


@bot.command(name="games")
async def games(ctx):
    """
    Display information about all gambling games with pagination.
    
    Usage: !games
    """
    try:
        view = GamesView(ctx.author.id)
        await ctx.send(embed=view.pages[0], view=view)
    except Exception as e:
        await ctx.send(f"❌ Error displaying games: {str(e)}")


# -----------------------------
# DEPOSIT STATISTICS TASK
# -----------------------------
@tasks.loop(minutes=15)
async def post_deposit_stats():
    """Post deposit statistics every 15 minutes."""
    try:
        channel = bot.get_channel(DEPOSIT_STATS_CHANNEL)
        if not channel:
            print(f"⚠️ Deposit stats channel {DEPOSIT_STATS_CHANNEL} not found")
            return
        
        # Query total deposits from all users
        c.execute("SELECT SUM(balance) FROM users")
        result = c.fetchone()
        total_deposits = result[0] if result[0] else 0
        
        # Count number of users with deposits
        c.execute("SELECT COUNT(*) FROM users WHERE balance > 0")
        users_with_balance = c.fetchone()[0]
        
        # Get total number of users
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        
        # Create embed
        embed = discord.Embed(
            title="💰 Total Deposit Statistics",
            description="Current deposit status across all players",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📊 Total Deposits",
            value=f"{format_money(total_deposits)}",
            inline=False
        )
        
        embed.add_field(
            name="👥 Active Players",
            value=f"{users_with_balance:,} players with balance",
            inline=True
        )
        
        embed.add_field(
            name="📈 Total Users",
            value=f"{total_users:,} registered users",
            inline=True
        )
        
        if users_with_balance > 0:
            avg_balance = total_deposits // users_with_balance
            embed.add_field(
                name="💵 Average Balance",
                value=f"{format_money(avg_balance)}",
                inline=False
            )
        
        embed.set_footer(text="Updates every 15 minutes")
        
        await channel.send(embed=embed)
        print(f"✅ Posted deposit statistics: {format_money(total_deposits)}")
        
    except Exception as e:
        print(f"❌ Error posting deposit statistics: {str(e)}")

@post_deposit_stats.before_loop
async def before_deposit_stats():
    """Wait until bot is ready before starting the task."""
    await bot.wait_until_ready()
    print("✅ Deposit statistics task started")

# -----------------------------
# STOCK MARKET AUTOMATED UPDATES
# -----------------------------
@tasks.loop(hours=1)
async def update_stock_prices():
    """Update stock prices every hour with random market fluctuations."""
    try:
        print("🔄 Updating stock market prices...")
        
        # Get all stocks
        stocks = get_all_stocks()
        
        for stock in stocks:
            stock_id, ticker, name, category, base_price, current_price, total_shares, available_shares = stock
            
            # Calculate new price with random fluctuation
            new_price = calculate_random_price_change(base_price, current_price, category)
            
            # Update price in database
            update_stock_price(stock_id, new_price)
            
            # Calculate change for logging
            change_pct = ((new_price - current_price) / current_price) * 100
            print(f"  {ticker}: {current_price:.2f} → {new_price:.2f} ({change_pct:+.2f}%)")
        
        print(f"✅ Updated prices for {len(stocks)} stocks")
        
    except Exception as e:
        print(f"❌ Error updating stock prices: {e}")

@update_stock_prices.before_loop
async def before_stock_price_updates():
    """Wait until bot is ready before starting the task."""
    await bot.wait_until_ready()
    print("✅ Stock market price update task started (runs every hour)")


# -----------------------------
# STOCK/INVENTORY SYSTEM
# -----------------------------
# Global variable to track stock message
stock_message_id = None
# Global dictionary to track each user's current page
user_stock_pages = {}
# Global counter for buy tickets
buy_ticket_counter = 1


class BuyerConfirmationView(discord.ui.View):
    """View for buyer to confirm purchase."""
    
    def __init__(self, item_id, pet_name, price, buyer_id, ticket_channel):
        super().__init__(timeout=300)  # 5 minute timeout
        self.item_id = item_id
        self.pet_name = pet_name
        self.price = price
        self.buyer_id = buyer_id
        self.ticket_channel = ticket_channel
    
    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Buyer confirms the purchase."""
        if interaction.user.id != self.buyer_id:
            await interaction.response.send_message("❌ Only the buyer can confirm this purchase.", ephemeral=True)
            return
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        
        # Send waiting message to buyer
        await interaction.response.send_message(
            "✅ **Purchase confirmed!**\n\nWaiting for owner approval...",
            ephemeral=False
        )
        
        # Create owner confirmation view
        owner_view = OwnerConfirmationView(self.item_id, self.pet_name, self.price, self.buyer_id, self.ticket_channel)
        
        # Send owner confirmation message
        owner_embed = discord.Embed(
            title="🔔 Purchase Approval Needed",
            description=f"**{interaction.user.mention}** wants to purchase:\n\n"
                       f"🐾 **Pet:** {self.pet_name}\n"
                       f"💰 **Price:** {format_money(self.price)}\n"
                       f"🏪 **Item ID:** #{self.item_id}",
            color=discord.Color.gold()
        )
        owner_embed.set_footer(text="Click Confirm to approve this purchase")
        
        await self.ticket_channel.send(
            f"<@{'> <@'.join(str(owner_id) for owner_id in OWNER_IDS)}>",
            embed=owner_embed,
            view=owner_view
        )
    
    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Buyer cancels the purchase."""
        if interaction.user.id != self.buyer_id:
            await interaction.response.send_message("❌ Only the buyer can cancel this purchase.", ephemeral=True)
            return
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        
        await interaction.response.send_message(
            "❌ **Purchase cancelled.**\n\nYou can close this ticket or try purchasing another pet.",
            ephemeral=False
        )


class OwnerConfirmationView(discord.ui.View):
    """View for owner to confirm and complete purchase."""
    
    def __init__(self, item_id, pet_name, price, buyer_id, ticket_channel):
        super().__init__(timeout=None)  # No timeout for owner confirmation
        self.item_id = item_id
        self.pet_name = pet_name
        self.price = price
        self.buyer_id = buyer_id
        self.ticket_channel = ticket_channel
    
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, custom_id=f"owner_confirm_buy")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Owner confirms and completes the purchase."""
        if interaction.user.id not in OWNER_IDS:
            await interaction.response.send_message("❌ Only bot owners can confirm purchases.", ephemeral=True)
            return
        
        try:
            # Check buyer's balance
            c.execute("SELECT balance FROM users WHERE user_id = ?", (self.buyer_id,))
            result = c.fetchone()
            
            if not result:
                await interaction.response.send_message(
                    f"❌ **Error:** Buyer <@{self.buyer_id}> not found in database.",
                    ephemeral=False
                )
                return
            
            buyer_balance = result[0]
            
            if buyer_balance < self.price:
                await interaction.response.send_message(
                    f"❌ **Insufficient funds!**\n\n"
                    f"<@{self.buyer_id}> has {format_money(buyer_balance)} but needs {format_money(self.price)}.",
                    ephemeral=False
                )
                return
            
            # Subtract amount from buyer's balance
            new_balance = buyer_balance - self.price
            c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, self.buyer_id))
            
            # Remove stock item from database
            c.execute("DELETE FROM stock_items WHERE id = ?", (self.item_id,))
            conn.commit()
            
            # Disable button
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
            
            # Send success message
            success_embed = discord.Embed(
                title="✅ Purchase Complete!",
                description=(
                    f"**Purchase successfully completed!**\n\n"
                    f"🐾 **Pet:** {self.pet_name}\n"
                    f"💰 **Price:** {format_money(self.price)}\n"
                    f"👤 **Buyer:** <@{self.buyer_id}>\n"
                    f"💵 **New Balance:** {format_money(new_balance)}\n\n"
                    f"**The pet has been removed from stock.**"
                ),
                color=discord.Color.green()
            )
            success_embed.set_footer(text=f"Confirmed by {interaction.user.name}")
            
            await interaction.response.send_message(embed=success_embed, ephemeral=False)
            
            # Update stock display
            await update_stock_display()
            
            print(f"✅ Purchase completed: {self.pet_name} sold to {self.buyer_id} for {format_money(self.price)}")
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Error completing purchase:** {str(e)}",
                ephemeral=False
            )
            print(f"❌ Error in owner confirmation: {str(e)}")


class StockView(discord.ui.View):
    """View for paginated stock/inventory display with buy functionality."""
    
    def __init__(self, user_id=None, item_data=None):
        super().__init__(timeout=None)  # Persistent view, no timeout
        self.user_id = user_id
        self.current_page = 0
        self.pages = []
        self.item_data = item_data  # Store item data for Buy button
        
    async def update_pages(self):
        """Fetch and create all stock pages from database."""
        self.pages = []
        
        try:
            conn_temp = sqlite3.connect("bot.db")
            c_temp = conn_temp.cursor()
            
            # Fetch all stock items ordered by date added
            c_temp.execute("""
                SELECT id, pet_name, mutation, trait, price, stock_amount, 
                       account_stored, image_url, date_added
                FROM stock_items
                ORDER BY date_added DESC
            """)
            items = c_temp.fetchall()
            conn_temp.close()
            
            if not items:
                # No items - create empty page
                embed = discord.Embed(
                    title="🐾 Brainrot Pet Stock",
                    description="**No items in stock currently**\n\nCheck back later for available pets!",
                    color=discord.Color.blue()
                )
                embed.set_footer(text="Page 0/0 • Use < > to navigate")
                self.pages.append(embed)
                return
            
            # Create one page per item
            for idx, item in enumerate(items):
                item_id, pet_name, mutation, trait, price, stock_amount, account_stored, image_url, date_added = item
                
                embed = discord.Embed(
                    title=f"🐾 {pet_name}",
                    description=f"**Available Brainrot Pet**",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="🔮 Mutation",
                    value=mutation,
                    inline=True
                )
                embed.add_field(
                    name="✨ Trait",
                    value=trait,
                    inline=True
                )
                embed.add_field(
                    name="💰 Price",
                    value=format_money(price),
                    inline=True
                )
                embed.add_field(
                    name="📦 Stock",
                    value=f"{stock_amount} available",
                    inline=True
                )
                embed.add_field(
                    name="📅 Added",
                    value=date_added.split()[0],  # Just the date
                    inline=True
                )
                embed.add_field(
                    name="🏪 Item ID",
                    value=f"#{item_id}",
                    inline=True
                )
                
                # Add image if URL is provided
                if image_url:
                    embed.set_image(url=image_url)
                
                embed.set_footer(text=f"Page {idx + 1}/{len(items)} • Use < > to navigate | Click Buy to purchase")
                self.pages.append((embed, item))  # Store both embed and item data
                
        except Exception as e:
            # Error page
            embed = discord.Embed(
                title="❌ Error Loading Stock",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            self.pages.append((embed, None))
    
    @discord.ui.button(label="<", style=discord.ButtonStyle.primary, custom_id="stock_prev")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page - shows ephemeral response to user."""
        global user_stock_pages
        
        # Create a temporary view instance for this user
        temp_view = StockView(user_id=interaction.user.id)
        await temp_view.update_pages()
        
        if not temp_view.pages:
            await interaction.response.send_message("❌ No stock items available.", ephemeral=True)
            return
        
        # Get or initialize user's current page
        user_id = interaction.user.id
        if user_id not in user_stock_pages:
            user_stock_pages[user_id] = 0
        
        # Move to previous page
        user_stock_pages[user_id] = (user_stock_pages[user_id] - 1) % len(temp_view.pages)
        current_page = user_stock_pages[user_id]
        
        # Get embed and item data for current page
        embed, item_data = temp_view.pages[current_page]
        
        # Send ephemeral response with the user's personal page
        await interaction.response.send_message(
            embed=embed, 
            view=temp_view,
            ephemeral=True
        )
    
    @discord.ui.button(label=">", style=discord.ButtonStyle.primary, custom_id="stock_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page - shows ephemeral response to user."""
        global user_stock_pages
        
        # Create a temporary view instance for this user
        temp_view = StockView(user_id=interaction.user.id)
        await temp_view.update_pages()
        
        if not temp_view.pages:
            await interaction.response.send_message("❌ No stock items available.", ephemeral=True)
            return
        
        # Get or initialize user's current page
        user_id = interaction.user.id
        if user_id not in user_stock_pages:
            user_stock_pages[user_id] = 0
        
        # Move to next page
        user_stock_pages[user_id] = (user_stock_pages[user_id] + 1) % len(temp_view.pages)
        current_page = user_stock_pages[user_id]
        
        # Get embed and item data for current page
        embed, item_data = temp_view.pages[current_page]
        
        # Send ephemeral response with the user's personal page
        await interaction.response.send_message(
            embed=embed, 
            view=temp_view,
            ephemeral=True
        )
    
    @discord.ui.button(label="🛒 Buy", style=discord.ButtonStyle.green, custom_id="stock_buy")
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Initiate purchase process for the current stock item."""
        global buy_ticket_counter, user_stock_pages
        
        try:
            # Get user's current page
            user_id = interaction.user.id
            if user_id not in user_stock_pages:
                user_stock_pages[user_id] = 0
            
            current_page = user_stock_pages[user_id]
            
            # Fetch current stock items
            temp_view = StockView(user_id=user_id)
            await temp_view.update_pages()
            
            if not temp_view.pages or current_page >= len(temp_view.pages):
                await interaction.response.send_message("❌ Error: Invalid stock page.", ephemeral=True)
                return
            
            # Get item data for current page
            embed, item_data = temp_view.pages[current_page]
            
            if not item_data:
                await interaction.response.send_message("❌ No item data available for this page.", ephemeral=True)
                return
            
            item_id, pet_name, mutation, trait, price, stock_amount, account_stored, image_url, date_added = item_data
            
            # Check buyer's balance
            c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            
            if not result:
                await interaction.response.send_message(
                    "❌ **You don't have a gambling account!**\n\n"
                    "Please make a deposit first to start gambling and purchasing pets.",
                    ephemeral=True
                )
                return
            
            buyer_balance = result[0]
            
            if buyer_balance < price:
                await interaction.response.send_message(
                    f"❌ **Insufficient funds!**\n\n"
                    f"You have {format_money(buyer_balance)} but this pet costs {format_money(price)}.\n\n"
                    f"You need {format_money(price - buyer_balance)} more to purchase this pet.",
                    ephemeral=True
                )
                return
            
            # Create buy ticket channel
            guild = interaction.guild
            category = guild.get_channel(TICKET_CATEGORY_ID)
            
            if not category:
                await interaction.response.send_message("❌ Error: Ticket category not found.", ephemeral=True)
                return
            
            # Create channel name
            channel_name = f"buy-{interaction.user.name}-{buy_ticket_counter}"
            buy_ticket_counter += 1
            
            # Set permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            # Add owners to permissions
            for owner_id in OWNER_IDS:
                owner = guild.get_member(owner_id)
                if owner:
                    overwrites[owner] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            # Create ticket channel
            ticket_channel = await category.create_text_channel(
                name=channel_name,
                overwrites=overwrites
            )
            
            # Ping owner roles
            role_mentions = ' '.join(f"<@&{role_id}>" for role_id in PING_ROLES)
            await ticket_channel.send(f"📢 {role_mentions}")
            
            # Send combined welcome and confirmation embed
            combined_embed = discord.Embed(
                title="🛒 Purchase Ticket",
                description=(
                    f"Welcome {interaction.user.mention} to **Eli's MM & Gambling!**\n\n"
                    f"An owner will be here to assist your purchase very shortly.\n\n"
                    f"**Pet Details:**\n"
                    f"🐾 **Name:** {pet_name}\n"
                    f"🔮 **Mutation:** {mutation}\n"
                    f"✨ **Trait:** {trait}\n"
                    f"💰 **Price:** {format_money(price)}\n"
                    f"💵 **Your Balance:** {format_money(buyer_balance)}\n\n"
                    f"**Please confirm you want to purchase this pet by clicking Yes below.**"
                ),
                color=discord.Color.blue()
            )
            
            # Send buyer confirmation view
            buyer_view = BuyerConfirmationView(item_id, pet_name, price, user_id, ticket_channel)
            
            await ticket_channel.send(f"{interaction.user.mention}", embed=combined_embed, view=buyer_view)
            
            # Send response to user
            await interaction.response.send_message(
                f"✅ **Purchase ticket created!**\n\n"
                f"Please head to {ticket_channel.mention} to complete your purchase.",
                ephemeral=True
            )
            
            print(f"✅ Buy ticket created: {channel_name} for {pet_name}")
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Error creating purchase ticket:** {str(e)}",
                ephemeral=True
            )
            print(f"❌ Error in buy button: {str(e)}")


@bot.command(name="addstock")
async def addstock(ctx, *, args: str = None):
    """
    Add a new item to the brainrot pet stock. Owner only.
    
    Usage: !addstock <Pet Name>, <Mutation>, <Trait>, <Price>, <Stock>, <Account>
    Example: !addstock Los Combinasionas 127.5m, Candy, Pumpkin, 300M, 1, gamb1lebank1
    
    Note: You can attach an image to the command message to include it in the stock listing.
    Fields are separated by commas. Spaces are allowed within each field.
    """
    # Check if user is owner
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("❌ Only bot owners can use this command.")
        return
    
    # Check if args provided
    if not args:
        await ctx.send(
            "❌ **Missing parameters!**\n\n"
            "**Usage:** `!addstock <Pet Name>, <Mutation>, <Trait>, <Price>, <Stock>, <Account>`\n\n"
            "**Example:** `!addstock Los Combinasionas 127.5m, Candy, Pumpkin, 300M, 1, gamb1lebank1`\n\n"
            "**Note:** Fields are separated by commas. Spaces are allowed within fields.\n"
            "You can attach an image to include it in the listing!"
        )
        return
    
    # Split by comma - this allows spaces within each field
    parts = [p.strip() for p in args.split(',')]
    
    # Validate we have exactly 6 parts
    if len(parts) < 6:
        await ctx.send(
            "❌ **Invalid format!**\n\n"
            "**Usage:** `!addstock <Pet Name>, <Mutation>, <Trait>, <Price>, <Stock>, <Account>`\n\n"
            "**Example:** `!addstock Los Combinasionas 127.5m, Candy, Pumpkin, 300M, 1, gamb1lebank1`\n\n"
            f"**You provided {len(parts)} field(s), but 6 are required.**\n\n"
            "**Note:** Fields are separated by commas. Spaces are allowed within fields.\n"
            "You can attach an image to include it in the listing!"
        )
        return
    
    # Extract the 6 required fields
    pet_name, mutation, trait, price, stock_amount, account_stored = parts[:6]
    
    # Validate all fields are non-empty after stripping
    if not all([pet_name, mutation, trait, price, stock_amount, account_stored]):
        await ctx.send(
            "❌ **Empty field detected!**\n\n"
            "All fields must contain values.\n\n"
            "**Usage:** `!addstock <Pet Name>, <Mutation>, <Trait>, <Price>, <Stock>, <Account>`\n\n"
            "**Example:** `!addstock Los Combinasionas 127.5m, Candy, Pumpkin, 300M, 1, gamb1lebank1`"
        )
        return
    
    try:
        # Parse price
        price_value = parse_money(price)
        if price_value <= 0:
            await ctx.send(f"❌ Invalid price format! Use formats like: 50m, 100m, 1b")
            return
        
        # Parse stock amount
        try:
            stock_value = int(stock_amount.strip())
            if stock_value <= 0:
                raise ValueError()
        except:
            await ctx.send(f"❌ Invalid stock amount! Must be a positive integer.")
            return
        
        # Check for attached image
        image_url = None
        if ctx.message.attachments:
            # Get the first attachment
            attachment = ctx.message.attachments[0]
            # Verify it's an image
            if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                image_url = attachment.url
        
        # Add to database
        conn_temp = sqlite3.connect("bot.db")
        c_temp = conn_temp.cursor()
        
        c_temp.execute("""
            INSERT INTO stock_items (pet_name, mutation, trait, price, stock_amount, 
                                     account_stored, image_url, date_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (pet_name.strip(), mutation.strip(), trait.strip(), price_value, stock_value, 
              account_stored.strip(), image_url, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
        
        item_id = c_temp.lastrowid
        conn_temp.commit()
        conn_temp.close()
        
        # Send confirmation in current channel
        confirm_embed = discord.Embed(
            title="✅ Stock Item Added!",
            description=f"**{pet_name}** has been added to the stock!",
            color=discord.Color.green()
        )
        confirm_embed.add_field(name="🔮 Mutation", value=mutation, inline=True)
        confirm_embed.add_field(name="✨ Trait", value=trait, inline=True)
        confirm_embed.add_field(name="💰 Price", value=format_money(price_value), inline=True)
        confirm_embed.add_field(name="📦 Stock", value=str(stock_value), inline=True)
        confirm_embed.add_field(name="🏪 Item ID", value=f"#{item_id}", inline=True)
        if image_url:
            confirm_embed.add_field(name="📷 Image", value="✅ Included", inline=True)
        
        await ctx.send(embed=confirm_embed)
        
        # Update stock channel
        await update_stock_display()
        
        print(f"✅ Stock item #{item_id} added: {pet_name}")
        
    except Exception as e:
        await ctx.send(f"❌ Error adding stock item: {str(e)}")
        print(f"❌ Error in addstock command: {str(e)}")


@bot.command(name="resetstock")
async def resetstock(ctx):
    """Delete all stock items (Owner only)"""
    if not is_owner(ctx.author):
        await ctx.send("❌ You do not have permission to use this command.")
        return
    
    try:
        # Get count of current stock items
        c.execute("SELECT COUNT(*) FROM stock_items")
        count = c.fetchone()[0]
        
        if count == 0:
            await ctx.send("ℹ️ There are no stock items to delete.")
            return
        
        # Delete all stock items
        c.execute("DELETE FROM stock_items")
        conn.commit()
        
        # Update stock display
        await update_stock_display()
        
        embed = discord.Embed(
            title="🗑️ Stock Reset Complete",
            description=f"✅ Successfully deleted **{count}** stock item(s).\n\nThe stock inventory has been completely cleared.",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)
        
        print(f"✅ Stock reset: {count} items deleted by {ctx.author}")
        
    except Exception as e:
        await ctx.send(f"❌ Error resetting stock: {str(e)}")
        print(f"❌ Error in resetstock command: {str(e)}")


@bot.command(name="ownercom")
async def ownercom(ctx):
    """Display all owner commands (Owner only)"""
    if not is_owner(ctx.author):
        await ctx.send("❌ You do not have permission to use this command.")
        return
    
    try:
        embed = discord.Embed(
            title="🔐 Owner Commands",
            description="Complete list of bot owner commands",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="📋 Ticket Management",
            value=(
                "**!ticketpanel** - Send deposit ticket panel\n"
                "**!withdrawalpanel** - Send withdrawal ticket panel\n"
                "**!ticketclose [reason]** - Close a ticket with optional reason"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💰 Balance Management",
            value=(
                "**!deposit @user amount** - Add gambling amount to a user\n"
                "**!viewamount @user** - View a user's balance\n"
                "**!amountall [page]** - View all users balances\n"
                "**!wipeamount @user** - Wipe a user's balance"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📊 Statistics & Monitoring",
            value=(
                "**!gambledall** - View total gambling statistics across all players\n"
                "**!resetgamblingall** - Reset all gambling statistics (total_gambled & gambled)"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🏪 Stock/Inventory Management",
            value=(
                "**!addstock <Name>, <Mutation>, <Trait>, <Price>, <Stock>, <Account>** - Add pet to stock\n"
                "**!resetstock** - Delete all current stock items"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🐾 Pet Tracking",
            value=(
                "**!trackpet <pet_id>** - Look up a pet by ID\n"
                "**!petids** - List all pets in stock"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📌 Utility",
            value=(
                "**!stick [message]** - Create a sticky message at the bottom of the channel\n"
                "**!unstick** - Remove the sticky message from the current channel"
            ),
            inline=False
        )
        
        embed.set_footer(text="These commands are restricted to bot owners only")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error displaying owner commands: {str(e)}")
        print(f"❌ Error in ownercom command: {str(e)}")


async def update_stock_display():
    """Update or create the stock display message in the stock channel."""
    global stock_message_id
    
    try:
        channel = bot.get_channel(STOCK_CHANNEL)
        if not channel:
            print(f"⚠️ Stock channel {STOCK_CHANNEL} not found")
            return
        
        # Create view and update pages
        view = StockView()
        await view.update_pages()
        
        if not view.pages:
            print("⚠️ No stock pages to display")
            return
        
        # Extract just the embed from the first page (tuple of embed, item_data)
        first_embed = view.pages[0][0] if isinstance(view.pages[0], tuple) else view.pages[0]
        
        # Try to edit existing message or create new one
        if stock_message_id:
            try:
                message = await channel.fetch_message(stock_message_id)
                await message.edit(embed=first_embed, view=view)
                print(f"✅ Updated stock display message")
            except discord.NotFound:
                # Message was deleted, create new one
                message = await channel.send(embed=first_embed, view=view)
                stock_message_id = message.id
                print(f"✅ Created new stock display message (old one was deleted)")
            except Exception as e:
                print(f"❌ Error updating stock message: {str(e)}")
        else:
            # No message exists, create one
            message = await channel.send(embed=first_embed, view=view)
            stock_message_id = message.id
            print(f"✅ Created new stock display message")
            
    except Exception as e:
        print(f"❌ Error updating stock display: {str(e)}")


# -----------------------------
# BOT READY
# -----------------------------
@bot.event
async def on_ready():
    """Bot ready event handler."""
    print(f"✅ Logged in as {bot.user}")
    # Register persistent views
    bot.add_view(TicketPanelView())
    bot.add_view(WithdrawalPanelView())
    bot.add_view(StockView())  # Register persistent stock view
    print("✅ Persistent views registered")
    
    # Start deposit statistics task if not already running
    if not post_deposit_stats.is_running():
        post_deposit_stats.start()
        print("✅ Deposit statistics task started")
    
    # Start stock market price update task if not already running
    if not update_stock_prices.is_running():
        update_stock_prices.start()
        print("✅ Stock market price update task started")
    
    # Initialize stock display if not exists
    try:
        await update_stock_display()
    except Exception as e:
        print(f"⚠️ Error initializing stock display: {str(e)}")

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for commands."""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument: {str(error)}")
    elif isinstance(error, commands.CommandNotFound):
        # Silently ignore command not found errors
        pass
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ Bot is missing required permissions.")
    else:
        # Log unexpected errors
        print(f"Error in command {ctx.command}: {error}")
        await ctx.send(f"❌ An unexpected error occurred: {str(error)}")

@bot.event
async def on_message(message):
    """Handle messages and manage stick messages."""
    # Process commands first
    await bot.process_commands(message)
    
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Check if this channel has a stick message
    channel_id = message.channel.id
    if channel_id in stick_messages:
        stick_data = stick_messages[channel_id]
        
        # Check cooldown (5 seconds)
        time_since_last_update = datetime.now() - stick_data["last_update"]
        if time_since_last_update.total_seconds() < 5:
            # Still in cooldown, don't repost
            return
        
        try:
            # Delete the old stick message
            old_stick = await message.channel.fetch_message(stick_data["message_id"])
            await old_stick.delete()
        except:
            # Old message already deleted or not found
            pass
        
        try:
            # Repost the stick message at the bottom
            new_stick = await message.channel.send(f"📌 {stick_data['content']}")
            
            # Update tracking
            stick_messages[channel_id] = {
                "message_id": new_stick.id,
                "content": stick_data["content"],
                "last_update": datetime.now()
            }
        except Exception as e:
            print(f"Error reposting stick message: {e}")

# -----------------------------
# SPIN WHEEL SYSTEM
# -----------------------------

def get_spin_data(user_id: int):
    """Get or create spin data for user."""
    c.execute("SELECT * FROM spin_wheel_data WHERE user_id = ?", (user_id,))
    data = c.fetchone()
    if not data:
        c.execute("""
            INSERT INTO spin_wheel_data (user_id, free_spins, purchased_spins, last_spin_time, total_spins_used, total_winnings, daily_purchased, last_purchase_date)
            VALUES (?, 0, 0, NULL, 0, 0, 0, NULL)
        """, (user_id,))
        conn.commit()
        return (user_id, 0, 0, None, 0, 0, 0, None)
    return data

def update_spin_data(user_id: int, free_spins: int = None, purchased_spins: int = None, last_spin_time: str = None, daily_purchased: int = None, last_purchase_date: str = None):
    """Update user spin data."""
    updates = []
    params = []
    
    if free_spins is not None:
        updates.append("free_spins = ?")
        params.append(free_spins)
    if purchased_spins is not None:
        updates.append("purchased_spins = ?")
        params.append(purchased_spins)
    if last_spin_time is not None:
        updates.append("last_spin_time = ?")
        params.append(last_spin_time)
    if daily_purchased is not None:
        updates.append("daily_purchased = ?")
        params.append(daily_purchased)
    if last_purchase_date is not None:
        updates.append("last_purchase_date = ?")
        params.append(last_purchase_date)
    
    if updates:
        params.append(user_id)
        c.execute(f"UPDATE spin_wheel_data SET {', '.join(updates)} WHERE user_id = ?", params)
        conn.commit()

def check_and_grant_daily_spin(user_id: int):
    """Check if user should receive their daily spin (24h passed since last spin)."""
    data = get_spin_data(user_id)
    last_spin_time = data[3]
    
    if last_spin_time is None:
        # Never spun before, no daily spin yet
        return False
    
    last_spin = datetime.fromisoformat(last_spin_time)
    time_since_spin = datetime.now() - last_spin
    
    # If 24 hours passed and they used their previous spin, grant new one
    if time_since_spin >= timedelta(hours=24) and data[1] == 0:  # free_spins == 0
        update_spin_data(user_id, free_spins=1)
        return True
    
    return False

def spin_wheel(user_id, is_paid_spin=False):
    """Execute a wheel spin and return the prize with provably fair info."""
    # Use provably fair to generate result (0-199 for precise percentages)
    result, client_seed, nonce, seed_hash = provably_fair.place_bet(
        user_id, "spinwheel", 0, 200  # amount=0 since spin cost was already paid/deducted
    )
    roll = result  # Already 0-199
    
    if is_paid_spin:
        # PAID SPINS - Enhanced Prize Pool
        # 55% (110/200) → 6.5M
        # 34% (68/200) → 20M
        # 2% (4/200) → 55M
        # 1% (2/200) → 100M
        # 0.5% (1/200) → Stock Pet
        # 0.5% (1/200) → 300M
        # 6.5% (13/200) → Recalculated base prizes
        
        if roll < 110:  # 0-109: 55%
            prize = {"type": "money", "value": 6_500_000, "display": "6.5M💰"}
        elif roll < 178:  # 110-177: 34%
            prize = {"type": "money", "value": 20_000_000, "display": "20M💰"}
        elif roll < 182:  # 178-181: 2%
            prize = {"type": "money", "value": 55_000_000, "display": "55M💰"}
        elif roll < 184:  # 182-183: 1%
            prize = {"type": "money", "value": 100_000_000, "display": "100M💰"}
        elif roll < 185:  # 184: 0.5%
            prize = {"type": "pet", "value": None, "display": "🐾 STOCK PET 🐾"}
        elif roll < 186:  # 185: 0.5%
            prize = {"type": "money", "value": 300_000_000, "display": "300M💰💎"}
        else:  # 186-199: 7% (filler - returns to base 6.5M)
            prize = {"type": "money", "value": 6_500_000, "display": "6.5M💰"}
    else:
        # FREE SPINS - Standard Prize Pool
        # 55% (110/200) → 3M
        # 34% (68/200) → 10M
        # 2% (4/200) → 25M
        # 1% (2/200) → 50M
        # 0.5% (1/200) → Stock Pet
        # 0.5% (1/200) → 200M
        # 6.5% (13/200) → Recalculated base prizes
        
        if roll < 110:  # 0-109: 55%
            prize = {"type": "money", "value": 3_000_000, "display": "3M💰"}
        elif roll < 178:  # 110-177: 34%
            prize = {"type": "money", "value": 10_000_000, "display": "10M💰"}
        elif roll < 182:  # 178-181: 2%
            prize = {"type": "money", "value": 25_000_000, "display": "25M💰"}
        elif roll < 184:  # 182-183: 1%
            prize = {"type": "money", "value": 50_000_000, "display": "50M💰"}
        elif roll < 185:  # 184: 0.5%
            prize = {"type": "pet", "value": None, "display": "🐾 STOCK PET 🐾"}
        elif roll < 186:  # 185: 0.5%
            prize = {"type": "money", "value": 200_000_000, "display": "200M💰💎"}
        else:  # 186-199: 7% (filler - returns to base 3M)
            prize = {"type": "money", "value": 3_000_000, "display": "3M💰"}
    
    # Add provably fair info to prize
    prize["client_seed"] = client_seed
    prize["nonce"] = nonce
    prize["seed_hash"] = seed_hash
    
    return prize

class SpinWheelView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.spinning = False
        
    @discord.ui.button(label="SPIN!", style=discord.ButtonStyle.success, emoji="🎰")
    async def spin_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your spin wheel!", ephemeral=True)
            return
        
        if self.spinning:
            await interaction.response.send_message("❌ Already spinning!", ephemeral=True)
            return
        
        # Check if user has spins
        data = get_spin_data(self.user_id)
        free_spins = data[1]
        purchased_spins = data[2]
        total_spins = free_spins + purchased_spins
        
        if total_spins <= 0:
            await interaction.response.send_message("❌ You don't have any spins! Use !buyspin to purchase more.", ephemeral=True)
            return
        
        self.spinning = True
        
        # Deduct a spin (prefer free spins first)
        if free_spins > 0:
            update_spin_data(self.user_id, free_spins=free_spins - 1)
            spin_type = "free"
            is_paid = False
        else:
            update_spin_data(self.user_id, purchased_spins=purchased_spins - 1)
            spin_type = "purchased"
            is_paid = True
        
        # Update last spin time
        update_spin_data(self.user_id, last_spin_time=datetime.now().isoformat())
        
        # Create spinning animation with appropriate prizes
        if is_paid:
            prizes = ["6.5M💰", "20M💰", "55M💰", "100M💰", "🐾PET🐾", "300M💰💎"]
            title_text = "🎰 SPINNING THE WHEEL! 🎰 (PAID SPIN - BETTER PRIZES!)"
        else:
            prizes = ["3M💰", "10M💰", "25M💰", "50M💰", "🐾PET🐾", "200M💰💎"]
            title_text = "🎰 SPINNING THE WHEEL! 🎰"
        
        # Animate the spin
        animation_embed = discord.Embed(
            title=title_text,
            description="",
            color=discord.Color.gold()
        )
        
        await interaction.response.edit_message(embed=animation_embed)
        
        # Show animation frames
        for i in range(12):
            prize_list = "\n".join([f"{'▶️' if j == i % len(prizes) else '⚪'} {prizes[j]}" for j in range(len(prizes))])
            animation_embed.description = f"```\n{prize_list}\n```"
            await interaction.edit_original_response(embed=animation_embed)
            await asyncio.sleep(0.15)
        
        # Get actual prize
        prize = spin_wheel(self.user_id, is_paid_spin=is_paid)
        
        # Process the prize
        result_embed = discord.Embed(
            title="🎉 WHEEL RESULT! 🎉",
            color=discord.Color.green() if prize["type"] == "money" else discord.Color.purple()
        )
        
        if prize["type"] == "money":
            # Credit money
            bal_before = get_balance(self.user_id)
            update_balance(self.user_id, prize["value"])
            bal_after = get_balance(self.user_id)
            
            result_embed.add_field(
                name="🎁 YOU WON",
                value=f"**{prize['display']}**",
                inline=False
            )
            result_embed.add_field(
                name="💵 Balance Update",
                value=f"{format_money(bal_before)} ➔ {format_money(bal_after)}",
                inline=False
            )
            
            # Add provably fair information
            result_embed.add_field(
                name="🔐 Provably Fair",
                value=f"Nonce: {prize.get('nonce', 0)} | Client: {prize.get('client_seed', '')[:8]}...\nSeed Hash: {prize.get('seed_hash', '')[:16]}...\nUse `!verify` to verify fairness",
                inline=False
            )
            
            # Log transaction
            log_transaction(self.user_id, "spin_win", prize["value"], bal_before, bal_after, 
                          f"Spin wheel win - {spin_type} spin")
            
            # Update stats
            c.execute("""
                UPDATE spin_wheel_data 
                SET total_spins_used = total_spins_used + 1,
                    total_winnings = total_winnings + ?
                WHERE user_id = ?
            """, (prize["value"], self.user_id))
            conn.commit()
            
        elif prize["type"] == "pet":
            # Special pet prize
            global current_special_prize
            if current_special_prize:
                result_embed.add_field(
                    name="🎁 MEGA WIN! 🐾",
                    value=f"**You won: {current_special_prize['pet_name']}**\n\n"
                          f"Account: {current_special_prize.get('account', 'N/A')}\n"
                          f"Pet ID: #{current_special_prize['pet_id']}\n\n"
                          f"🎫 **Please open a support ticket to claim your prize!**",
                    inline=False
                )
                
                # Add provably fair information
                result_embed.add_field(
                    name="🔐 Provably Fair",
                    value=f"Nonce: {prize.get('nonce', 0)} | Client: {prize.get('client_seed', '')[:8]}...\nSeed Hash: {prize.get('seed_hash', '')[:16]}...\nUse `!verify` to verify fairness",
                    inline=False
                )
            else:
                # Fallback if no special prize set
                result_embed.add_field(
                    name="🎁 MEGA WIN! 🐾",
                    value=f"**You won a SPECIAL PRIZE!**\n\n"
                          f"🎫 **Please open a support ticket to claim your prize!**\n"
                          f"Contact an owner to claim your stock pet!",
                    inline=False
                )
                
                # Add provably fair information
                result_embed.add_field(
                    name="🔐 Provably Fair",
                    value=f"Nonce: {prize.get('nonce', 0)} | Client: {prize.get('client_seed', '')[:8]}...\nSeed Hash: {prize.get('seed_hash', '')[:16]}...\nUse `!verify` to verify fairness",
                    inline=False
                )
            
            # Notify owners about the pet prize win
            try:
                winner = interaction.guild.get_member(self.user_id)
                winner_mention = winner.mention if winner else f"User ID: {self.user_id}"
                
                owner_notification = discord.Embed(
                    title="🚨 STOCK PET WON! 🐾",
                    description=f"**{winner.display_name if winner else 'A user'}** just won the stock pet!\n\n"
                                f"Winner: {winner_mention}\n"
                                f"Prize: {current_special_prize['pet_name'] if current_special_prize else 'Stock Pet'}\n"
                                f"Pet ID: #{current_special_prize['pet_id'] if current_special_prize else 'N/A'}",
                    color=discord.Color.gold(),
                    timestamp=datetime.now()
                )
                
                # DM and ping both owners
                for owner_id in OWNER_IDS:
                    try:
                        owner = await bot.fetch_user(owner_id)
                        if owner:
                            # Send DM
                            await owner.send(embed=owner_notification)
                            # Try to mention in channel if possible
                            if interaction.channel:
                                await interaction.channel.send(f"<@{owner_id}> Stock pet won by {winner_mention}!", embed=owner_notification)
                    except Exception as e:
                        print(f"Failed to notify owner {owner_id}: {e}")
            except Exception as e:
                print(f"Error notifying owners about stock pet win: {e}")
            
            # Update stats
            c.execute("""
                UPDATE spin_wheel_data 
                SET total_spins_used = total_spins_used + 1
                WHERE user_id = ?
            """, (self.user_id,))
            conn.commit()
        
        # Record in history
        c.execute("""
            INSERT INTO spin_wheel_history (user_id, prize_type, prize_value, timestamp, spin_type)
            VALUES (?, ?, ?, ?, ?)
        """, (self.user_id, prize["type"], str(prize["value"]), datetime.now().isoformat(), spin_type))
        conn.commit()
        
        # Update remaining spins display
        data = get_spin_data(self.user_id)
        result_embed.set_footer(text=f"Remaining Spins: {data[1]} Free + {data[2]} Purchased")
        
        self.spinning = False
        await interaction.edit_original_response(embed=result_embed, view=self)
    
    @discord.ui.button(label="Buy Spin", style=discord.ButtonStyle.primary, emoji="💰")
    async def buy_spin_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your spin wheel!", ephemeral=True)
            return
        
        # Show purchase options
        view = BuySpinView(self.user_id)
        embed = discord.Embed(
            title="💰 Purchase Spins",
            description="Select how many spins you'd like to buy:",
            color=discord.Color.blue()
        )
        embed.add_field(name="1 Spin", value="10M 💵", inline=True)
        embed.add_field(name="3 Spins", value="30M 💵", inline=True)
        embed.set_footer(text="Purchased spins stack and don't expire!")
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class BuySpinView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
    
    @discord.ui.button(label="1 Spin (10M)", style=discord.ButtonStyle.success, emoji="1️⃣")
    async def buy_one(self, interaction: discord.Interaction, button: Button):
        await self.purchase_spins(interaction, 1, 10_000_000)
    
    @discord.ui.button(label="3 Spins (30M)", style=discord.ButtonStyle.success, emoji="3️⃣")
    async def buy_three(self, interaction: discord.Interaction, button: Button):
        await self.purchase_spins(interaction, 3, 30_000_000)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="❌ Purchase cancelled.", embed=None, view=None)
    
    async def purchase_spins(self, interaction: discord.Interaction, count: int, cost: int):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your purchase menu!", ephemeral=True)
            return
        
        # Check if user is an owner (bypass daily limit)
        is_owner = interaction.user.id in [1182265710248996874, 1249352131870195744, 1250923685443797035]
        
        if not is_owner:
            # Check daily purchase limit for non-owners
            data = get_spin_data(self.user_id)
            daily_purchased = data[6] if len(data) > 6 else 0
            last_purchase_date = data[7] if len(data) > 7 else None
            
            today = datetime.now().date().isoformat()
            
            # Reset daily count if it's a new day
            if last_purchase_date != today:
                daily_purchased = 0
            
            # Check if purchase would exceed daily limit
            if daily_purchased + count > 10:
                remaining = 10 - daily_purchased
                await interaction.response.edit_message(
                    content=f"❌ Daily purchase limit reached! You can only buy {remaining} more spin(s) today.\n"
                            f"Daily limit: 10 spins per day (resets at midnight)\n"
                            f"Already purchased today: {daily_purchased} spin(s)",
                    embed=None,
                    view=None
                )
                return
        
        # Check balance
        balance = get_balance(self.user_id)
        if balance < cost:
            await interaction.response.edit_message(
                content=f"❌ Insufficient funds! You need {format_money(cost)} but only have {format_money(balance)}.",
                embed=None,
                view=None
            )
            return
        
        # Process purchase
        bal_before = balance
        update_balance(self.user_id, -cost)
        bal_after = get_balance(self.user_id)
        
        # Add purchased spins
        data = get_spin_data(self.user_id)
        purchased_spins = data[2]
        update_spin_data(self.user_id, purchased_spins=purchased_spins + count)
        
        # Update daily purchase count for non-owners
        if not is_owner:
            daily_purchased = data[6] if len(data) > 6 else 0
            last_purchase_date = data[7] if len(data) > 7 else None
            today = datetime.now().date().isoformat()
            
            # Reset if new day
            if last_purchase_date != today:
                daily_purchased = 0
            
            update_spin_data(self.user_id, daily_purchased=daily_purchased + count, last_purchase_date=today)
        
        # Log transaction
        log_transaction(self.user_id, "spin_purchase", -cost, bal_before, bal_after,
                       f"Purchased {count} spin(s)")
        
        # Success message
        embed = discord.Embed(
            title="✅ Purchase Successful!",
            description=f"You purchased **{count} spin(s)** for {format_money(cost)}",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Balance Update",
            value=f"{format_money(bal_before)} ➔ {format_money(bal_after)}",
            inline=False
        )
        embed.add_field(
            name="Total Spins",
            value=f"Free: {data[1]} | Purchased: {purchased_spins + count}",
            inline=False
        )
        
        # Add daily purchase info for non-owners
        if not is_owner:
            data_updated = get_spin_data(self.user_id)
            daily_purchased_new = data_updated[6] if len(data_updated) > 6 else 0
            embed.add_field(
                name="Daily Purchases",
                value=f"{daily_purchased_new}/10 spins purchased today",
                inline=False
            )
        
        await interaction.response.edit_message(content=None, embed=embed, view=None)

@bot.command(name="spinwheel")
async def spinwheel(ctx):
    """Spin the daily wheel for prizes!"""
    global spin_wheel_active
    
    if not spin_wheel_active:
        await ctx.send("❌ The spin wheel hasn't been activated yet! Wait for an owner to use !activatewheel")
        return
    
    # Check and grant daily spin if applicable
    check_and_grant_daily_spin(ctx.author.id)
    
    # Get spin data
    data = get_spin_data(ctx.author.id)
    free_spins = data[1]
    purchased_spins = data[2]
    total_spins = free_spins + purchased_spins
    last_spin_time = data[3]
    
    # Create wheel embed
    embed = discord.Embed(
        title="🎰 ELI'S MEGA SPIN WHEEL 🎰",
        description="Press **SPIN!** to test your luck!\n\n"
                    "**FREE SPIN PRIZES:**\n"
                    "💰 3M (55%) | 💰 10M (34%)\n"
                    "💰 25M (2%) | 💰 50M (1%)\n"
                    "🐾 Stock Pet (0.5%) | 💎 200M (0.5%)\n\n"
                    "**PAID SPIN PRIZES (BETTER!):**\n"
                    "💰 6.5M (55%) | 💰 20M (34%)\n"
                    "💰 55M (2%) | 💰 100M (1%)\n"
                    "🐾 Stock Pet (0.5%) | 💎 300M (0.5%)",
        color=discord.Color.gold()
    )
    
    # Show spin status
    if last_spin_time:
        last_spin = datetime.fromisoformat(last_spin_time)
        time_until_next = last_spin + timedelta(hours=24) - datetime.now()
        if time_until_next.total_seconds() > 0:
            hours = int(time_until_next.total_seconds() // 3600)
            minutes = int((time_until_next.total_seconds() % 3600) // 60)
            embed.add_field(
                name="⏰ Next Free Spin",
                value=f"In {hours}h {minutes}m" if free_spins == 0 else "Ready!",
                inline=True
            )
    else:
        embed.add_field(
            name="⏰ Next Free Spin",
            value="Ready!",
            inline=True
        )
    
    embed.add_field(
        name="🎫 Available Spins",
        value=f"Free: **{free_spins}** | Purchased: **{purchased_spins}**",
        inline=True
    )
    
    if total_spins == 0:
        embed.add_field(
            name="💵 No Spins?",
            value="Use the **Buy Spin** button or !buyspin",
            inline=False
        )
    
    embed.set_footer(text=f"Total Spins Used: {data[4]} | Total Won: {format_money(data[5])}")
    
    view = SpinWheelView(ctx.author.id)
    await ctx.send(embed=embed, view=view)

@bot.command(name="buyspin")
async def buyspin(ctx):
    """Purchase additional spins for 10M each."""
    global spin_wheel_active
    
    if not spin_wheel_active:
        await ctx.send("❌ The spin wheel hasn't been activated yet!")
        return
    
    # Show purchase menu
    view = BuySpinView(ctx.author.id)
    embed = discord.Embed(
        title="💰 Purchase Spins",
        description="Select how many spins you'd like to buy:\n\n"
                    "**Purchased spins:**\n"
                    "✅ Stack with free spins\n"
                    "✅ Never expire\n"
                    "✅ Don't affect daily spin timer",
        color=discord.Color.blue()
    )
    embed.add_field(name="1 Spin", value="10M 💵", inline=True)
    embed.add_field(name="3 Spins", value="30M 💵", inline=True)
    
    balance = get_balance(ctx.author.id)
    embed.set_footer(text=f"Your Balance: {format_money(balance)}")
    
    await ctx.send(embed=embed, view=view)

@bot.command(name="activatewheel")
async def activatewheel(ctx):
    """Owner command: Activate the spin wheel and grant all members 1 free spin."""
    # Check if user is authorized (specific user IDs only)
    if ctx.author.id not in [1182265710248996874, 1249352131870195744, 1250923685443797035]:
        await ctx.send("❌ This command is only available to specific owners!")
        return
    
    global spin_wheel_active
    
    if spin_wheel_active:
        await ctx.send("❌ The spin wheel is already activated!")
        return
    
    # Activate the wheel
    spin_wheel_active = True
    
    # Get all members with @member role
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        await ctx.send("❌ Could not find guild!")
        return
    
    member_role = guild.get_role(1442285739067834528)  # @member role ID
    if not member_role:
        await ctx.send("⚠️ Warning: Could not find @member role. Wheel activated but no spins granted.")
        return
    
    # Grant 1 free spin to all members
    count = 0
    for member in member_role.members:
        if not member.bot:
            # Get or create spin data
            get_spin_data(member.id)
            # Grant 1 free spin
            update_spin_data(member.id, free_spins=1)
            count += 1
    
    embed = discord.Embed(
        title="🎰 SPIN WHEEL ACTIVATED! 🎰",
        description=f"The daily spin wheel is now live!\n\n"
                    f"✅ Granted **1 free spin** to **{count} members**\n\n"
                    f"Players can now use !spinwheel to play!",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="deactivatewheel")
async def deactivatewheel(ctx):
    """Owner command: Deactivate the spin wheel and reset all stats."""
    # Check if user is authorized (specific user IDs only)
    if ctx.author.id not in [1182265710248996874, 1249352131870195744, 1250923685443797035]:
        await ctx.send("❌ This command is only available to specific owners!")
        return
    
    global spin_wheel_active
    
    if not spin_wheel_active:
        await ctx.send("❌ The spin wheel is not currently activated!")
        return
    
    # Confirm deactivation
    confirm_embed = discord.Embed(
        title="⚠️ CONFIRM DEACTIVATION",
        description="This will:\n"
                    "• Deactivate the spin wheel\n"
                    "• **DELETE ALL** user spin data\n"
                    "• **DELETE ALL** spin history\n"
                    "• Reset the system to initial state\n\n"
                    "This action **CANNOT BE UNDONE**!\n\n"
                    "React with ✅ to confirm or ❌ to cancel.",
        color=discord.Color.red()
    )
    confirm_msg = await ctx.send(embed=confirm_embed)
    await confirm_msg.add_reaction("✅")
    await confirm_msg.add_reaction("❌")
    
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
    
    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
        
        if str(reaction.emoji) == "❌":
            await ctx.send("❌ Deactivation cancelled.")
            return
        
        # Proceed with deactivation
        conn = sqlite3.connect('gambling_bot.db')
        c = conn.cursor()
        
        # Delete all spin wheel data
        c.execute("DELETE FROM spin_wheel_data")
        c.execute("DELETE FROM spin_wheel_history")
        
        conn.commit()
        conn.close()
        
        # Deactivate the wheel
        spin_wheel_active = False
        
        success_embed = discord.Embed(
            title="🔴 SPIN WHEEL DEACTIVATED",
            description="The spin wheel has been deactivated and all data has been reset.\n\n"
                        f"✅ Deleted all user spin data\n"
                        f"✅ Deleted all spin history\n"
                        f"✅ System reset to initial state\n\n"
                        f"Use `!activatewheel` to reactivate.",
            color=discord.Color.red()
        )
        await ctx.send(embed=success_embed)
        
    except asyncio.TimeoutError:
        await ctx.send("⏱️ Confirmation timed out. Deactivation cancelled.")

@bot.command(name="addspin")
async def addspin(ctx, member: discord.Member, amount: int = 1):
    """Owner command: Gift spins to a specific user."""
    # Restrict to specific user IDs
    allowed_user_ids = [1182265710248996874, 1249352131870195744, 1250923685443797035]
    if ctx.author.id not in allowed_user_ids:
        await ctx.send("❌ You don't have permission to use this command!")
        return
    
    if amount < 1:
        await ctx.send("❌ Amount must be at least 1!")
        return
    
    if amount > 100:
        await ctx.send("❌ Maximum 100 spins at once!")
        return
    
    # Get current data
    data = get_spin_data(member.id)
    purchased_spins = data[2]
    
    # Add spins (as purchased so they stack)
    update_spin_data(member.id, purchased_spins=purchased_spins + amount)
    
    embed = discord.Embed(
        title="🎁 Spins Gifted!",
        description=f"Added **{amount} spin(s)** to {member.mention}",
        color=discord.Color.green()
    )
    embed.add_field(
        name="New Total",
        value=f"Free: {data[1]} | Purchased: {purchased_spins + amount}",
        inline=False
    )
    
    await ctx.send(embed=embed)
    
    # Notify the member
    try:
        dm_embed = discord.Embed(
            title="🎁 You received free spins!",
            description=f"An owner gifted you **{amount} spin(s)**!\n\nUse !spinwheel to play!",
            color=discord.Color.gold()
        )
        await member.send(embed=dm_embed)
    except:
        pass  # DMs disabled

@bot.command(name="setspecialprize")
async def setspecialprize(ctx, *, args: str):
    """Owner command: Set the special stock pet prize for the 0.5% win.
    
    Usage: !setspecialprize <pet_name>, <account_name>
    Example: !setspecialprize Naughty Naughty 10m/s, gamb1ebotbank1
    """
    # Check if user is authorized (specific user IDs only)
    if ctx.author.id not in [1182265710248996874, 1249352131870195744, 1250923685443797035]:
        await ctx.send("❌ This command is only available to specific owners!")
        return
    
    # Parse the arguments (pet_name, account_name)
    try:
        parts = args.split(",", 1)
        if len(parts) != 2:
            await ctx.send("❌ Invalid format! Use: `!setspecialprize <pet_name>, <account_name>`\n"
                          "Example: `!setspecialprize Naughty Naughty 10m/s, gamb1ebotbank1`")
            return
        
        pet_name = parts[0].strip()
        account_name = parts[1].strip()
        
        if not pet_name or not account_name:
            await ctx.send("❌ Pet name and account name cannot be empty!")
            return
    except Exception as e:
        await ctx.send(f"❌ Error parsing command: {str(e)}")
        return
    
    global current_special_prize
    
    # Generate a special ID for wheel prizes (using negative numbers to differentiate from stock items)
    import secrets
    wheel_prize_id = -abs(secrets.randbelow(1000000) + 1)
    
    current_special_prize = {
        "pet_id": wheel_prize_id,
        "pet_name": pet_name,
        "account": account_name,
        "is_wheel_prize": True
    }
    
    embed = discord.Embed(
        title="✅ Special Prize Set!",
        description=f"The 0.5% wheel prize is now:\n\n"
                    f"**{pet_name}**\n"
                    f"Account: {account_name}\n"
                    f"Wheel Prize ID: #{wheel_prize_id}",
        color=discord.Color.purple()
    )
    embed.set_footer(text="This prize is separate from stock items and cannot be purchased")
    await ctx.send(embed=embed)

@bot.command(name="changewheelpet")
async def changewheelpet(ctx, *, args: str):
    """Owner command: Change the special stock pet prize for the 0.5% win.
    
    Usage: !changewheelpet <pet_name>, <account_name>
    Example: !changewheelpet Naughty Naughty 10m/s, gamb1ebotbank1
    """
    # Check if user is authorized (specific user IDs only)
    if ctx.author.id not in [1182265710248996874, 1249352131870195744, 1250923685443797035]:
        await ctx.send("❌ This command is only available to specific owners!")
        return
    
    # Parse the arguments (pet_name, account_name)
    try:
        parts = args.split(",", 1)
        if len(parts) != 2:
            await ctx.send("❌ Invalid format! Use: `!changewheelpet <pet_name>, <account_name>`\n"
                          "Example: `!changewheelpet Naughty Naughty 10m/s, gamb1ebotbank1`")
            return
        
        pet_name = parts[0].strip()
        account_name = parts[1].strip()
        
        if not pet_name or not account_name:
            await ctx.send("❌ Pet name and account name cannot be empty!")
            return
    except Exception as e:
        await ctx.send(f"❌ Error parsing command: {str(e)}")
        return
    
    global current_special_prize
    
    # Generate a special ID for wheel prizes (using negative numbers to differentiate from stock items)
    import secrets
    wheel_prize_id = -abs(secrets.randbelow(1000000) + 1)
    
    current_special_prize = {
        "pet_id": wheel_prize_id,
        "pet_name": pet_name,
        "account": account_name,
        "is_wheel_prize": True
    }
    
    embed = discord.Embed(
        title="✅ Wheel Pet Prize Updated!",
        description=f"The 0.5% wheel prize has been changed to:\n\n"
                    f"**{pet_name}**\n"
                    f"Account: {account_name}\n"
                    f"Wheel Prize ID: #{wheel_prize_id}",
        color=discord.Color.purple()
    )
    embed.set_footer(text="This prize is separate from stock items and cannot be purchased")
    await ctx.send(embed=embed)

@bot.command(name="autowinpet")
async def autowinpet(ctx):
    """Owner command: Auto-win the pet prize for testing purposes."""
    # Check if user is authorized (specific user IDs only)
    if ctx.author.id not in [1182265710248996874, 1249352131870195744, 1250923685443797035]:
        await ctx.send("❌ This command is only available to specific owners!")
        return
    
    global current_special_prize
    if not current_special_prize:
        await ctx.send("❌ No wheel prize is currently set! Use `!setspecialprize` first.")
        return
    
    # Create win notification embed
    result_embed = discord.Embed(
        title="🎰 TESTING: AUTO PET WIN 🎰",
        description="**Simulating 0.5% pet win for testing...**",
        color=discord.Color.gold()
    )
    
    result_embed.add_field(
        name="🎁 MEGA WIN! 🐾",
        value=f"**You won: {current_special_prize['pet_name']}**\n\n"
              f"Account: {current_special_prize.get('account', 'N/A')}\n"
              f"Pet ID: #{current_special_prize['pet_id']}\n\n"
              f"🎫 **Please open a support ticket to claim your prize!**",
        inline=False
    )
    
    result_embed.set_footer(text="This is a test command - no actual prize awarded")
    await ctx.send(embed=result_embed)
    
    # Notify owners about the test win
    try:
        winner = ctx.author
        winner_mention = winner.mention
        
        owner_notification = discord.Embed(
            title="🚨 TEST: STOCK PET WON! 🐾",
            description=f"**{winner.display_name}** triggered test pet win!\n\n"
                        f"Winner: {winner_mention}\n"
                        f"Prize: {current_special_prize['pet_name']}\n"
                        f"Pet ID: #{current_special_prize['pet_id']}\n"
                        f"Account: {current_special_prize.get('account', 'N/A')}",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        owner_notification.set_footer(text="This was a test command - no actual prize awarded")
        
        # DM and ping both owners
        OWNER_IDS = [1182265710248996874, 1249352131870195744, 1250923685443797035]
        for owner_id in OWNER_IDS:
            try:
                owner = await bot.fetch_user(owner_id)
                if owner:
                    # Send DM
                    await owner.send(embed=owner_notification)
                    # Try to mention in channel if possible
                    if ctx.channel:
                        await ctx.channel.send(f"<@{owner_id}> Test pet win triggered by {winner_mention}!", embed=owner_notification)
            except Exception as e:
                print(f"Failed to notify owner {owner_id}: {e}")
    except Exception as e:
        print(f"Error notifying owners about test pet win: {e}")

@bot.command(name="ownermessage")
async def ownermessage(ctx, channel: discord.TextChannel, *, message: str):
    """Owner command: Send a message as the bot to any channel.
    
    Usage: !ownermessage #channel-name Your message here
    Example: !ownermessage #announcements Welcome to the server!
    """
    # Check if user is authorized (specific user IDs only)
    if ctx.author.id not in [1182265710248996874, 1249352131870195744, 1250923685443797035]:
        await ctx.send("❌ This command is only available to specific owners!")
        return
    
    try:
        # Send the message to the target channel as the bot
        await channel.send(message)
        
        # Confirm to the owner (in their command channel)
        await ctx.send(f"✅ Message sent to {channel.mention}!")
    except discord.Forbidden:
        await ctx.send(f"❌ I don't have permission to send messages in {channel.mention}!")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {str(e)}")

@bot.command(name="wheelstats")
async def wheelstats(ctx, member: discord.Member = None):
    """View spin wheel statistics."""
    target = member or ctx.author
    
    data = get_spin_data(target.id)
    
    embed = discord.Embed(
        title=f"🎰 {target.display_name}'s Wheel Stats",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Available Spins",
        value=f"Free: **{data[1]}**\nPurchased: **{data[2]}**",
        inline=True
    )
    
    embed.add_field(
        name="Statistics",
        value=f"Total Spins: **{data[4]}**\nTotal Winnings: **{format_money(data[5])}**",
        inline=True
    )
    
    if data[3]:
        last_spin = datetime.fromisoformat(data[3])
        time_until_next = last_spin + timedelta(hours=24) - datetime.now()
        if time_until_next.total_seconds() > 0:
            hours = int(time_until_next.total_seconds() // 3600)
            minutes = int((time_until_next.total_seconds() % 3600) // 60)
            embed.add_field(
                name="Next Free Spin",
                value=f"In {hours}h {minutes}m",
                inline=False
            )
        else:
            embed.add_field(
                name="Next Free Spin",
                value="Ready! (Spin to claim)",
                inline=False
            )
    
    embed.set_thumbnail(url=target.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="spincom")
async def spincom(ctx):
    """View all available spin wheel commands."""
    embed = discord.Embed(
        title="🎰 Spin Wheel Commands",
        description="Complete list of spin wheel commands and features",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name="🎮 Player Commands",
        value=(
            "`!spinwheel` - Open the spin wheel and spin\n"
            "`!buyspin` - Purchase additional spins (10M each, 3 for 30M)\n"
            "`!wheelstats [@user]` - View spin statistics\n"
            "`!spincom` - View this command list"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Owner Commands",
        value=(
            "`!activatewheel` - Activate wheel and grant all members 1 free spin\n"
            "`!deactivatewheel` - Deactivate wheel and reset all data\n"
            "`!addspin @user <amount>` - Gift spins to a user\n"
            "`!setspecialprize <pet_name>, <account>` - Set the wheel pet prize\n"
            "`!changewheelpet <pet_name>, <account>` - Change the wheel pet prize\n"
            "`!autowinpet` - Test pet win (dev testing)"
        ),
        inline=False
    )
    
    embed.add_field(
        name="💰 Prize Information",
        value=(
            "**Free Spins**: 3M-200M range\n"
            "**Paid Spins**: 6.5M-300M range (**BETTER REWARDS!**)\n"
            "Both have 0.5% chance for Stock Pet"
        ),
        inline=False
    )
    
    embed.add_field(
        name="ℹ️ How It Works",
        value=(
            "• Get 1 free spin daily (resets 24h after use)\n"
            "• Purchase spins stack indefinitely\n"
            "• Free spins used first, then purchased spins\n"
            "• Purchased spins give **HIGHER REWARDS**!"
        ),
        inline=False
    )
    
    embed.set_footer(text="Use !games to see all gambling games")
    await ctx.send(embed=embed)

@bot.command(name="ownerdonation")
async def ownerdonation(ctx, recipient: discord.Member, value: str):
    """
    Owner command to donate to users with no limits or cooldowns.
    
    Usage: !ownerdonation @user <amount>
    Example: !ownerdonation @John 500m
    """
    # Check if user is authorized (specific user IDs only)
    if ctx.author.id not in [1182265710248996874, 1249352131870195744, 1250923685443797035]:
        await ctx.send("❌ This command is only available to specific owners!")
        return
    
    # Parse amount
    try:
        parsed_value = parse_money(value)
    except ValueError as e:
        await ctx.send(f"❌ Invalid amount: {str(e)}")
        return
    
    # Check if trying to donate to self
    if recipient.id == ctx.author.id:
        await ctx.send("❌ You cannot donate to yourself!")
        return
    
    # Check if recipient is a bot
    if recipient.bot:
        await ctx.send("❌ You cannot donate to bots!")
        return
    
    # Get owner's balance
    owner_balance = get_balance(ctx.author.id)
    if owner_balance < parsed_value:
        await ctx.send(f"❌ Insufficient balance! You have {format_money(owner_balance)} but tried to donate {format_money(parsed_value)}")
        return
    
    # Execute transaction
    owner_bal_before = owner_balance
    recipient_bal_before = get_balance(recipient.id)
    
    # Deduct from owner
    update_balance(ctx.author.id, -parsed_value)
    owner_bal_after = get_balance(ctx.author.id)
    
    # Add to recipient
    update_balance(recipient.id, parsed_value)
    recipient_bal_after = get_balance(recipient.id)
    
    # Verify transaction integrity
    expected_owner_bal = owner_bal_before - parsed_value
    expected_recipient_bal = recipient_bal_before + parsed_value
    
    if owner_bal_after != expected_owner_bal or recipient_bal_after != expected_recipient_bal:
        # Rollback transaction
        update_balance(ctx.author.id, parsed_value)
        update_balance(recipient.id, -parsed_value)
        await ctx.send("❌ Transaction failed due to integrity check. No money was transferred.")
        log_transaction(ctx.author.id, "owner_donation_failed", 0, owner_bal_before, owner_bal_before,
                       f"Failed owner donation to {recipient.id}")
        return
    
    # Log transactions
    log_transaction(ctx.author.id, "owner_donation_sent", -parsed_value, owner_bal_before, owner_bal_after,
                   f"Owner donated {format_money(parsed_value)} to {recipient.id}")
    log_transaction(recipient.id, "owner_donation_received", parsed_value, recipient_bal_before, recipient_bal_after,
                   f"Received owner donation of {format_money(parsed_value)} from {ctx.author.id}")
    
    # Send confirmation in channel
    embed = discord.Embed(
        title="👑 Owner Donation",
        description=f"**{ctx.author.mention}** has donated {format_money(parsed_value)} to {recipient.mention}!",
        color=discord.Color.gold()
    )
    embed.add_field(
        name=f"{ctx.author.display_name}'s Balance",
        value=f"{format_money(owner_bal_before)} ➔ {format_money(owner_bal_after)}",
        inline=True
    )
    embed.add_field(
        name=f"{recipient.display_name}'s Balance",
        value=f"{format_money(recipient_bal_before)} ➔ {format_money(recipient_bal_after)}",
        inline=True
    )
    await ctx.send(embed=embed)
    
    # Send DM to recipient
    try:
        dm_embed = discord.Embed(
            title="💰 You Received an Owner Donation!",
            description=f"**{ctx.author.display_name}** has donated **{format_money(parsed_value)}** to you!",
            color=discord.Color.gold()
        )
        dm_embed.add_field(
            name="Your New Balance",
            value=format_money(recipient_bal_after),
            inline=False
        )
        dm_embed.set_footer(text="This is an owner donation with no limits")
        await recipient.send(embed=dm_embed)
    except discord.Forbidden:
        # User has DMs disabled
        await ctx.send(f"⚠️ Could not DM {recipient.mention} (DMs disabled)")

# -----------------------------
# 🔄 RESET GAMES COMMAND
# -----------------------------
@bot.command(name='resetgames')
async def reset_games(ctx):
    """
    Cancel all active games for the user and refund when appropriate.
    Prevents money glitches by only refunding games that haven't been resolved.
    """
    user_id = ctx.author.id
    refunded = 0
    games_cancelled = []
    
    # Track what was cancelled for the response
    refund_details = []
    
    # 1. Check and cancel Coinflip game
    if user_id in active_coinflip:
        game_data = active_coinflip[user_id]
        bet_amount = game_data.get("bet", 0)
        
        # Refund the bet
        update_balance(user_id, bet_amount)
        refunded += bet_amount
        refund_details.append(f"Coinflip: {format_money(bet_amount)}")
        games_cancelled.append("Coinflip")
        
        # Remove from active games
        del active_coinflip[user_id]
    
    # 2. Check and cancel Flip & Chase game
    if user_id in active_flip_chase:
        game_data = active_flip_chase[user_id]
        bet_amount = game_data.get("bet", 0)
        
        # Refund the bet
        update_balance(user_id, bet_amount)
        refunded += bet_amount
        refund_details.append(f"Flip & Chase: {format_money(bet_amount)}")
        games_cancelled.append("Flip & Chase")
        
        # Remove from active games
        del active_flip_chase[user_id]
    
    # 3. Check and cancel Blackjack game
    if user_id in active_blackjack:
        game = active_blackjack[user_id]
        bet_amount = game.bet
        
        # Refund the bet
        update_balance(user_id, bet_amount)
        refunded += bet_amount
        refund_details.append(f"Blackjack: {format_money(bet_amount)}")
        games_cancelled.append("Blackjack")
        
        # Remove from active games
        del active_blackjack[user_id]
    
    # 4. Check and cancel Lucky Number game
    if user_id in lucky_number_games:
        game_data = lucky_number_games[user_id]
        bet_amount = game_data.get("bet", 0)
        
        # Refund the bet
        update_balance(user_id, bet_amount)
        refunded += bet_amount
        refund_details.append(f"Lucky Number: {format_money(bet_amount)}")
        games_cancelled.append("Lucky Number")
        
        # Remove from active games
        del lucky_number_games[user_id]
    
    # 5. Check and cancel Crash game
    if user_id in crash_games:
        game_data = crash_games[user_id]
        bet_amount = game_data.get("bet", 0)
        
        # Refund the bet
        update_balance(user_id, bet_amount)
        refunded += bet_amount
        refund_details.append(f"Crash: {format_money(bet_amount)}")
        games_cancelled.append("Crash")
        
        # Remove from active games
        del crash_games[user_id]
    
    # 6. Check and cancel Limbo game
    if user_id in limbo_games:
        game_data = limbo_games[user_id]
        bet_amount = game_data.get("bet", 0)
        
        # Refund the bet
        update_balance(user_id, bet_amount)
        refunded += bet_amount
        refund_details.append(f"Limbo: {format_money(bet_amount)}")
        games_cancelled.append("Limbo")
        
        # Remove from active games
        del limbo_games[user_id]
    
    # 7. Check and cancel RPS game (button-based, tracked by view timeout)
    # RPS games are handled by the view timeout, no persistent state to clean
    # But we'll mention it in the response if needed
    
    # 8. Check and cancel Baccarat game
    if user_id in active_baccarat_games:
        # Baccarat games are tracked with current_bet in the view
        # We need to refund if there's an active view
        # Since we can't easily access the view, we'll just remove the tracking
        # The view itself will handle refund on timeout
        games_cancelled.append("Baccarat")
        del active_baccarat_games[user_id]
        # Note: The actual refund happens in the BaccaratView.end_game or timeout
    
    # 9. Check poker games - need to access poker manager
    # Poker manager is set up later, so we need to check if it exists globally
    if 'poker_manager' in globals() and poker_manager:
        # Check all active poker games
        for channel_id, game in list(poker_manager.active_games.items()):
            if user_id in [p.user_id for p in game.players]:
                # Find the player
                player = next((p for p in game.players if p.user_id == user_id), None)
                if player and not player.has_folded:
                    # Refund the player's current bet in the pot
                    if player.chips_in_pot > 0:
                        update_balance(user_id, player.chips_in_pot)
                        refunded += player.chips_in_pot
                        refund_details.append(f"Poker (Channel {channel_id}): {format_money(player.chips_in_pot)}")
                    
                    # Remove player from game
                    game.players.remove(player)
                    games_cancelled.append(f"Poker (Channel {channel_id})")
                    
                    # If game has too few players, end it
                    if len(game.players) < 2:
                        poker_manager.remove_game(channel_id)
    
    # Build response embed
    if games_cancelled:
        embed = discord.Embed(
            title="🔄 Games Reset",
            description=f"{ctx.author.mention}, your active games have been cancelled.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Games Cancelled",
            value="\n".join([f"• {game}" for game in games_cancelled]),
            inline=False
        )
        
        if refunded > 0:
            embed.add_field(
                name="💰 Total Refunded",
                value=format_money(refunded),
                inline=False
            )
            
            if refund_details:
                embed.add_field(
                    name="Refund Breakdown",
                    value="\n".join([f"• {detail}" for detail in refund_details]),
                    inline=False
                )
        
        user_data = get_user(user_id)
        embed.add_field(
            name="New Balance",
            value=format_money(user_data[1]),  # balance is index 1
            inline=False
        )
        
        embed.set_footer(text="Your games have been safely reset • No money glitches!")
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="ℹ️ No Active Games",
            description=f"{ctx.author.mention}, you don't have any active games to cancel.",
            color=discord.Color.light_grey()
        )
        embed.set_footer(text="Use this command when you have stuck or broken games")
        await ctx.send(embed=embed)

# ========================================
# BACCARAT GAME WITH INTERACTIVE BUTTONS
# ========================================

# Track active baccarat games: {user_id: {"bet": amount, "bet_on": "player"/"banker"/"tie"}}
active_baccarat_games = {}

class BaccaratView(discord.ui.View):
    """Interactive view for Baccarat game with chip and control buttons."""
    
    def __init__(self, user_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user_id = user_id
        self.current_bet = 0
        self.bet_on = None
        
    async def on_timeout(self):
        """Handle timeout by canceling the game."""
        if self.user_id in active_baccarat_games:
            # Refund the bet
            user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.user_id)
            set_balance(self.user_id, balance + self.current_bet)
            del active_baccarat_games[self.user_id]
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
    
    # Chip buttons (Row 1)
    @discord.ui.button(label="💵 500K", style=discord.ButtonStyle.success, row=0)
    async def chip_500k(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.add_bet(interaction, 500000)
    
    @discord.ui.button(label="💴 1M", style=discord.ButtonStyle.success, row=0)
    async def chip_1m(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.add_bet(interaction, 1000000)
    
    @discord.ui.button(label="💶 5M", style=discord.ButtonStyle.success, row=0)
    async def chip_5m(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.add_bet(interaction, 5000000)
    
    @discord.ui.button(label="💷 20M", style=discord.ButtonStyle.success, row=0)
    async def chip_20m(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.add_bet(interaction, 20000000)
    
    @discord.ui.button(label="💸 50M", style=discord.ButtonStyle.success, row=0)
    async def chip_50m(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.add_bet(interaction, 50000000)
    
    # Betting position buttons (Row 2)
    @discord.ui.button(label="🎴 Bet Player", style=discord.ButtonStyle.primary, row=1)
    async def bet_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.select_bet_position(interaction, "player")
    
    @discord.ui.button(label="🏦 Bet Banker", style=discord.ButtonStyle.primary, row=1)
    async def bet_banker(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.select_bet_position(interaction, "banker")
    
    @discord.ui.button(label="🤝 Bet Tie", style=discord.ButtonStyle.primary, row=1)
    async def bet_tie(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.select_bet_position(interaction, "tie")
    
    # Control buttons (Row 3)
    @discord.ui.button(label="🃏 Deal", style=discord.ButtonStyle.danger, row=2)
    async def deal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.deal_cards(interaction)
    
    @discord.ui.button(label="❌ End Game", style=discord.ButtonStyle.secondary, row=2)
    async def end_game_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.end_game(interaction)
    
    async def add_bet(self, interaction: discord.Interaction, amount: int):
        """Add chips to the current bet."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return
        
        # Check balance
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.user_id)
        
        if balance < amount:
            await interaction.response.send_message(f"❌ Insufficient balance! You need {amount:,}$ but only have {balance:,}$", ephemeral=True)
            return
        
        # Add to current bet
        self.current_bet += amount
        set_balance(self.user_id, balance - amount)
        
        # Update the embed
        new_balance = balance - amount
        embed = discord.Embed(
            title="🎴 Baccarat Table",
            description=f"**Current Bet:** {self.current_bet:,}$\n**Betting On:** {self.bet_on.title() if self.bet_on else 'Not selected'}\n**Balance:** {new_balance:,}$",
            color=discord.Color.gold()
        )
        embed.add_field(name="💡 Instructions", value=(
            "1️⃣ Add chips to build your bet\n"
            "2️⃣ Choose Player, Banker, or Tie\n"
            "3️⃣ Click Deal to play!\n\n"
            "**Payouts:**\n"
            "• Player: 1:1 (2x)\n"
            "• Banker: 0.95:1 (1.95x)\n"
            "• Tie: 8:1 (9x)"
        ), inline=False)
        embed.set_footer(text="🔐 Provably Fair • Use !verify to check")
        
        await interaction.response.edit_message(embed=embed)
    
    async def select_bet_position(self, interaction: discord.Interaction, position: str):
        """Select where to bet: player, banker, or tie."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return
        
        if self.current_bet == 0:
            await interaction.response.send_message("❌ Add chips first before choosing where to bet!", ephemeral=True)
            return
        
        self.bet_on = position
        
        # Get current balance
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.user_id)
        
        # Update the embed
        embed = discord.Embed(
            title="🎴 Baccarat Table",
            description=f"**Current Bet:** {self.current_bet:,}$\n**Betting On:** {position.title()}\n**Balance:** {balance:,}$",
            color=discord.Color.gold()
        )
        embed.add_field(name="✅ Bet Placed!", value=(
            f"You're betting {self.current_bet:,}$ on **{position.title()}**\n\n"
            "**Payouts:**\n"
            f"• {'✅' if position == 'player' else '⚪'} Player: 1:1 (2x)\n"
            f"• {'✅' if position == 'banker' else '⚪'} Banker: 0.95:1 (1.95x)\n"
            f"• {'✅' if position == 'tie' else '⚪'} Tie: 8:1 (9x)\n\n"
            "Click **Deal** when ready!"
        ), inline=False)
        embed.set_footer(text="🔐 Provably Fair • Use !verify to check")
        
        await interaction.response.edit_message(embed=embed)
    
    async def deal_cards(self, interaction: discord.Interaction):
        """Deal the cards and determine winner."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return
        
        if self.current_bet == 0:
            await interaction.response.send_message("❌ Add chips first!", ephemeral=True)
            return
        
        if not self.bet_on:
            await interaction.response.send_message("❌ Choose where to bet first (Player, Banker, or Tie)!", ephemeral=True)
            return
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        # Track gamble
        add_gambled(self.user_id, self.current_bet)
        
        # Use provably fair to generate 6 cards (3 for player, 3 for banker)
        # Modulo 13 for card values (1-13, where 10-13 are face cards = 0 points)
        results, client_seed, nonce, seed_hash = provably_fair.place_bet_multiple(
            self.user_id, "baccarat", self.current_bet, count=6, modulo=13
        )
        
        # Convert results to card values (1-13 -> actual baccarat values)
        def card_value(result):
            val = (result % 13) + 1
            if val >= 10:  # 10, J, Q, K = 0
                return 0
            return val
        
        player_cards = [card_value(results[0]), card_value(results[1])]
        banker_cards = [card_value(results[2]), card_value(results[3])]
        
        # Calculate initial totals
        player_total = (player_cards[0] + player_cards[1]) % 10
        banker_total = (banker_cards[0] + banker_cards[1]) % 10
        
        # Track if third card was drawn
        player_drew_third = False
        banker_drew_third = False
        
        # Baccarat third card rules
        if player_total <= 5 and banker_total <= 7:
            # Player draws third card
            player_cards.append(card_value(results[4]))
            player_total = (player_cards[0] + player_cards[1] + player_cards[2]) % 10
            player_drew_third = True
            
            # Banker draws based on complex rules
            player_third = player_cards[2]
            if banker_total <= 2:
                banker_cards.append(card_value(results[5]))
                banker_drew_third = True
            elif banker_total == 3 and player_third != 8:
                banker_cards.append(card_value(results[5]))
                banker_drew_third = True
            elif banker_total == 4 and player_third in [2,3,4,5,6,7]:
                banker_cards.append(card_value(results[5]))
                banker_drew_third = True
            elif banker_total == 5 and player_third in [4,5,6,7]:
                banker_cards.append(card_value(results[5]))
                banker_drew_third = True
            elif banker_total == 6 and player_third in [6,7]:
                banker_cards.append(card_value(results[5]))
                banker_drew_third = True
                
            if banker_drew_third:
                banker_total = sum(banker_cards) % 10
        elif banker_total <= 5:
            # Only banker draws
            banker_cards.append(card_value(results[5]))
            banker_total = sum(banker_cards) % 10
            banker_drew_third = True
        
        # Determine winner
        if player_total > banker_total:
            winner = "player"
        elif banker_total > player_total:
            winner = "banker"
        else:
            winner = "tie"
        
        # Calculate payout
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.user_id)
        
        if self.bet_on == winner:
            if winner == "player":
                payout = self.current_bet * 2  # 1:1
                profit = self.current_bet
            elif winner == "banker":
                payout = int(self.current_bet * 1.95)  # 0.95:1 (5% commission)
                profit = payout - self.current_bet
            else:  # tie
                payout = self.current_bet * 9  # 8:1
                profit = self.current_bet * 8
            
            set_balance(self.user_id, balance + payout)
            result_text = f"🎉 **YOU WIN!**\n\nPayout: {payout:,}$\nProfit: +{profit:,}$"
            color = discord.Color.green()
        elif winner == "tie" and self.bet_on != "tie":
            # Tie returns bets to player and banker
            set_balance(self.user_id, balance + self.current_bet)
            result_text = f"🤝 **TIE - BET RETURNED**\n\nYour {self.current_bet:,}$ bet has been returned."
            color = discord.Color.light_grey()
            profit = 0
        else:
            result_text = f"❌ **YOU LOSE**\n\nLoss: -{self.current_bet:,}$"
            color = discord.Color.red()
            profit = -self.current_bet
        
        # Get final balance
        _, final_balance, _, _, _, _, _ = get_user(self.user_id)
        
        # Create result embed
        embed = discord.Embed(
            title="🎴 Baccarat Result",
            description=result_text,
            color=color
        )
        
        # Display cards
        player_cards_str = " + ".join([f"**{c}**" for c in player_cards])
        banker_cards_str = " + ".join([f"**{c}**" for c in banker_cards])
        
        embed.add_field(
            name="🎴 Player Hand",
            value=f"{player_cards_str}\nTotal: **{player_total}**",
            inline=True
        )
        embed.add_field(
            name="🏦 Banker Hand",
            value=f"{banker_cards_str}\nTotal: **{banker_total}**",
            inline=True
        )
        embed.add_field(
            name="📊 Game Summary",
            value=(
                f"**Your Bet:** {self.current_bet:,}$ on {self.bet_on.title()}\n"
                f"**Winner:** {winner.title()}\n"
                f"**New Balance:** {final_balance:,}$"
            ),
            inline=False
        )
        
        # Add provably fair info
        embed.add_field(
            name="🔐 Provably Fair",
            value=(
                f"Nonce: {nonce} | Client: {client_seed[:8]}...\n"
                f"Seed Hash: {seed_hash[:16]}...\n"
                f"Use !verify to verify fairness"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Net: {'+' if profit >= 0 else ''}{profit:,}$ • Provably Fair Baccarat")
        
        # Remove from active games
        if self.user_id in active_baccarat_games:
            del active_baccarat_games[self.user_id]
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def end_game(self, interaction: discord.Interaction):
        """End the game and refund any bet."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return
        
        # Refund the bet if any
        if self.current_bet > 0:
            user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(self.user_id)
            set_balance(self.user_id, balance + self.current_bet)
        
        # Remove from active games
        if self.user_id in active_baccarat_games:
            del active_baccarat_games[self.user_id]
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        embed = discord.Embed(
            title="❌ Game Ended",
            description=f"Baccarat game cancelled. Your bet of {self.current_bet:,}$ has been refunded.",
            color=discord.Color.light_grey()
        )
        
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command(name="baccarat")
async def baccarat(ctx):
    """Start a Baccarat game with interactive chip buttons."""
    try:
        # Check if user already has an active game
        if ctx.author.id in active_baccarat_games:
            await ctx.send("❌ You already have an active Baccarat game! Use the 'End Game' button or !resetgames to cancel it.")
            return
        
        # Get user data
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn, favorite_game = get_user(ctx.author.id)
        
        # Create the initial embed
        embed = discord.Embed(
            title="🎴 Baccarat Table",
            description=f"**Current Bet:** 0$\n**Betting On:** Not selected\n**Balance:** {balance:,}$",
            color=discord.Color.gold()
        )
        embed.add_field(name="🎮 How to Play", value=(
            "**Step 1:** Click chip buttons to add to your bet\n"
            "**Step 2:** Choose Player, Banker, or Tie\n"
            "**Step 3:** Click Deal to play!\n\n"
            "**Objective:** Get closest to 9 points\n"
            "**Card Values:**\n"
            "• Ace = 1 point\n"
            "• 2-9 = Face value\n"
            "• 10, J, Q, K = 0 points\n"
            "• Total is last digit (e.g., 15 = 5)"
        ), inline=False)
        embed.add_field(name="💰 Payouts", value=(
            "• **Player:** 1:1 (2x your bet)\n"
            "• **Banker:** 0.95:1 (1.95x - 5% commission)\n"
            "• **Tie:** 8:1 (9x your bet)\n"
            "• Tie also returns Player/Banker bets"
        ), inline=False)
        embed.set_footer(text="🔐 Provably Fair • Use !verify to check your game")
        
        # Create view with buttons
        view = BaccaratView(ctx.author.id)
        
        # Track active game
        active_baccarat_games[ctx.author.id] = {"bet": 0, "bet_on": None}
        
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"❌ Error starting Baccarat: {str(e)}")
        if ctx.author.id in active_baccarat_games:
            del active_baccarat_games[ctx.author.id]

# -----------------------------
# POKER GAME SETUP
# -----------------------------
from poker_commands import setup_poker_commands
poker_manager = setup_poker_commands(bot, parse_money, get_user, update_balance, add_gambled)

# -----------------------------
# RUN BOT
# -----------------------------
# Get bot token from environment variable or use placeholder
bot_token = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
if bot_token == "YOUR_BOT_TOKEN_HERE":
    print("⚠️ WARNING: Using placeholder bot token. Set DISCORD_BOT_TOKEN environment variable.")
bot.run(bot_token)

