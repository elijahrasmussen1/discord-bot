# discord-bot
import discord
from discord.ext import commands
from discord.ui import View, Button
import sqlite3
import random
import time
import asyncio
from datetime import datetime, timedelta, timezone

# -----------------------------
# INTENTS
# -----------------------------
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix=["!", "-"], intents=intents)

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

# Giveaway Configuration
GIVEAWAY_CHANNEL_ID = 1442336661731147837
INVITES_CHANNEL_ID = 1442705248274747594
INVITE_TRACKER_BOT_ID = 720351927581278219

# Role-based giveaway entries
MEMBER_ROLE_ID = 1442285739067834528  # 1 entry
LEVEL5_ROLE_ID = 1448410734428950569  # 2 entries
SHOP_OWNER_ROLE_ID = 1446627385511383162  # 3 entries
SERVER_BOOSTER_ROLE_ID = 1442698887180714258  # 4 entries, bypass requirements

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
c.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    timestamp INTEGER
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS giveaways (
    giveaway_id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    channel_id INTEGER,
    prize TEXT,
    winners_count INTEGER,
    end_time INTEGER,
    invite_requirement INTEGER,
    message_requirement INTEGER,
    message_period TEXT,
    active INTEGER DEFAULT 1
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS giveaway_entries (
    giveaway_id INTEGER,
    user_id INTEGER,
    entries INTEGER DEFAULT 1,
    PRIMARY KEY (giveaway_id, user_id)
)
""")
conn.commit()

# -----------------------------
# HELPERS
# -----------------------------
def parse_money(value: str) -> int:
    value = value.lower().replace(",", "")
    if value.endswith("m"):
        return int(float(value[:-1]) * 1_000_000)
    elif value.endswith("b"):
        return int(float(value[:-1]) * 1_000_000_000)
    elif value.endswith("k"):
        return int(float(value[:-1]) * 1_000)
    else:
        return -1

def is_owner(user):
    return user.id in OWNER_IDS

def get_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return get_user(user_id)
    return row

def update_balance(user_id, amount):
    user_id, bal, req, gambled, total_gambled, total_withdrawn = get_user(user_id)
    new_bal = bal + amount
    new_req = int(new_bal * GAMBLE_PERCENT)
    c.execute(
        "UPDATE users SET balance=?, required_gamble=? WHERE user_id=?",
        (new_bal, new_req, user_id)
    )
    conn.commit()

def add_gambled(user_id, amount):
    user_id, bal, req, gambled, total_gambled, total_withdrawn = get_user(user_id)
    new_gambled = gambled + amount
    new_total_gambled = total_gambled + amount
    c.execute(
        "UPDATE users SET gambled=?, total_gambled=? WHERE user_id=?",
        (new_gambled, new_total_gambled, user_id)
    )
    conn.commit()

def withdraw_balance(user_id, amount):
    user_id, bal, req, gambled, total_gambled, total_withdrawn = get_user(user_id)
    new_bal = bal - amount
    new_req = int(new_bal * GAMBLE_PERCENT)
    new_total_withdrawn = total_withdrawn + amount
    c.execute(
        "UPDATE users SET balance=?, required_gamble=?, gambled=0, total_withdrawn=? WHERE user_id=?",
        (new_bal, new_req, new_total_withdrawn, user_id)
    )
    conn.commit()

def parse_duration(duration_str):
    """Parse duration string like '10 minutes', '5 hours', '2 days' to seconds"""
    parts = duration_str.lower().strip().split()
    if len(parts) != 2:
        return None
    try:
        value = int(parts[0])
        unit = parts[1]
        if unit.startswith('minute'):
            return value * 60
        elif unit.startswith('hour'):
            return value * 3600
        elif unit.startswith('day'):
            return value * 86400
        else:
            return None
    except ValueError:
        return None

def get_user_invites(guild, user_id):
    """Get user invite count by checking Invite Tracker bot
    
    NOTE: This is a placeholder function. To fully integrate with Invite Tracker bot,
    you would need to either:
    1. Use their API if available
    2. Query their database if you have access
    3. Use Discord's invite tracking (guild.invites) and match to inviter
    
    For testing purposes, this returns 0 for non-boosters.
    Server Boosters bypass this check anyway.
    
    To make this functional, replace this function with actual invite tracking logic.
    """
    # TODO: Implement actual invite tracking integration
    # For now, assume all invites are met (return a high number for testing)
    # In production, replace with actual invite count from Invite Tracker
    return 999  # Temporary: allows testing without invite tracking integration

def get_message_count(user_id, period):
    """Get message count for a user based on period (today, weekly, monthly)"""
    now = int(time.time())
    if period.lower() == 'today':
        start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    elif period.lower() == 'weekly':
        start = int((datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    elif period.lower() == 'monthly':
        start = int(datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
    else:
        return 0
    
    c.execute("SELECT COUNT(*) FROM messages WHERE user_id=? AND timestamp>=?", (user_id, start))
    return c.fetchone()[0]

def get_entry_count(member):
    """Calculate entry count based on user roles"""
    role_ids = [role.id for role in member.roles]
    
    # Server Booster gets 4 entries
    if SERVER_BOOSTER_ROLE_ID in role_ids:
        return 4
    # Shop Owner gets 3 entries
    elif SHOP_OWNER_ROLE_ID in role_ids:
        return 3
    # Level 5 gets 2 entries
    elif LEVEL5_ROLE_ID in role_ids:
        return 2
    # Member gets 1 entry
    elif MEMBER_ROLE_ID in role_ids:
        return 1
    else:
        return 0

def is_booster(member):
    """Check if user has booster role (bypasses requirements)"""
    return any(role.id == SERVER_BOOSTER_ROLE_ID for role in member.roles)

def select_winners(entries, winners_count):
    """Select winners from entries using weighted random selection
    
    Args:
        entries: List of tuples (user_id, entry_count)
        winners_count: Number of winners to select
    
    Returns:
        List of winner user IDs
    """
    if not entries:
        return []
    
    # Create weighted list of user IDs based on entries
    weighted_entries = []
    for user_id, entry_count in entries:
        weighted_entries.extend([user_id] * entry_count)
    
    # Pick winners
    winners = []
    available_entries = weighted_entries.copy()
    
    for _ in range(min(winners_count, len(entries))):
        if not available_entries:
            break
        winner_id = random.choice(available_entries)
        winners.append(winner_id)
        # Remove all entries of this winner to avoid duplicate winners
        available_entries = [uid for uid in available_entries if uid != winner_id]
    
    return winners

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

        messages = []
        async for m in self.channel.history(limit=None, oldest_first=True):
            timestamp = m.created_at.strftime("%Y-%m-%d %H:%M")
            messages.append(f"**[{timestamp}] {m.author.display_name}:** {m.content}")

        transcript_channel = interaction.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
        ticket_name = self.channel.name
        ticket_id = self.channel.id

        embed = discord.Embed(title="📄 Ticket Transcript", color=discord.Color.blue())
        embed.add_field(name="Ticket Information", value=f"Ticket Name: {ticket_name}\nTicket ID: {ticket_id}", inline=False)
        await transcript_channel.send(embed=embed)

        for i in range(0, len(messages), 10):
            await transcript_channel.send(embed=discord.Embed(
                description="\n".join(messages[i:i+10]),
                color=discord.Color.blue()
            ))

        await interaction.response.send_message("✅ Ticket closed and transcript saved.", ephemeral=True)
        await self.channel.delete()

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Deposit Ticket", style=discord.ButtonStyle.green, custom_id="open_deposit_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        user = interaction.user

        c.execute("SELECT ticket_number FROM tickets WHERE user_id=?", (user.id,))
        row = c.fetchone()
        ticket_num = row[0] + 1 if row else 1
        c.execute("REPLACE INTO tickets VALUES (?,?)", (user.id, ticket_num))
        conn.commit()

        category = guild.get_channel(TICKET_CATEGORY_ID)
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

class WithdrawalPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Withdrawal Ticket", style=discord.ButtonStyle.green, custom_id="open_withdraw_ticket")
    async def open_withdraw_ticket(self, interaction: discord.Interaction, button: Button):
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

# -----------------------------
# GIVEAWAY VIEWS
# -----------------------------
class GiveawayView(View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🎉 Join Giveaway", style=discord.ButtonStyle.green, custom_id="join_giveaway")
    async def join_giveaway(self, interaction: discord.Interaction, button: Button):
        # Get giveaway details
        c.execute("SELECT * FROM giveaways WHERE giveaway_id=? AND active=1", (self.giveaway_id,))
        giveaway = c.fetchone()
        
        if not giveaway:
            await interaction.response.send_message("❌ This giveaway is no longer active.", ephemeral=True)
            return
        
        _, _, _, _, _, _, invite_req, message_req, message_period, _ = giveaway
        
        member = interaction.user
        guild = interaction.guild
        
        # Check if already entered
        c.execute("SELECT * FROM giveaway_entries WHERE giveaway_id=? AND user_id=?", 
                  (self.giveaway_id, member.id))
        if c.fetchone():
            await interaction.response.send_message("❌ You have already joined this giveaway!", ephemeral=True)
            return
        
        # Get entry count based on roles
        entries = get_entry_count(member)
        
        if entries == 0:
            await interaction.response.send_message("❌ You don't have a qualifying role to enter this giveaway!", ephemeral=True)
            return
        
        # Server boosters bypass requirements
        if is_booster(member):
            c.execute("INSERT INTO giveaway_entries VALUES (?, ?, ?)", 
                      (self.giveaway_id, member.id, entries))
            conn.commit()
            await interaction.response.send_message(
                f"✅ You joined the giveaway with **{entries} entries** (Server Booster - Requirements Bypassed)!", 
                ephemeral=True
            )
            return
        
        # Check invite requirement
        user_invites = get_user_invites(guild, member.id)
        if user_invites < invite_req:
            await interaction.response.send_message(
                f"❌ Join failed! You must complete the invite requirement.\n"
                f"Required: {invite_req} invites | Your invites: {user_invites}\n"
                f"Use /invites in <#{INVITES_CHANNEL_ID}> to see your invites.",
                ephemeral=True
            )
            return
        
        # Check message requirement
        user_messages = get_message_count(member.id, message_period)
        if user_messages < message_req:
            await interaction.response.send_message(
                f"❌ Join failed! You must complete the message requirement.\n"
                f"Required: {message_req} messages ({message_period}) | Your messages: {user_messages}\n"
                f"Spamming messages is a blacklist from the giveaway!",
                ephemeral=True
            )
            return
        
        # Both requirements met
        c.execute("INSERT INTO giveaway_entries VALUES (?, ?, ?)", 
                  (self.giveaway_id, member.id, entries))
        conn.commit()
        
        await interaction.response.send_message(
            f"✅ You successfully joined the giveaway with **{entries} entries**!", 
            ephemeral=True
        )

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
        "**!withdraw** - Open a withdrawal ticket (if 30% gambled)\n"
        "**!coinflip [amount] [heads/tails]** - Gamble a coinflip\n"
        "**!m [@user]** - View message count statistics (defaults to yourself)"
    ), inline=False)
    if is_owner(ctx.author):
        embed.add_field(name="🔐 Owner Commands", value=(
            "**!ticketpanel** - Send deposit ticket panel\n"
            "**!withdrawalpanel** - Send withdrawal ticket panel\n"
            "**!deposit @user amount** - Add gambling amount to a user\n"
            "**!viewamount @user** - View a user's balance\n"
            "**!amountall [page]** - View all users balances\n"
            "**!wipeamount @user** - Wipe a user's balance"
        ), inline=False)
        embed.add_field(name="🎉 Giveaway Commands", value=(
            "**-gcreate** - Create a new giveaway (interactive)\n"
            "**-greroll [giveaway_id]** - Reroll giveaway winners"
        ), inline=False)
    await ctx.send(embed=embed)

@bot.command(name="amount")
async def amount(ctx):
    user_id, bal, req, gambled, _, _ = get_user(ctx.author.id)
    remaining = max(req - gambled, 0)
    await ctx.send(f"💰 **Your Gambling Amount**\nBalance: `{bal:,}$`\nRequired Gamble: `{req:,}$`\nRemaining: `{remaining:,}$`")

@bot.command(name="withdraw")
async def withdraw(ctx):
    user_id, bal, req, gambled, _, _ = get_user(ctx.author.id)
    remaining_gamble = max(req - gambled, 0)
    if bal <= 0:
        await ctx.send("❌ You must make a deposit in order to withdraw.")
        return
    if remaining_gamble > 0:
        await ctx.send(f"❌ You must gamble {remaining_gamble:,}$ before withdrawing.")
        return
    withdraw_balance(ctx.author.id, bal)
    await ctx.send(f"✅ You withdrew {bal:,}$ SAB currency. Your new balance is 0$ and new 30% gambling requirement will apply next deposit.")
    log_channel = bot.get_channel(WITHDRAWAL_LOG_CHANNEL)
    await log_channel.send(f"💸 {ctx.author} withdrew {bal:,}$ SAB currency.")

# -----------------------------
# ✅ FIXED COINFLIP COMMAND
# -----------------------------
@bot.command(name="coinflip")
async def coinflip(ctx, amount: str = None, choice: str = None):
    if amount is None or choice is None:
        await ctx.send("❌ Usage: `!coinflip <amount> <heads/tails>`")
        return

    choice = choice.lower()
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

    gambled += value
    total_gambled += value
    required_gamble = int(balance * GAMBLE_PERCENT)

    c.execute(
        "UPDATE users SET balance=?, gambled=?, total_gambled=?, required_gamble=? WHERE user_id=?",
        (balance, gambled, total_gambled, required_gamble, ctx.author.id)
    )
    conn.commit()

    remaining = max(required_gamble - gambled, 0)

    embed = discord.Embed(title="🎰 Coinflip Result", description=result_msg, color=discord.Color.gold())
    embed.add_field(name="Balance", value=f"{balance:,}$")
    embed.add_field(name="Required Gamble", value=f"{required_gamble:,}$")
    embed.add_field(name="Remaining", value=f"{remaining:,}$")
    embed.add_field(name="Outcome", value=f"The coin landed on **{outcome}**")

    await ctx.send(embed=embed)

@bot.command(name="deposit")
async def deposit(ctx, user: discord.Member, amount: str):
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can deposit.")
        return
    value = parse_money(amount)
    if value < MIN_DEPOSIT:
        await ctx.send(f"❌ Minimum deposit is {MIN_DEPOSIT:,}$")
        return
    update_balance(user.id, value)
    user_id, bal, req, gambled, _, _ = get_user(user.id)
    remaining = max(req - gambled, 0)
    await ctx.send(f"✅ Added {value:,}$ to {user.mention}\nBalance: {bal:,}$ | Required Gamble: {req:,}$ | Remaining: {remaining:,}$")

@bot.command(name="viewamount")
async def viewamount(ctx, user: discord.Member):
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can use this.")
        return
    user_id, bal, req, gambled, _, _ = get_user(user.id)
    remaining = max(req - gambled, 0)
    await ctx.send(f"💰 **{user.display_name}'s Gambling Amount**\nBalance: `{bal:,}$`\nRequired Gamble: `{req:,}$`\nRemaining: `{remaining:,}$`")

@bot.command(name="amountall")
async def amountall(ctx, page: int = 1):
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can use this.")
        return
    c.execute("SELECT user_id, balance FROM users ORDER BY user_id")
    users = c.fetchall()
    total_pages = (len(users) + USERS_PER_PAGE - 1) // USERS_PER_PAGE
    page = max(1, min(page, total_pages))
    start = (page - 1) * USERS_PER_PAGE
    end = start + USERS_PER_PAGE
    user_list = users[start:end]
    description = "\n".join(f"<@{uid}>: {bal:,}$" for uid, bal in user_list)
    await ctx.send(embed=discord.Embed(
        title=f"💰 Gambling Balances - Page {page}/{total_pages}",
        description=description,
        color=discord.Color.green()
    ))

@bot.command(name="wipeamount")
async def wipeamount(ctx, user: discord.Member):
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can use this.")
        return
    c.execute("UPDATE users SET balance=0, required_gamble=0, gambled=0 WHERE user_id=?", (user.id,))
    conn.commit()
    await ctx.send(f"✅ {user.mention}'s balance wiped.")

@bot.command(name="m")
async def messages_count(ctx, user: discord.Member = None):
    if user is None:
        user = ctx.author
    
    # Calculate time boundaries
    today_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    week_start = int((datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    month_start = int(datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
    
    # Query message counts
    c.execute("SELECT COUNT(*) FROM messages WHERE user_id=? AND timestamp>=?", (user.id, today_start))
    today_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM messages WHERE user_id=? AND timestamp>=?", (user.id, week_start))
    week_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM messages WHERE user_id=? AND timestamp>=?", (user.id, month_start))
    month_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (user.id,))
    all_time_count = c.fetchone()[0]
    
    # Create professional embed
    embed = discord.Embed(
        title=f"📊 Message Statistics for {user.display_name}",
        description="Tracking message activity for giveaway eligibility",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="📅 Today", value=f"`{today_count:,}` messages", inline=True)
    embed.add_field(name="📆 This Week", value=f"`{week_count:,}` messages", inline=True)
    embed.add_field(name="🗓️ This Month", value=f"`{month_count:,}` messages", inline=True)
    embed.add_field(name="🌐 All Time", value=f"`{all_time_count:,}` messages", inline=True)
    
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text=f"User ID: {user.id}")
    embed.timestamp = datetime.now(timezone.utc)
    
    await ctx.send(embed=embed)

@bot.command(name="gcreate")
async def gcreate(ctx):
    """Interactive giveaway creation command"""
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can create giveaways.")
        return
    
    await ctx.send("🎉 **Giveaway Creation Wizard**\nPlease answer the following questions:")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        # Question 1: Duration
        await ctx.send("**Question 1:** What is the duration of the giveaway?\n*Format: `10 minutes`, `5 hours`, `2 days`*")
        duration_msg = await bot.wait_for('message', check=check, timeout=60.0)
        duration_seconds = parse_duration(duration_msg.content)
        
        if duration_seconds is None:
            await ctx.send("❌ Invalid duration format. Giveaway creation cancelled.")
            return
        
        # Question 2: Number of Winners
        await ctx.send("**Question 2:** How many winners?\n*Format: Enter a number (e.g., `1`, `3`)*")
        winners_msg = await bot.wait_for('message', check=check, timeout=60.0)
        
        try:
            winners_count = int(winners_msg.content)
            if winners_count < 1:
                await ctx.send("❌ Winners count must be at least 1. Giveaway creation cancelled.")
                return
        except ValueError:
            await ctx.send("❌ Invalid number. Giveaway creation cancelled.")
            return
        
        # Question 3: Prize
        await ctx.send("**Question 3:** What is the prize?")
        prize_msg = await bot.wait_for('message', check=check, timeout=120.0)
        prize = prize_msg.content
        
        # Question 4: Invite Requirement
        await ctx.send("**Giveaway Requirements:**\n**Question 4:** Minimum invites required?\n*Format: Enter a number (e.g., `2`)*")
        invite_msg = await bot.wait_for('message', check=check, timeout=60.0)
        
        try:
            invite_req = int(invite_msg.content)
        except ValueError:
            await ctx.send("❌ Invalid number. Giveaway creation cancelled.")
            return
        
        # Question 5: Message Requirement
        await ctx.send("**Question 5:** Minimum messages required and period?\n*Format: `250 Today`, `100 Weekly`, `500 Monthly`*")
        message_msg = await bot.wait_for('message', check=check, timeout=60.0)
        
        msg_parts = message_msg.content.split()
        if len(msg_parts) != 2:
            await ctx.send("❌ Invalid format. Giveaway creation cancelled.")
            return
        
        try:
            message_req = int(msg_parts[0])
            message_period = msg_parts[1].lower()
            
            if message_period not in ['today', 'weekly', 'monthly']:
                await ctx.send("❌ Period must be 'Today', 'Weekly', or 'Monthly'. Giveaway creation cancelled.")
                return
        except ValueError:
            await ctx.send("❌ Invalid number. Giveaway creation cancelled.")
            return
        
        # Create giveaway
        end_time = int(time.time()) + duration_seconds
        
        # Create giveaway embed
        embed = discord.Embed(
            title="🎉 GIVEAWAY 🎉",
            description=f"**Prize:** {prize}\n\n"
                       f"**Winners:** {winners_count}\n"
                       f"**Ends:** <t:{end_time}:R>\n\n"
                       f"**Requirements:**\n"
                       f"📨 Invites: {invite_req}\n"
                       f"💬 Messages: {message_req} ({message_period.title()})\n\n"
                       f"**Role Entries:**\n"
                       f"<@&{MEMBER_ROLE_ID}>: 1 entry\n"
                       f"<@&{LEVEL5_ROLE_ID}>: 2 entries\n"
                       f"<@&{SHOP_OWNER_ROLE_ID}>: 3 entries\n"
                       f"<@&{SERVER_BOOSTER_ROLE_ID}>: 4 entries (bypass requirements)",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Click the button below to join!")
        
        # Send to giveaway channel
        giveaway_channel = bot.get_channel(GIVEAWAY_CHANNEL_ID)
        if not giveaway_channel:
            await ctx.send("❌ Giveaway channel not found!")
            return
        
        # Insert into database first to get giveaway_id
        c.execute("""
            INSERT INTO giveaways (message_id, channel_id, prize, winners_count, end_time, 
                                   invite_requirement, message_requirement, message_period, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (0, GIVEAWAY_CHANNEL_ID, prize, winners_count, end_time, invite_req, message_req, message_period))
        conn.commit()
        giveaway_id = c.lastrowid
        
        # Send giveaway message with button
        giveaway_msg = await giveaway_channel.send(embed=embed, view=GiveawayView(giveaway_id))
        
        # Update with message_id
        c.execute("UPDATE giveaways SET message_id=? WHERE giveaway_id=?", (giveaway_msg.id, giveaway_id))
        conn.commit()
        
        await ctx.send(f"✅ Giveaway created! ID: `{giveaway_id}` | Jump: {giveaway_msg.jump_url}")
        
        # Schedule giveaway end
        asyncio.create_task(end_giveaway(giveaway_id, duration_seconds))
        
    except asyncio.TimeoutError:
        await ctx.send("❌ Giveaway creation timed out. Please try again.")

async def end_giveaway(giveaway_id, delay):
    """End a giveaway after the specified delay"""
    await asyncio.sleep(delay)
    
    # Get giveaway details
    c.execute("SELECT * FROM giveaways WHERE giveaway_id=? AND active=1", (giveaway_id,))
    giveaway = c.fetchone()
    
    if not giveaway:
        return
    
    giveaway_id, message_id, channel_id, prize, winners_count, end_time, invite_req, message_req, message_period, _ = giveaway
    
    # Get all entries
    c.execute("SELECT user_id, entries FROM giveaway_entries WHERE giveaway_id=?", (giveaway_id,))
    entries = c.fetchall()
    
    if not entries:
        # No entries, announce no winners
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                message = await channel.fetch_message(message_id)
                await message.reply("❌ No one entered the giveaway. No winners selected.")
            except discord.NotFound:
                print(f"Giveaway message not found: {message_id}")
            except discord.Forbidden:
                print(f"Bot lacks permission to access giveaway: {message_id}")
        
        c.execute("UPDATE giveaways SET active=0 WHERE giveaway_id=?", (giveaway_id,))
        conn.commit()
        return
    
    # Select winners using helper function
    winners = select_winners(entries, winners_count)
    
    # Announce winners
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            message = await channel.fetch_message(message_id)
            winner_mentions = " ".join([f"<@{uid}>" for uid in winners])
            
            embed = discord.Embed(
                title="🎉 GIVEAWAY ENDED 🎉",
                description=f"**Prize:** {prize}\n\n**Winners:**\n{winner_mentions}",
                color=discord.Color.green()
            )
            
            await message.edit(embed=embed, view=None)
            await message.reply(f"🎊 Congratulations {winner_mentions}! You won **{prize}**!")
        except discord.NotFound:
            print(f"Giveaway message not found: {message_id}")
        except discord.Forbidden:
            print(f"Bot lacks permission to edit giveaway: {message_id}")
        except Exception as e:
            print(f"Unexpected error ending giveaway {giveaway_id}: {type(e).__name__}")
    
    # Mark giveaway as inactive
    c.execute("UPDATE giveaways SET active=0 WHERE giveaway_id=?", (giveaway_id,))
    conn.commit()

@bot.command(name="greroll")
async def greroll(ctx, giveaway_id: int):
    """Reroll a giveaway to select new winners"""
    if not is_owner(ctx.author):
        await ctx.send("❌ Only owners can reroll giveaways.")
        return
    
    # Get giveaway details
    c.execute("SELECT * FROM giveaways WHERE giveaway_id=?", (giveaway_id,))
    giveaway = c.fetchone()
    
    if not giveaway:
        await ctx.send(f"❌ Giveaway with ID `{giveaway_id}` not found.")
        return
    
    _, message_id, channel_id, prize, winners_count, end_time, invite_req, message_req, message_period, active = giveaway
    
    # Get all entries
    c.execute("SELECT user_id, entries FROM giveaway_entries WHERE giveaway_id=?", (giveaway_id,))
    entries = c.fetchall()
    
    if not entries:
        await ctx.send(f"❌ No entries found for giveaway ID `{giveaway_id}`.")
        return
    
    # Select new winners using helper function
    winners = select_winners(entries, winners_count)
    
    # Announce new winners
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            message = await channel.fetch_message(message_id)
            winner_mentions = " ".join([f"<@{uid}>" for uid in winners])
            
            await message.reply(f"🔄 **Giveaway Rerolled!**\n🎊 New Winners: {winner_mentions}!\nPrize: **{prize}**")
            await ctx.send(f"✅ Giveaway rerolled! New winners: {winner_mentions}")
        except discord.NotFound:
            await ctx.send(f"❌ Giveaway message not found.")
        except discord.Forbidden:
            await ctx.send(f"❌ Bot lacks permission to access the giveaway message.")
        except Exception:
            await ctx.send(f"❌ An error occurred while rerolling the giveaway.")
    else:
        await ctx.send(f"❌ Giveaway channel not found.")

# -----------------------------
# BOT READY
# -----------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        await bot.process_commands(message)
        return
    
    # Track message in database
    timestamp = int(time.time())
    c.execute("INSERT INTO messages (user_id, timestamp) VALUES (?, ?)", (message.author.id, timestamp))
    conn.commit()
    
    # Process commands
    await bot.process_commands(message)

# -----------------------------
# RUN BOT
# -----------------------------
bot.run("YOUR_BOT_TOKEN_HERE")

