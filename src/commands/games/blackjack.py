import discord
from discord import app_commands
import asyncio
import random
import datetime
from src.db.database import get_connection
from src.utils.helpers import get_user_internal_id_with_guild_and_discord_id
from src.utils.cache import UserCache


# 定义牌面和花色
SUITS = ['♠️', '♥️', '♣️', '♦️']
RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']


class BlackjackGame:
    """二十一点游戏类"""

    def __init__(self, player_id: int, bet_amount: int):
        self.player_id = player_id
        self.bet_amount = bet_amount
        self.deck = self._create_deck()
        self.player_hand = []
        self.dealer_hand = []
        self.game_over = False
        self.result = None

    def _create_deck(self):
        """创建一副牌并洗牌"""
        deck = []
        for suit in SUITS:
            for rank in RANKS:
                deck.append((rank, suit))
        random.shuffle(deck)
        return deck

    def _card_value(self, card):
        """计算单张牌的点数"""
        rank = card[0]
        if rank in ['J', 'Q', 'K']:
            return 10
        elif rank == 'A':
            return 11  # A默认为11，后续会处理爆牌情况
        else:
            return int(rank)

    def _calculate_hand_value(self, hand):
        """计算手牌总点数"""
        value = sum(self._card_value(card) for card in hand)
        aces = sum(1 for card in hand if card[0] == 'A')

        # 如果爆牌且有A，将A从11变为1
        while value > 21 and aces:
            value -= 10
            aces -= 1

        return value

    def _format_card(self, card):
        """格式化牌的显示"""
        return f"{card[1]}{card[0]}"

    def _format_hand(self, hand, hide_first=False):
        """格式化手牌显示"""
        if hide_first and len(hand) > 0:
            cards = ["🎴"] + [self._format_card(card) for card in hand[1:]]
        else:
            cards = [self._format_card(card) for card in hand]
        return " ".join(cards)

    def deal_initial_cards(self):
        """发初始牌"""
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]

    def hit(self, is_player=True):
        """要牌"""
        if len(self.deck) == 0:
            raise RuntimeError("牌堆已空，无法继续游戏")
        hand = self.player_hand if is_player else self.dealer_hand
        hand.append(self.deck.pop())
        return self._calculate_hand_value(hand)

    def dealer_should_hit(self):
        """
        激进AI：永不服输！只要输就继续要牌
        策略：
        - 庄家点数 < 17：必须要牌（基础规则）
        - 庄家点数 >= 17 且 < 玩家点数：继续要牌（宁愿爆牌也不认输！）
        - 庄家点数 >= 玩家点数：停牌（已经赢了或平局）
        """
        dealer_value = self._calculate_hand_value(self.dealer_hand)
        player_value = self._calculate_hand_value(self.player_hand)

        # 基础规则：小于17必须要牌
        if dealer_value < 17:
            return True

        # 激进策略：只要落后就要牌，宁愿爆牌也不认输！
        if dealer_value < player_value:
            return True

        # 平局或领先：停牌
        return False

    def check_blackjack(self):
        """检查是否有人开局就是21点"""
        player_value = self._calculate_hand_value(self.player_hand)
        dealer_value = self._calculate_hand_value(self.dealer_hand)

        if player_value == 21 and dealer_value == 21:
            return "tie"
        elif player_value == 21:
            return "player_blackjack"
        elif dealer_value == 21:
            return "dealer_blackjack"
        return None

    def determine_winner(self):
        """判断胜负"""
        player_value = self._calculate_hand_value(self.player_hand)
        dealer_value = self._calculate_hand_value(self.dealer_hand)

        if player_value > 21:
            return "dealer", "player_bust"
        elif dealer_value > 21:
            return "player", "dealer_bust"
        elif player_value > dealer_value:
            return "player", "player_higher"
        elif dealer_value > player_value:
            return "dealer", "dealer_higher"
        else:
            return "tie", "same_value"

    def get_game_state_embed(self, show_dealer_card=False, game_over=False):
        """生成游戏状态的embed消息"""
        embed = discord.Embed(title="🎰 二十一点游戏", color=0xdc143c)  # 红色

        # 庄家的牌
        dealer_hand_str = self._format_hand(self.dealer_hand, hide_first=not show_dealer_card)
        dealer_value = self._calculate_hand_value(self.dealer_hand) if show_dealer_card else "?"

        # 玩家的牌
        player_hand_str = self._format_hand(self.player_hand)
        player_value = self._calculate_hand_value(self.player_hand)

        # 使用更宽的描述字段，增加空行让排版更舒服
        description = f"""
**🤖 庄家的牌**

{dealer_hand_str}

点数: `{dealer_value}`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**👤 你的牌**

{player_hand_str}

点数: `{player_value}`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**💰 下注金额:** `{self.bet_amount}` 积分
"""

        embed.description = description.strip()

        if not game_over:
            embed.set_footer(text="使用按钮选择你的行动 | 2分钟内有效")

        return embed


