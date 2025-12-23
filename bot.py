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
OWNER_IDS = [1182265710248996874, 1249352131870195744]
TICKET_CATEGORY_ID = 1442410056019742750
TRANSCRIPT_CHANNEL_ID = 1442288590611681401
WITHDRAWAL_LOG_CHANNEL = 1450656547402285167
AUDIT_LOG_CHANNEL = 1451387246061293662  # Channel for fraud detection and activity logs
DEPOSIT_STATS_CHANNEL = 1452401825994248212  # Channel for 15-minute deposit statistics
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
    
    conn.commit()
except Exception as e:
    print(f"⚠️ Database migration error (non-fatal): {e}")

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

def update_balance(user_id, amount):
    """Update user balance by adding amount. Validates inputs."""
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid amount: {amount}")
    
    user_id_db, bal, req, gambled, total_gambled, total_withdrawn = get_user(user_id)
    new_bal = bal + amount
    new_req = int(new_bal * GAMBLE_PERCENT)
    c.execute(
        "UPDATE users SET balance=?, required_gamble=? WHERE user_id=?",
        (new_bal, new_req, user_id_db)
    )
    conn.commit()

def add_gambled(user_id, amount):
    """Add gambled amount to user's gamble stats. Validates inputs."""
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid amount: {amount}")
    
    user_id_db, bal, req, gambled, total_gambled, total_withdrawn = get_user(user_id)
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
    
    user_id_db, bal, req, gambled, total_gambled, total_withdrawn = get_user(user_id)
    new_bal = bal - amount
    new_req = int(new_bal * GAMBLE_PERCENT)
    new_total_withdrawn = total_withdrawn + amount
    c.execute(
        "UPDATE users SET balance=?, required_gamble=?, gambled=0, total_withdrawn=? WHERE user_id=?",
        (new_bal, new_req, new_total_withdrawn, user_id_db)
    )
    conn.commit()

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
            user_id, bal_before, req, gambled, total_gambled, total_withdrawn = get_user(self.user.id)
            
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
            user_id, bal, req, gambled, _, _ = get_user(interaction.user.id)
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
        "**!donate @user [amount]** - Donate balance to another player\n"
        "**!withdraw** - Request a full withdrawal (requires owner approval)\n"
        "**!leaderboards** (or **!lb**) - View the top 10 players leaderboard\n"
        "**!games** - View all gambling game rules and info"
    ), inline=False)
    embed.add_field(name="🎮 Solo Gambling Games", value=(
        "**!cf [amount] [heads/tails]** - Simple coinflip! Bet on heads or tails\n"
        "**!flipchase [amount]** - Flip & Chase: Double or nothing progressive game\n"
        "**!slots [amount]** - Play the slot machine (3x3 grid)\n"
        "**!luckynumber [amount] [1-5000]** - Start lucky number game\n"
        "**!pick [number]** - Pick your lucky number\n"
        "**!crash [amount]** - Play crash game (cash out before it crashes!)\n"
        "**!blackjack [amount]** - Play Blackjack! Beat the dealer without going over 21\n"
        "**!limbo [amount]** - Play Limbo! Above or below 50?"
    ), inline=False)
    embed.add_field(name="⚔️ PvP Games", value=(
        "**!fight @user [amount]** - Challenge a player to a gladiator duel!\n"
        "**!pickgladiator [name]** - Pick your gladiator for fights\n"
        "**!choptree @user [amount]** - Challenge a player to risky lumberjack!\n"
        "**!chop** - Take your turn chopping the tree\n"
        "**!wordchain @user [amount]** - Challenge a player to word chain!\n"
        "**!word [your_word]** - Play your word in the chain"
    ), inline=False)
    if is_owner(ctx.author):
        embed.add_field(name="🔐 Owner Commands", value=(
            "**!ticketpanel** - Send deposit ticket panel\n"
            "**!withdrawalpanel** - Send withdrawal ticket panel\n"
            "**!ticketclose [reason]** - Close a ticket with optional reason\n"
            "**!deposit @user amount** - Add gambling amount to a user\n"
            "**!viewamount @user** - View a user's balance\n"
            "**!amountall [page]** - View all users balances\n"
            "**!gambledall** - View total gambling statistics across all players\n"
            "**!resetgamblingall** - Reset all gambling statistics (total_gambled & gambled)\n"
            "**!wipeamount @user** - Wipe a user's balance\n"
            "**!stick [message]** - Create a sticky message at the bottom of the channel\n"
            "**!unstick** - Remove the sticky message from the current channel"
        ), inline=False)
    await ctx.send(embed=embed)

