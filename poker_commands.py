"""
Poker Commands Module
Discord command handlers for poker game.
"""

import discord
from discord.ext import commands
from typing import Dict, Optional, Callable
from poker_game import PokerGame, GamePhase
from poker_player import PlayerAction
import asyncio


class PokerManager:
    """Manages active poker games across different channels."""
    
    def __init__(self, bot, parse_money_func, get_user_func, update_balance_func, add_gambled_func):
        self.bot = bot
        self.active_games: Dict[int, PokerGame] = {}  # channel_id -> PokerGame
        self.game_tasks: Dict[int, asyncio.Task] = {}  # channel_id -> monitoring task
        self.parse_money = parse_money_func
        self.get_user = get_user_func
        self.update_balance = update_balance_func
        self.add_gambled = add_gambled_func
    
    def create_game(self, channel_id: int, host_id: int, small_blind: int = 50, big_blind: int = 100) -> PokerGame:
        """Create a new poker game in a channel."""
        if channel_id in self.active_games:
            raise ValueError("A game is already active in this channel")
        
        game = PokerGame(channel_id, host_id, small_blind, big_blind)
        self.active_games[channel_id] = game
        return game
    
    def get_game(self, channel_id: int) -> Optional[PokerGame]:
        """Get the active game in a channel."""
        return self.active_games.get(channel_id)
    
    def remove_game(self, channel_id: int):
        """Remove a game from a channel."""
        if channel_id in self.active_games:
            del self.active_games[channel_id]
        if channel_id in self.game_tasks:
            self.game_tasks[channel_id].cancel()
            del self.game_tasks[channel_id]
    
    async def monitor_game(self, channel_id: int):
        """Monitor a game for turn timeouts."""
        game = self.get_game(channel_id)
        if not game:
            return
        
        channel = self.bot.get_channel(channel_id)
        
        while game.phase not in [GamePhase.WAITING, GamePhase.FINISHED]:
            await asyncio.sleep(1)
            
            if game.is_turn_expired():
                current_player = game.get_current_player()
                if current_player:
                    await channel.send(f"⏰ {current_player.username}'s turn timed out. Auto-folding...")
                    game.handle_turn_timeout()
                    
                    # Update game state
                    if game.phase == GamePhase.FINISHED:
                        await self.show_game_results(channel, game)
                        break
                    else:
                        await self.show_game_state(channel, game)
    
    async def show_game_state(self, channel, game: PokerGame):
        """Display current game state."""
        state = game.get_game_state()
        
        embed = discord.Embed(
            title="🃏 Texas Hold'em Poker",
            description=f"**Phase:** {state['phase'].replace('_', ' ').title()}",
            color=discord.Color.green()
        )
        
        # Community cards
        if state['community_cards']:
            embed.add_field(
                name="Community Cards",
                value=" ".join(state['community_cards']),
                inline=False
            )
        
        # Pot and current bet
        embed.add_field(name="Pot", value=f"{state['pot']:,}$", inline=True)
        embed.add_field(name="Current Bet", value=f"{state['current_bet']:,}$", inline=True)
        
        # Players
        players_info = []
        for p in state['players']:
            status = "✅" if p['is_active'] else "❌"
            if p['is_all_in']:
                status = "🔴"
            
            action = f" ({p['last_action']})" if p['last_action'] else ""
            is_dealer = " 🎲" if p['position'] == state['dealer_position'] else ""
            is_current = " ⏰" if p['user_id'] == state['current_player'] else ""
            
            players_info.append(
                f"{status} **{p['username']}**{is_dealer}{is_current}: {p['stack']:,}$ "
                f"(bet: {p['current_bet']:,}$){action}"
            )
        
        embed.add_field(name="Players", value="\n".join(players_info), inline=False)
        
        # Current turn
        if state['current_player']:
            current = next(p for p in state['players'] if p['user_id'] == state['current_player'])
            embed.add_field(
                name="Current Turn",
                value=f"{current['username']} ({state['time_remaining']}s remaining)",
                inline=False
            )
        
        await channel.send(embed=embed)
    
    async def show_game_results(self, channel, game: PokerGame):
        """Display game results and winner."""
        embed = discord.Embed(
            title="🏆 Hand Complete!",
            color=discord.Color.gold()
        )
        
        # Show community cards
        if game.community_cards:
            embed.add_field(
                name="Community Cards",
                value=" ".join(str(c) for c in game.community_cards),
                inline=False
            )
        
        # Show winners from log
        winners = [log for log in game.game_log if log.get('action') == 'winner']
        
        for winner_log in winners:
            hand_info = winner_log.get('hand', 'N/A')
            hole_cards = winner_log.get('hole_cards', 'N/A')
            amount = winner_log.get('amount', 0)
            
            embed.add_field(
                name=f"Winner: {winner_log['username']}",
                value=f"**Hand:** {hand_info}\n**Hole Cards:** {hole_cards}\n**Won:** {amount:,}$",
                inline=False
            )
        
        # Show shuffle verification
        if game.shuffle_verification:
            embed.add_field(
                name="🔒 Shuffle Verification",
                value=f"Hash: `{game.shuffle_hash[:16]}...`\n"
                      f"Verified: ✅ Fair shuffle confirmed",
                inline=False
            )
        
        await channel.send(embed=embed)


