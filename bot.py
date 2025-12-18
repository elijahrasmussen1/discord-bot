# discord-bot
import discord
from discord.ext import commands
from discord.ui import View, Button
import sqlite3
import random

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
        try:
            return int(value)
        except ValueError:
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
# COINFLIP COMMAND
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
    if value < 0:
        await ctx.send("❌ Invalid amount format! Use k, m, or b (e.g., 10m, 5k) or a plain number.")
        return

    if value == 0:
        await ctx.send("❌ You must gamble a positive amount.")
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
    if value < 0:
        await ctx.send("❌ Invalid amount format! Use k, m, or b (e.g., 10m, 5k) or a plain number.")
        return
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

# -----------------------------
# BOT READY
# -----------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# -----------------------------
# RUN BOT
# -----------------------------
bot.run("YOUR_BOT_TOKEN_HERE")