@bot.command(name="amount")
async def amount(ctx):
    """Display user's balance and gamble requirements."""
    try:
        user_id, bal, req, gambled, _, _ = get_user(ctx.author.id)
        remaining = max(req - gambled, 0)
        await ctx.send(f"💰 **Your Gambling Amount**\nBalance: `{bal:,}$`\nRequired Gamble: `{req:,}$`\nRemaining: `{remaining:,}$`")
    except Exception as e:
        await ctx.send(f"❌ Error fetching your balance: {str(e)}")

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
    
    try:
        # Parse donation amount
        value = parse_money(amount)
        
        # Minimum donation amount
        if value < 1000000:  # 1M minimum
            await ctx.send("❌ Minimum donation amount is 1,000,000$")
            return
        
        # Get donor's balance
        donor_id, donor_bal, donor_req, donor_gambled, _, _ = get_user(ctx.author.id)
        
        # Check if donor has enough balance
        if donor_bal < value:
            await ctx.send(f"❌ Insufficient balance! You have {donor_bal:,}$ but tried to donate {value:,}$")
            return
        
        # Get recipient's info
        recipient_id, recipient_bal, recipient_req, recipient_gambled, _, _ = get_user(user.id)
        
        # Perform the transaction
        # Deduct from donor
        update_balance(ctx.author.id, -value)
        
        # Add to recipient
        update_balance(user.id, value)
        
        # Get updated balances
        _, donor_new_bal, _, _, _, _ = get_user(ctx.author.id)
        _, recipient_new_bal, _, _, _, _ = get_user(user.id)
        
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
        embed.set_footer(text="Thank you for your generosity!")
        
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
        user_id, bal, req, gambled, _, _ = get_user(ctx.author.id)
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
        super().__init__(timeout=60)
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
            # Perform the flip
            outcome = random.choice(["heads", "tails"])
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
        super().__init__(timeout=60)
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
        
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(ctx.author.id)
        
        if value > balance:
            await ctx.send("❌ You cannot gamble more than your balance.")
            return
        
        # Minimum bet
        if value < 1000000:  # 1M minimum
            await ctx.send("❌ Minimum bet is 1,000,000$!")
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

