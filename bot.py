import discord
from discord.ext import commands
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

            await channel.send(
                content=" ".join(f"<@&{r}>" for r in PING_ROLES),
                embed=discord.Embed(
                    title="💰 Deposit Ticket",
                    description=f"{user.mention}, thank you for opening a deposit ticket inside **Eli's MM!**",
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
    await ctx.send(embed=discord.Embed(
        title="💰 Deposit Brainrots",
        description=(
            "**Exchange Rate:** 1$/s brainrot = 1$\n"
            f"**Minimum Deposit:** {MIN_DEPOSIT:,}$\n"
            "Click the button below to open a deposit ticket."
        ),
        color=discord.Color.orange()
    ), view=TicketPanelView())

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
    embed.add_field(name="👤 Member Commands", value=(
        "**!amount** - View your balance and remaining required gamble\n"
        "**!withdraw** - Request a full withdrawal (requires owner approval)\n"
        "**!coinflip [amount] [heads/tails]** - Gamble a coinflip\n"
        "**!slots [amount]** - Play the slot machine (3x3 grid)\n"
        "**!luckynumber [amount] [1-5000]** - Start lucky number game\n"
        "**!pick [number]** - Pick your lucky number\n"
        "**!crash [amount]** - Play crash game (cash out before it crashes!)\n"
        "**!rules** - View all gambling game rules and info"
    ))
    if is_owner(ctx.author):
        embed.add_field(name="🔐 Owner Commands", value=(
            "**!ticketpanel** - Send deposit ticket panel\n"
            "**!withdrawalpanel** - Send withdrawal ticket panel\n"
            "**!ticketclose [reason]** - Close a ticket with optional reason\n"
            "**!deposit @user amount** - Add gambling amount to a user\n"
            "**!viewamount @user** - View a user's balance\n"
            "**!amountall [page]** - View all users balances\n"
            "**!wipeamount @user** - Wipe a user's balance\n"
            "**!stick [message]** - Create a sticky message at the bottom of the channel\n"
            "**!unstick** - Remove the sticky message from the current channel"
        ))
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
# ✅ FIXED COINFLIP COMMAND
# -----------------------------
@bot.command(name="coinflip")
async def coinflip(ctx, amount: str = None, choice: str = None):
    """Coinflip gambling command with proper error handling."""
    try:
        if amount is None or choice is None:
            await ctx.send("❌ Usage: `!coinflip <amount> <heads/tails>`")
            return

        choice = choice.lower().strip()
        if choice not in ("heads", "tails"):
            await ctx.send("❌ You must choose **heads** or **tails**.")
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
                f"User placed {RAPID_BET_THRESHOLD}+ bets in 60 seconds\nBet Amount: {value:,}$\nGame: Coinflip"
            )
        
        # Check for high bet (fraud detection)
        if value >= HIGH_BET_THRESHOLD:
            await log_user_activity(
                bot,
                ctx.author,
                "High Value Bet",
                f"Amount: {value:,}$\nGame: Coinflip\nChoice: {choice}\nBalance: {balance:,}$"
            )

        outcome = random.choice(["heads", "tails"])
        won = choice == outcome

        if won:
            balance += value
            result_msg = f"🎉 You won the coinflip! Your balance increased by {value:,}$."
        else:
            balance -= value
            result_msg = f"💀 You lost the coinflip! Your balance decreased by {value:,}$."

        # Increase gambled amount - this reduces the remaining requirement
        gambled += value
        total_gambled += value
        # Do NOT recalculate required_gamble - it stays the same until withdrawal

        c.execute(
            "UPDATE users SET balance=?, gambled=?, total_gambled=? WHERE user_id=?",
            (balance, gambled, total_gambled, ctx.author.id)
        )
        conn.commit()
        
        # Log bet activity
        await log_bet_activity(ctx.author.id, value, "coinflip", "win" if won else "loss")

        remaining = max(required_gamble - gambled, 0)

        embed = discord.Embed(title="🎰 Coinflip Result", description=result_msg, color=discord.Color.gold())
        embed.add_field(name="Balance", value=f"{balance:,}$")
        embed.add_field(name="Required Gamble", value=f"{required_gamble:,}$")
        embed.add_field(name="Remaining", value=f"{remaining:,}$")
        embed.add_field(name="Outcome", value=f"The coin landed on **{outcome}**")

        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error during coinflip: {str(e)}")

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

        if max_num < 1 or max_num > 5000:
            await ctx.send("❌ Number range must be between 1-5000!")
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
        self.current_multiplier = 1.0
        self.cashed_out = False
        self.crashed = False
        self.task = None
    
    async def start_crash_animation(self, message):
        """Animate the multiplier increasing until crash."""
        try:
            while not self.cashed_out and not self.crashed:
                # Increase multiplier
                self.current_multiplier += 0.1
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
                
                # Wait before next update (gets faster as multiplier increases)
                wait_time = max(0.8, 1.8 - (self.current_multiplier - 1.0) * 0.05)
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
        
        # Generate random crash point (weighted towards lower values for house edge)
        # Using exponential distribution for realistic crash game odds
        import random
        rand = random.random()
        
        if rand < 0.33:
            # 33% chance: crash between 1.1x and 2.0x
            crash_point = round(random.uniform(1.1, 2.0), 2)
        elif rand < 0.66:
            # 33% chance: crash between 2.0x and 5.0x
            crash_point = round(random.uniform(2.0, 5.0), 2)
        elif rand < 0.90:
            # 24% chance: crash between 5.0x and 10.0x
            crash_point = round(random.uniform(5.0, 10.0), 2)
        else:
            # 10% chance: crash between 10.0x and 50.0x (rare high multipliers)
            crash_point = round(random.uniform(10.0, 50.0), 2)
        
        # Create initial embed
        embed = discord.Embed(
            title="🚀 Crash Game Started!",
            description="The multiplier is starting to climb! Watch it go up and cash out before it crashes!",
            color=discord.Color.purple()
        )
        embed.add_field(name="💰 Bet Amount", value=f"{value:,}$", inline=True)
        embed.add_field(name="📈 Starting Multiplier", value="1.0x", inline=True)
        embed.add_field(name="🎯 Status", value="**READY**", inline=True)
        embed.set_footer(text="Click 'Cash Out' at any time to secure your winnings!")
        
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
# 📜 RULES COMMAND
# -----------------------------
@bot.command(name="rules")
async def rules(ctx):
    """
    Display the rules and information for all gambling games.
    
    Usage: !rules
    """
    try:
        embed = discord.Embed(
            title="🎰 Gambling Games Rules",
            description="Welcome to Eli's MM gambling system! Here are all the games you can play:",
            color=discord.Color.blue()
        )
        
        # Coinflip
        embed.add_field(
            name="🪙 Coinflip",
            value=(
                "**Command:** `!coinflip <amount> <heads/tails>`\n"
                "**Example:** `!coinflip 10m heads`\n"
                "**How to Play:** Choose heads or tails. If the coin lands on your choice, you win 2x your bet!\n"
                "**Multiplier:** 2x (100% return on win)\n"
                "**Win Chance:** 50%\n"
            ),
            inline=False
        )
        
        # Slots
        embed.add_field(
            name="🎰 Slots",
            value=(
                "**Command:** `!slots <amount>`\n"
                "**Example:** `!slots 5m`\n"
                "**How to Play:** Spin a 3x3 slot machine! Match 3 symbols in a row, column, or diagonal to win.\n"
                "**Multipliers:**\n"
                "  • 7️⃣ Jackpot = 5.0x\n"
                "  • 💎 Diamond = 3.0x\n"
                "  • ⭐ Star = 2.5x\n"
                "  • 🍇 Grape = 2.0x\n"
                "  • 🍊 Orange = 1.8x\n"
                "  • 🍋 Lemon = 1.5x\n"
                "  • 🍒 Cherry = 1.2x\n"
                "**Features:** Click 🔄 Spin Again to replay with same bet!\n"
            ),
            inline=False
        )
        
        # Lucky Number
        embed.add_field(
            name="🎲 Lucky Number",
            value=(
                "**Commands:** \n"
                "  1. `!luckynumber <amount> <max_number>` - Start game\n"
                "  2. `!pick <number>` - Make your guess\n"
                "**Example:** `!luckynumber 1m 100` then `!pick 42`\n"
                "**How to Play:** Choose a number range (1-5000), then guess the lucky number!\n"
                "**Risk Levels & Multipliers:**\n"
                "  • 1-10: Low risk → 8x\n"
                "  • 1-50: Medium risk → 40x\n"
                "  • 1-100: High risk → 80x\n"
                "  • 1-500: Very high risk → 400x\n"
                "  • 1-1000: Extreme risk → 800x\n"
                "  • 1-2500: Ultra risk → 2000x\n"
                "  • 1-5000: Maximum risk → 4000x\n"
                "**Note:** Higher ranges = bigger multipliers but lower win chance!\n"
            ),
            inline=False
        )
        
        # Crash
        embed.add_field(
            name="🚀 Crash",
            value=(
                "**Command:** `!crash <amount>`\n"
                "**Example:** `!crash 10m`\n"
                "**How to Play:** A multiplier starts at 1.0x and climbs higher. Cash out before it crashes to win!\n"
                "**Strategy:** The longer you wait, the higher the multiplier - but higher risk of crashing!\n"
                "**Multiplier Range:** Crashes anywhere from 1.1x to 50x+ (weighted towards lower values)\n"
                "**Your Winnings:** Bet amount × multiplier when you cash out\n"
                "**Features:** Click 💵 Cash Out button to secure your winnings at any time!\n"
                "**Risk:** If you don't cash out before the crash, you lose your entire bet\n"
            ),
            inline=False
        )
        
        # General Rules
        embed.add_field(
            name="📋 General Rules",
            value=(
                "• **Deposit Requirement:** Minimum 10M deposit required\n"
                "• **Gambling Requirement:** Must gamble 30% of your balance before withdrawing\n"
                "• **Balance Updates:** All wins/losses update your balance instantly\n"
                "• **Fraud Detection:** Rapid betting and high-value bets are monitored\n"
                "• **Withdrawals:** Use `!withdraw` when you meet the gambling requirement\n"
            ),
            inline=False
        )
        
        embed.set_footer(text="🎲 Gamble responsibly! • Use !assist for more commands")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error displaying rules: {str(e)}")


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