# Global poker manager
poker_manager: Optional[PokerManager] = None


def setup_poker_commands(bot, parse_money_func, get_user_func, update_balance_func, add_gambled_func):
    """Setup poker commands on the bot."""
    global poker_manager
    poker_manager = PokerManager(bot, parse_money_func, get_user_func, update_balance_func, add_gambled_func)
    
    @bot.command(name="pokerjoin")
    async def poker_join(ctx, amount: str = None):
        """Join a poker table with a buy-in amount."""
        if amount is None:
            await ctx.send("❌ Usage: `!pokerjoin <amount>` (e.g., !pokerjoin 1000 or !pokerjoin 1k)")
            return
        
        value = poker_manager.parse_money(amount)
        if value <= 0:
            await ctx.send("❌ Invalid amount format! Use k, m, or b (e.g., 10m, 5k).")
            return
        
        # Check user's balance
        user_id, balance, _, _, _, _ = poker_manager.get_user(ctx.author.id)
        if value > balance:
            await ctx.send(f"❌ Insufficient balance. Your balance: {balance:,}$")
            return
        
        # Get or create game
        game = poker_manager.get_game(ctx.channel.id)
        if game is None:
            # Create new game with this user as host
            game = poker_manager.create_game(ctx.channel.id, ctx.author.id)
            await ctx.send(f"🃏 **New Poker Table Created!**\n"
                          f"{ctx.author.mention} is the host.\n"
                          f"Small Blind: {game.small_blind:,}$ | Big Blind: {game.big_blind:,}$\n"
                          f"Use `!pokerjoin <amount>` to join and `!pokerstart` to begin!")
        
        # Add player
        if game.add_player(ctx.author.id, ctx.author.display_name, value):
            # Deduct from user's balance
            poker_manager.update_balance(ctx.author.id, -value)
            await ctx.send(f"✅ {ctx.author.mention} joined the table with {value:,}$!")
        else:
            await ctx.send("❌ Cannot join the table. Game may be full or already started.")
    
    @bot.command(name="pokerstart")
    async def poker_start(ctx):
        """Start the poker game (host only)."""
        game = poker_manager.get_game(ctx.channel.id)
        
        if game is None:
            await ctx.send("❌ No poker game in this channel. Use `!pokerjoin <amount>` to create one.")
            return
        
        if ctx.author.id != game.host_id:
            await ctx.send("❌ Only the host can start the game.")
            return
        
        if not game.can_start():
            await ctx.send(f"❌ Need at least {game.min_players} players to start. "
                          f"Current players: {len(game.players)}")
            return
        
        game.start_game()
        
        # Send hole cards to each player via DM
        for player in game.players:
            try:
                user = await bot.fetch_user(player.user_id)
                hole_cards = player.get_hole_cards_string()
                await user.send(f"🃏 **Your Hole Cards:** {hole_cards}")
            except:
                pass
        
        await ctx.send(f"🃏 **Poker game started!**\n"
                      f"Shuffle Hash: `{game.shuffle_hash[:32]}...`\n"
                      f"Players have been dealt their hole cards via DM.")
        
        await poker_manager.show_game_state(ctx.channel, game)
        
        # Start monitoring task
        task = asyncio.create_task(poker_manager.monitor_game(ctx.channel.id))
        poker_manager.game_tasks[ctx.channel.id] = task
    
    @bot.command(name="pokercheck")
    async def poker_check(ctx):
        """Check (pass without betting)."""
        game = poker_manager.get_game(ctx.channel.id)
        if game is None:
            await ctx.send("❌ No active poker game in this channel.")
            return
        
        success, message = game.player_action(ctx.author.id, PlayerAction.CHECK)
        await ctx.send(message if success else f"❌ {message}")
        
        if success:
            if game.phase == GamePhase.FINISHED:
                await poker_manager.show_game_results(ctx.channel, game)
            else:
                await poker_manager.show_game_state(ctx.channel, game)
    
    @bot.command(name="pokerbet")
    async def poker_bet(ctx, amount: str = None):
        """Place a bet."""
        if amount is None:
            await ctx.send("❌ Usage: `!pokerbet <amount>`")
            return
        
        value = poker_manager.parse_money(amount)
        if value <= 0:
            await ctx.send("❌ Invalid amount format!")
            return
        
        game = poker_manager.get_game(ctx.channel.id)
        if game is None:
            await ctx.send("❌ No active poker game in this channel.")
            return
        
        success, message = game.player_action(ctx.author.id, PlayerAction.BET, value)
        await ctx.send(message if success else f"❌ {message}")
        
        if success:
            if game.phase == GamePhase.FINISHED:
                await poker_manager.show_game_results(ctx.channel, game)
            else:
                await poker_manager.show_game_state(ctx.channel, game)
    
    @bot.command(name="pokerraise")
    async def poker_raise(ctx, amount: str = None):
        """Raise the current bet."""
        if amount is None:
            await ctx.send("❌ Usage: `!pokerraise <amount>`")
            return
        
        value = poker_manager.parse_money(amount)
        if value <= 0:
            await ctx.send("❌ Invalid amount format!")
            return
        
        game = poker_manager.get_game(ctx.channel.id)
        if game is None:
            await ctx.send("❌ No active poker game in this channel.")
            return
        
        success, message = game.player_action(ctx.author.id, PlayerAction.RAISE, value)
        await ctx.send(message if success else f"❌ {message}")
        
        if success:
            if game.phase == GamePhase.FINISHED:
                await poker_manager.show_game_results(ctx.channel, game)
            else:
                await poker_manager.show_game_state(ctx.channel, game)
    
    @bot.command(name="pokercall")
    async def poker_call(ctx):
        """Call the current bet."""
        game = poker_manager.get_game(ctx.channel.id)
        if game is None:
            await ctx.send("❌ No active poker game in this channel.")
            return
        
        success, message = game.player_action(ctx.author.id, PlayerAction.CALL)
        await ctx.send(message if success else f"❌ {message}")
        
        if success:
            if game.phase == GamePhase.FINISHED:
                await poker_manager.show_game_results(ctx.channel, game)
            else:
                await poker_manager.show_game_state(ctx.channel, game)
    
    @bot.command(name="pokerfold")
    async def poker_fold(ctx):
        """Fold your hand."""
        game = poker_manager.get_game(ctx.channel.id)
        if game is None:
            await ctx.send("❌ No active poker game in this channel.")
            return
        
        success, message = game.player_action(ctx.author.id, PlayerAction.FOLD)
        await ctx.send(message if success else f"❌ {message}")
        
        if success:
            if game.phase == GamePhase.FINISHED:
                await poker_manager.show_game_results(ctx.channel, game)
            else:
                await poker_manager.show_game_state(ctx.channel, game)
    
    @bot.command(name="pokertable")
    async def poker_table(ctx):
        """View the current poker table state."""
        game = poker_manager.get_game(ctx.channel.id)
        if game is None:
            await ctx.send("❌ No active poker game in this channel.")
            return
        
        await poker_manager.show_game_state(ctx.channel, game)
    
    @bot.command(name="pokerleave")
    async def poker_leave(ctx):
        """Leave the poker table (only in waiting phase)."""
        game = poker_manager.get_game(ctx.channel.id)
        if game is None:
            await ctx.send("❌ No poker game in this channel.")
            return
        
        # Find player's stack before removing
        player = next((p for p in game.players if p.user_id == ctx.author.id), None)
        if player and game.remove_player(ctx.author.id):
            # Refund the player
            poker_manager.update_balance(ctx.author.id, player.stack)
            
            await ctx.send(f"✅ {ctx.author.mention} left the table.")
            
            # If no players left, remove the game
            if len(game.players) == 0:
                poker_manager.remove_game(ctx.channel.id)
                await ctx.send("🃏 Poker table closed (no players remaining).")
        else:
            await ctx.send("❌ Cannot leave. Game may have already started or you're not in the game.")
    
    @bot.command(name="pokerend")
    async def poker_end(ctx):
        """End the poker game and return chips to players (host only)."""
        game = poker_manager.get_game(ctx.channel.id)
        if game is None:
            await ctx.send("❌ No poker game in this channel.")
            return
        
        if ctx.author.id != game.host_id:
            await ctx.send("❌ Only the host can end the game.")
            return
        
        # Refund all players their remaining stacks
        for player in game.players:
            if player.stack > 0:
                poker_manager.update_balance(player.user_id, player.stack)
            
            # Add total bet to gambled amount
            if player.total_bet > 0:
                poker_manager.add_gambled(player.user_id, player.total_bet)
        
        poker_manager.remove_game(ctx.channel.id)
        await ctx.send("🃏 Poker game ended. All remaining chips returned to players.")
    
    return poker_manager