class FlipChaseView(View):
    def __init__(self, user_id, current_winnings, initial_bet, rounds_won):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.current_winnings = current_winnings
        self.initial_bet = initial_bet
        self.rounds_won = rounds_won
        
    @discord.ui.button(label="🎲 Chase (Double or Nothing)", style=discord.ButtonStyle.green)
    async def chase_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        # Flip the coin
        outcome = random.choice(["heads", "tails"])
        player_choice = random.choice(["heads", "tails"])
        won = player_choice == outcome
        
        if won:
            # Double winnings and offer to chase again
            self.current_winnings *= 2
            self.rounds_won += 1
            
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
            embed = discord.Embed(
                title="💀 Chase Failed!",
                description=f"**You lost!** The coin landed on **{outcome}**.\nYou lost all your winnings!",
                color=discord.Color.red()
            )
            embed.add_field(name="Lost Winnings", value=f"{format_money(self.current_winnings)}", inline=True)
            embed.add_field(name="Rounds Won", value=f"{self.rounds_won}", inline=True)
            embed.add_field(name="Initial Bet", value=f"{format_money(self.initial_bet)}", inline=True)
            
            # Update database - user loses everything (already deducted initial bet)
            user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(self.user_id)
            
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
        
        # Get user data
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(self.user_id)
        
        # Add winnings to balance
        profit = self.current_winnings - self.initial_bet
        balance += self.current_winnings
        gambled += self.initial_bet
        total_gambled += self.initial_bet
        
        # Update database
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

        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(ctx.author.id)

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
        
        # First flip to start the game
        outcome = random.choice(["heads", "tails"])
        player_choice = random.choice(["heads", "tails"])
        won = player_choice == outcome
        
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
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.ctx = ctx
        self.spun = False
    
    async def perform_spin(self, interaction: discord.Interaction):
        """Perform the slot machine spin logic."""
        try:
            # Slot symbols with weights for balanced gameplay
            symbols = ["🍒", "🍋", "🍊", "🍇", "💎", "⭐", "7️⃣"]
            
            # Generate 3x3 grid
            grid = [[random.choice(symbols) for _ in range(3)] for _ in range(3)]
            
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
            embed.set_footer(text=f"Click 'Spin Again' to play another round with the same bet!")
            
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
        
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(ctx.author.id)
        
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
        user_id, bal_before, req, gambled, _, _ = get_user(user.id)
        
        # Update balance
        update_balance(user.id, value)
        user_id, bal, req, gambled, _, _ = get_user(user.id)
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
        user_id, bal, req, gambled, _, _ = get_user(user.id)
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

@bot.command(name="ticketclose")
async def ticketclose(ctx, *, reason: str = "No reason provided."):
    """Close a ticket with an optional reason. Only usable by owners in ticket channels."""
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can close tickets.")
        return
    
    try:
        # Get ticket metadata from database
        c.execute("SELECT user_id, panel_name, ticket_name, open_date FROM ticket_metadata WHERE channel_id=?", (ctx.channel.id,))
        ticket_data = c.fetchone()
        
        if not ticket_data:
            await ctx.send("❌ This command can only be used in ticket channels.")
            return
        
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
    """Calculate fair multiplier based on risk (odds of winning)."""
    if max_range <= 10:
        return 8.0  # 1/10 = 10% chance → 8x return (80% RTP, house edge 20%)
    elif max_range <= 50:
        return 40.0  # 1/50 = 2% chance → 40x return (80% RTP)
    elif max_range <= 100:
        return 80.0  # 1/100 = 1% chance → 80x return (80% RTP)
    elif max_range <= 500:
        return 400.0  # 1/500 = 0.2% chance → 400x return (80% RTP)
    elif max_range <= 1000:
        return 800.0  # 1/1000 = 0.1% chance → 800x return (80% RTP)
    elif max_range <= 2500:
        return 2000.0  # 1/2500 = 0.04% chance → 2000x return (80% RTP)
    elif max_range <= 5000:
        return 4000.0  # 1/5000 = 0.02% chance → 4000x return (80% RTP)
    else:
        return 4000.0  # Cap at 5000

