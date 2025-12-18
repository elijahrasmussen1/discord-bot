import discord
from discord.ext import commands
from discord.ui import View, Button
import sqlite3
import random
import os

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
PING_ROLES = [1442285602166018069, 1442993726057087089]
MIN_DEPOSIT = 10_000_000
GAMBLE_PERCENT = 0.30
USERS_PER_PAGE = 5
GUILD_ID = 1442270020959867162

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
            # Process the withdrawal
            withdraw_balance(self.user.id, self.amount)
            
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

            channel = await guild.create_text_channel(
                name=f"deposit-{user.name}-{ticket_num:03}",
                category=category,
                overwrites=overwrites
            )

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

            channel = await guild.create_text_channel(
                name=f"withdraw-{interaction.user.name}-{ticket_num:03}",
                category=category,
                overwrites=overwrites
            )

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
        "**!withdraw [amount]** - Request a withdrawal (requires owner approval)\n"
        "**!coinflip [amount] [heads/tails]** - Gamble a coinflip"
    ))
    if is_owner(ctx.author):
        embed.add_field(name="🔐 Owner Commands", value=(
            "**!ticketpanel** - Send deposit ticket panel\n"
            "**!withdrawalpanel** - Send withdrawal ticket panel\n"
            "**!deposit @user amount** - Add gambling amount to a user\n"
            "**!viewamount @user** - View a user's balance\n"
            "**!amountall [page]** - View all users balances\n"
            "**!wipeamount @user** - Wipe a user's balance"
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
async def withdraw(ctx, amount: str = None):
    """Request a withdrawal. Owners must approve the request."""
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
        
        # Determine withdrawal amount
        if amount is None:
            # Withdraw full balance
            withdraw_amount = bal
        else:
            # Parse the specified amount
            withdraw_amount = parse_money(amount)
            if withdraw_amount <= 0:
                await ctx.send("❌ Invalid amount format! Use k, m, or b (e.g., 10m, 5k).")
                return
            
            # Check if amount is valid
            if withdraw_amount > bal:
                await ctx.send(f"❌ You cannot withdraw more than your balance ({bal:,}$).")
                return
        
        # Create withdrawal request embed
        embed = discord.Embed(
            title="💸 Withdrawal Request",
            description=f"{ctx.author.mention} has requested a withdrawal.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Amount", value=f"{withdraw_amount:,}$", inline=True)
        embed.add_field(name="Current Balance", value=f"{bal:,}$", inline=True)
        embed.add_field(name="Remaining After", value=f"{bal - withdraw_amount:,}$", inline=True)
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

        remaining = max(required_gamble - gambled, 0)

        embed = discord.Embed(title="🎰 Coinflip Result", description=result_msg, color=discord.Color.gold())
        embed.add_field(name="Balance", value=f"{balance:,}$")
        embed.add_field(name="Required Gamble", value=f"{required_gamble:,}$")
        embed.add_field(name="Remaining", value=f"{remaining:,}$")
        embed.add_field(name="Outcome", value=f"The coin landed on **{outcome}**")

        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error during coinflip: {str(e)}")

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
        update_balance(user.id, value)
        user_id, bal, req, gambled, _, _ = get_user(user.id)
        remaining = max(req - gambled, 0)
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

# -----------------------------
# RUN BOT
# -----------------------------
# Get bot token from environment variable or use placeholder
bot_token = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
if bot_token == "YOUR_BOT_TOKEN_HERE":
    print("⚠️ WARNING: Using placeholder bot token. Set DISCORD_BOT_TOKEN environment variable.")
bot.run(bot_token)