class BlackjackView(discord.ui.View):
    """二十一点游戏交互按钮"""

    def __init__(self, game: BlackjackGame, user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.game = game
        self.user_id = user_id
        self.guild_id = guild_id
        self.message = None

    async def on_timeout(self):
        """处理超时：返还积分"""
        try:
            supabase = get_connection()
            user_internal_id = get_user_internal_id_with_guild_and_discord_id(
                self.guild_id,
                self.user_id
            )

            # 返还下注金额（因为游戏未完成）
            await UserCache.update_points(
                self.guild_id,
                self.user_id,
                user_internal_id,
                self.game.bet_amount
            )
        except Exception as e:
            print(f"超时返还积分失败: {e}")

    @discord.ui.button(label="要牌 (Hit)", style=discord.ButtonStyle.primary, emoji="🎴")
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """要牌按钮"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("这不是你的游戏！", ephemeral=True)
            return

        # 玩家要牌
        player_value = self.game.hit(is_player=True)

        # 检查是否爆牌
        if player_value > 21:
            await self._end_game(interaction, "player_bust")
            return

        # 更新显示
        embed = self.game.get_game_state_embed(show_dealer_card=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="停牌 (Stand)", style=discord.ButtonStyle.success, emoji="✋")
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """停牌按钮"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("这不是你的游戏！", ephemeral=True)
            return

        # 玩家停牌，庄家开始要牌
        await self._dealer_turn(interaction)

    async def _dealer_turn(self, interaction: discord.Interaction):
        """庄家回合"""
        # 禁用所有按钮
        for item in self.children:
            item.disabled = True

        # 显示庄家的牌
        embed = self.game.get_game_state_embed(show_dealer_card=True)
        embed.set_footer(text="庄家正在要牌...")
        await interaction.response.edit_message(embed=embed, view=self)

        # 庄家自动要牌（小于17点必须要牌）
        await asyncio.sleep(1.5)
        while self.game.dealer_should_hit():
            self.game.hit(is_player=False)
            embed = self.game.get_game_state_embed(show_dealer_card=True)
            await interaction.edit_original_response(embed=embed, view=self)
            await asyncio.sleep(1.5)

        # 判断胜负
        winner, reason = self.game.determine_winner()
        await self._end_game(interaction, reason, winner=winner)

    async def _end_game(self, interaction: discord.Interaction, reason: str, winner: str = None):
        """结束游戏"""
        # 禁用所有按钮
        for item in self.children:
            item.disabled = True

        # 显示最终牌面
        embed = self.game.get_game_state_embed(show_dealer_card=True, game_over=True)

        # 检查 interaction 是否已经被响应
        already_responded = interaction.response.is_done()

        # 计算奖励
        supabase = get_connection()
        user_internal_id = get_user_internal_id_with_guild_and_discord_id(
            self.guild_id,
            self.user_id
        )

        # 积分结算逻辑（开始游戏时已经扣除了下注金额）
        # 保持红色主题不变
        if reason == "player_bust":
            # 玩家爆牌，输掉（已经扣了下注金额，不需要额外操作）
            result_text = f"💥 **爆牌了！**\n\n你输了 `{self.game.bet_amount}` 积分"
            points_change = 0
        elif reason == "dealer_bust":
            # 庄家爆牌，玩家赢（返还本金 + 奖励 = 2倍下注金额）
            winnings = self.game.bet_amount * 2
            result_text = f"🎉 **庄家爆牌！**\n\n你赢了 `{self.game.bet_amount}` 积分"
            points_change = winnings
        elif winner == "player":
            # 玩家赢（返还本金 + 奖励 = 2倍下注金额）
            winnings = self.game.bet_amount * 2
            result_text = f"🎉 **你赢了！**\n\n你赢了 `{self.game.bet_amount}` 积分"
            points_change = winnings
        elif winner == "dealer":
            # 庄家赢，玩家输（已经扣了下注金额，不需要额外操作）
            result_text = f"😢 **你输了！**\n\n你输了 `{self.game.bet_amount}` 积分"
            points_change = 0
        else:  # tie
            # 平局（返还本金）
            result_text = f"🤝 **平局！**\n\n返还 `{self.game.bet_amount}` 积分"
            points_change = self.game.bet_amount

        # 更新积分（注意：开始游戏时已经扣除了下注金额，这里是结算输赢）
        try:
            await UserCache.update_points(
                self.guild_id,
                self.user_id,
                user_internal_id,
                points_change
            )
        except Exception as e:
            print(f"更新积分失败: {e}")

        # 在描述中添加游戏结果
        embed.description += f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**🎮 游戏结果**\n\n{result_text}"
        embed.set_footer(text="游戏结束 | 感谢游玩")

        # 根据 interaction 状态选择合适的方法
        if already_responded:
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

        self.stop()


# 斜杠命令定义
@app_commands.command(name="blackjack", description="🎰 二十一点游戏 - 和AI庄家对决")
@app_commands.describe(bet="下注金额 (输入数字或 'all' 下注全部)")
@app_commands.guild_only()
async def blackjack(interaction: discord.Interaction, bet: str):
    """
    二十一点游戏命令

    Args:
        interaction: Discord交互
        bet: 下注金额（可以是数字或 "all"）
    """
    supabase = get_connection()

    # 获取用户内部ID
    user_internal_id = get_user_internal_id_with_guild_and_discord_id(interaction.guild.id, interaction.user.id)

    # 如果用户不存在，自动创建
    if not user_internal_id:
        try:
            create_response = supabase.table('users').insert({
                'guild_id': interaction.guild.id,
                'discord_user_id': interaction.user.id,
                'points': 0,
                'last_draw_date': None,
                'paid_draws_today': 0,
                'last_paid_draw_date': '1970-01-01',
                'equipped_pet_id': None,
                'last_pet_points_update': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
            }).execute()
            user_internal_id = create_response.data[0]['id']
        except Exception as e:
            print(f"创建用户失败: {e}")
            await interaction.response.send_message("❌ 获取用户信息失败，请稍后重试。", ephemeral=True)
            return

    # 检查用户积分
    try:
        user_result = supabase.table('users').select('points').eq('id', user_internal_id).execute()
        if not user_result.data:
            await interaction.response.send_message("❌ 获取用户信息失败！", ephemeral=True)
            return

        current_points = user_result.data[0]['points']
    except Exception as e:
        print(f"查询用户积分失败: {e}")
        await interaction.response.send_message("❌ 查询积分失败，请稍后重试。", ephemeral=True)
        return

    # 处理下注金额
    if bet.lower() == "all":
        bet_amount = current_points
        if bet_amount < 1:
            await interaction.response.send_message("❌ 你没有足够的积分开始游戏！", ephemeral=True)
            return
    else:
        # 尝试转换为整数
        try:
            bet_amount = int(bet)
        except ValueError:
            await interaction.response.send_message("❌ 无效的下注金额！请输入数字或 'all'", ephemeral=True)
            return

        # 验证下注金额
        if bet_amount < 1:
            await interaction.response.send_message("❌ 下注金额必须大于0！", ephemeral=True)
            return

        if current_points < bet_amount:
            await interaction.response.send_message(
                f"❌ 积分不足！你当前有 {current_points} 积分，需要 {bet_amount} 积分才能开始游戏。",
                ephemeral=True
            )
            return

    # 扣除下注金额
    try:
        await UserCache.update_points(
            interaction.guild.id,
            interaction.user.id,
            user_internal_id,
            -bet_amount
        )
    except Exception as e:
        print(f"扣除积分失败: {e}")
        await interaction.response.send_message("❌ 下注失败，请稍后重试。", ephemeral=True)
        return

    # 创建游戏实例
    game = BlackjackGame(interaction.user.id, bet_amount)
    game.deal_initial_cards()

    # 检查是否开局就是21点
    blackjack_check = game.check_blackjack()
    if blackjack_check:
        embed = game.get_game_state_embed(show_dealer_card=True, game_over=True)

        if blackjack_check == "player_blackjack":
            # 玩家BlackJack，赢1.5倍（返还本金 + 1.5倍奖励）
            total_return = int(bet_amount * 2.5)
            profit = int(bet_amount * 1.5)
            result_text = f"🎰 **BlackJack!**\n\n你开局就是21点！\n\n你赢了 `{profit}` 积分"
            # 保持红色主题
            points_change = total_return
        elif blackjack_check == "dealer_blackjack":
            # 庄家BlackJack，玩家输（已经扣了下注金额）
            result_text = f"😢 **庄家BlackJack!**\n\n庄家开局就是21点！\n\n你输了 `{bet_amount}` 积分"
            # 保持红色主题
            points_change = 0
        else:  # tie
            # 平局（返还本金）
            result_text = f"🤝 **双方BlackJack平局！**\n\n双方都是21点！\n\n返还 `{bet_amount}` 积分"
            # 保持红色主题
            points_change = bet_amount

        # 更新积分
        try:
            await UserCache.update_points(
                interaction.guild.id,
                interaction.user.id,
                user_internal_id,
                points_change
            )
        except Exception as e:
            print(f"更新积分失败: {e}")

        # 在描述中添加游戏结果
        embed.description += f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**🎮 游戏结果**\n\n{result_text}"
        embed.set_footer(text="游戏结束 | 感谢游玩")
        await interaction.response.send_message(embed=embed)
        return

    # 创建交互视图
    view = BlackjackView(game, interaction.user.id, interaction.guild.id)
    embed = game.get_game_state_embed(show_dealer_card=False)
    await interaction.response.send_message(embed=embed, view=view)


def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(blackjack)