@bot.command(name="luckynumber")
async def luckynumber(ctx, amount: str = None, max_number: str = None):
    """
    Start a lucky number game - guess the lucky number to win big!
    
    Usage: !luckynumber <amount> <max_number>
    Example: !luckynumber 10m 100
    
    After starting, use !pick <your_number> to make your guess.
    
    Risk levels:
    - 1-10: Low risk, 8x multiplier
    - 1-50: Medium risk, 40x multiplier
    - 1-100: High risk, 80x multiplier
    - 1-500: Very high risk, 400x multiplier
    - 1-1000: Extreme risk, 800x multiplier
    - 1-2500: Ultra risk, 2000x multiplier
    - 1-5000: Maximum risk, 4000x multiplier
    """
    try:
        if amount is None or max_number is None:
            await ctx.send("❌ Usage: `!luckynumber <amount> <1-5000>`\nExample: `!luckynumber 10m 100`")
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

        if max_num < 10 or max_num > 5000:
            await ctx.send("❌ Number range must be between 10-5000! Minimum is 10.")
            return

        # Get user data
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(ctx.author.id)

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

        # Generate lucky number
        lucky_num = random.randint(1, max_num)
        multiplier = calculate_lucky_number_multiplier(max_num)
        
        # Store game state
        lucky_number_games[ctx.author.id] = {
            "bet": value,
            "range": max_num,
            "lucky_num": lucky_num,
            "timestamp": datetime.now(),
            "multiplier": multiplier
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
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(ctx.author.id)
        
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
        super().__init__(timeout=120)  # 2 minute timeout
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
                    
                    # Update to crash embed
                    embed = discord.Embed(
                        title="💥 CRASH!",
                        description=f"The multiplier crashed at **{self.crash_point}x**!",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="💸 Final Multiplier", value=f"**{self.crash_point}x**", inline=True)
                    embed.add_field(name="💔 You Lost", value=f"{self.bet_amount:,}$", inline=True)
                    embed.add_field(name="🎲 Result", value="**CRASHED**", inline=True)
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
                if self.current_multiplier < 2.0:
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
        
        # Minimum cashout multiplier is 2.0x to make the game much harder
        if self.current_multiplier < 2.0:
            await interaction.response.send_message(
                f"❌ Minimum cashout is **2.0x**! Current: **{self.current_multiplier}x**\n"
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
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(ctx.author.id)
        
        # Check balance
        if value > balance:
            await ctx.send(f"❌ Insufficient balance! You have {balance:,}$ but need {value:,}$")
            return
        
        # Generate random crash point with MUCH higher house edge
        # Heavily weighted toward early crashes - much harder to win
        import random
        rand = random.random()
        
        if rand < 0.55:
            # 55% chance: crash between 1.15x and 1.5x (very early crash)
            crash_point = round(random.uniform(1.15, 1.5), 2)
        elif rand < 0.78:
            # 23% chance: crash between 1.5x and 2.0x
            crash_point = round(random.uniform(1.5, 2.0), 2)
        elif rand < 0.90:
            # 12% chance: crash between 2.0x and 3.0x
            crash_point = round(random.uniform(2.0, 3.0), 2)
        elif rand < 0.97:
            # 7% chance: crash between 3.0x and 5.0x
            crash_point = round(random.uniform(3.0, 5.0), 2)
        else:
            # 3% chance: crash between 5.0x and 10.0x (rare)
            crash_point = round(random.uniform(5.0, 10.0), 2)
        
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
            "message": message
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
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(self.opponent_id)
        
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
        self.deck = self.create_deck()
        random.shuffle(self.deck)
        self.player_hand = []
        self.dealer_hand = []
        self.game_over = False
        self.player_stood = False
        
    def create_deck(self):
        """Create a standard 52-card deck (can use multiple decks)"""
        suits = ['♠️', '♥️', '♣️', '♦️']
        ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        deck = []
        # Use 2 decks for more randomness
        for _ in range(2):
            for suit in suits:
                for rank in ranks:
                    deck.append(f"{rank}{suit}")
        return deck
    
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
            self.deck = self.create_deck()
            random.shuffle(self.deck)
        return self.deck.pop()
    
    def format_hand(self, hand, hide_first=False):
        """Format hand for display"""
        if hide_first:
            return f"🎴 {' '.join(hand[1:])} (? + {self.hand_value(hand[1:])})"
        return f"🎴 {' '.join(hand)} ({self.hand_value(hand)})"

class BlackjackView(View):
    """Interactive buttons for Blackjack game"""
    def __init__(self, game):
        super().__init__(timeout=120)
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
            
            embed.set_footer(text="Play again with !blackjack <amount>")
            
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
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(self.game.user_id)
        
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
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(self.game.user_id)
        
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
        
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(ctx.author.id)
        
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
        user_id, balance, required_gamble, gambled, total_gambled, total_withdrawn = get_user(ctx.author.id)
        
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
            value="Take turns using `!chop` to cut sections of the tree. The player who makes the tree fall loses!",
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
            "channel_id": interaction.channel.id
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
            
            # Generate random number between 1-100
            roll = random.randint(1, 100)
            
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
        
        # Page 1: Coinflip
        embed0 = discord.Embed(
            title="🪙 Coinflip",
            description="**Simple heads or tails - Classic coinflip betting!**",
            color=discord.Color.gold()
        )
        embed0.add_field(
            name="📋 Command",
            value="`!cf <amount> <heads/tails>`",
            inline=False
        )
        embed0.add_field(
            name="💡 Example",
            value="`!cf 200m heads`",
            inline=False
        )
        embed0.add_field(
            name="🎮 How to Play",
            value="1. Bet an amount and choose heads or tails\n2. Click **Start CF** to flip the coin\n3. Win if the coin lands on your choice!\n4. Click **Flip Again** to replay with same bet and choice",
            inline=False
        )
        embed0.add_field(
            name="💰 Payout",
            value="**Win**: 1.95x your bet (5% house edge)",
            inline=True
        )
        embed0.add_field(
            name="🎯 Win Chance",
            value="**50%** - Fair odds!",
            inline=True
        )
        embed0.add_field(
            name="✨ Features",
            value="• **Start CF** button to begin\n• **Flip Again** button to replay with same side\n• Simple, fast gameplay\n• Fair 50/50 odds",
            inline=False
        )
        embed0.add_field(
            name="⚠️ Note",
            value="Using the flip again button will use the same side of the coin you originally picked!",
            inline=False
        )
        embed0.set_footer(text="Page 1/11 • Use the buttons below to see other games")
        pages.append(embed0)
        
        # Page 2: Flip & Chase
        embed1 = discord.Embed(
            title="🎲 Flip & Chase",
            description="**Progressive double-or-nothing game - Chase for bigger wins or bank anytime!**",
            color=discord.Color.gold()
        )
        embed1.add_field(
            name="📋 Command",
            value="`!flipchase <amount>`",
            inline=False
        )
        embed1.add_field(
            name="💡 Example",
            value="`!flipchase 10m`",
            inline=False
        )
        embed1.add_field(
            name="🎮 How to Play",
            value="1. Bet an amount to start\n2. Win the first flip to start chasing\n3. **Chase**: Double your winnings (risk losing all)\n4. **Bank**: Keep your current winnings safe\n5. Lose any flip = lose everything!",
            inline=False
        )
        embed1.add_field(
            name="💰 Multipliers",
            value="**Round 1**: 2x\n**Round 2**: 4x\n**Round 3**: 8x\n**Round 4**: 16x\n**And so on...**",
            inline=True
        )
        embed1.add_field(
            name="🎯 Strategy",
            value="Balance risk vs reward!\nBank early for safe profit\nor chase for massive wins!",
            inline=True
        )
        embed1.add_field(
            name="⚠️ Warning",
            value="Losing ANY round means you lose ALL winnings! Bank wisely.",
            inline=False
        )
        embed1.set_footer(text="Page 2/11 • Use the buttons below to see other games")
        pages.append(embed1)
        
        # Page 2: Slots
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
        embed2.set_footer(text="Page 3/11 • Use the buttons below to see other games")
        pages.append(embed2)
        
        # Page 3: Lucky Number
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
        embed3.set_footer(text="Page 4/11 • Use the buttons below to see other games")
        pages.append(embed3)
        
        # Page 4: Crash
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
            value="Bet amount × multiplier when you cash out (minimum 2.0x)",
            inline=False
        )
        embed4.add_field(
            name="✨ Features",
            value=(
                "• Multiplier starts at **1.0x**\n"
                "• Minimum cashout: **2.0x** (game is very hard!)\n"
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
        embed4.set_footer(text="Page 5/11 • Use the buttons below to see other games")
        pages.append(embed4)
        
        # Page 5: Blackjack
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
        embed5.set_footer(text="Page 6/11 • Use the buttons below to see other games")
        pages.append(embed5)
        
        # Page 6: Gladiator Fights
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
        embed6.set_footer(text="Page 7/11 • Use the buttons below to see other games")
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
        embed7.set_footer(text="Page 8/11 • Use the buttons below to see other games")
        pages.append(embed7)
        
        # Page 8: Word Chain
        embed8 = discord.Embed(
            title="🔤 Word Chain",
            description="**Turn-based word game - Chain words by matching letters!**",
            color=discord.Color.blue()
        )
        embed8.add_field(
            name="📋 Commands",
            value="`!wordchain @user <amount>` - Start game\n`!word <your_word>` - Play word",
            inline=False
        )
        embed8.add_field(
            name="💡 Example",
            value="`!wordchain @John 25m`\n`!word elephant`",
            inline=False
        )
        embed8.add_field(
            name="🎮 How to Play",
            value="1. Challenge an opponent with `!wordchain`\n2. Opponent must accept\n3. Take turns with `!word <word>`\n4. Each word must start with the last letter of the previous word\n5. **30 seconds per turn** - timeout = loss!\n6. No repeating words!",
            inline=False
        )
        embed8.add_field(
            name="📝 Example Chain",
            value="Apple → Elephant → Tiger → Raccoon → Nest",
            inline=False
        )
        embed8.add_field(
            name="💰 Winner Takes All",
            value="First player to repeat a word, timeout, or give invalid word loses. Winner gets 2x the bet!",
            inline=False
        )
        embed8.add_field(
            name="⚠️ Important",
            value="• Only letters allowed in words\n• 30-second time limit per turn\n• Play must continue in the same channel\n• Case doesn't matter",
            inline=False
        )
        embed8.set_footer(text="Page 9/11 • Use the buttons below to see other games")
        pages.append(embed8)
        
        # Page 9: Limbo
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
        embed9.set_footer(text="Page 10/11 • Use the buttons below to see other games")
        pages.append(embed9)
        
        # Page 10: General Rules
        embed10 = discord.Embed(
            title="📋 General Rules",
            description="**Important information about the gambling system**",
            color=discord.Color.red()
        )
        embed10.add_field(
            name="💵 Deposit Requirement",
            value="Minimum **10M** deposit required",
            inline=False
        )
        embed10.add_field(
            name="🎲 Gambling Requirement",
            value="Must gamble **30%** of your balance before withdrawing",
            inline=False
        )
        embed10.add_field(
            name="⚡ Balance Updates",
            value="All wins/losses update your balance instantly",
            inline=False
        )
        embed10.add_field(
            name="🛡️ Fraud Detection",
            value="Rapid betting and high-value bets are monitored",
            inline=False
        )
        embed10.add_field(
            name="💸 Withdrawals",
            value="Use `!withdraw` when you meet the gambling requirement",
            inline=False
        )
        embed10.add_field(
            name="ℹ️ More Commands",
            value="Use `!assist` to see all available commands",
            inline=False
        )
        embed10.set_footer(text="Page 11/11 • Use the buttons below to see other games")
        pages.append(embed10)
        
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
# BOT READY
# -----------------------------
@bot.event
async def on_ready():
    """Bot ready event handler."""
    print(f"✅ Logged in as {bot.user}")
    # Register persistent views
    bot.add_view(TicketPanelView())
    bot.add_view(WithdrawalPanelView())
    print("✅ Persistent views registered")
    
    # Start deposit statistics task if not already running
    if not post_deposit_stats.is_running():
        post_deposit_stats.start()
        print("✅ Deposit statistics task started")

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
# RUN BOT
# -----------------------------
# Get bot token from environment variable or use placeholder
bot_token = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
if bot_token == "YOUR_BOT_TOKEN_HERE":
    print("⚠️ WARNING: Using placeholder bot token. Set DISCORD_BOT_TOKEN environment variable.")
bot.run(bot_token)

