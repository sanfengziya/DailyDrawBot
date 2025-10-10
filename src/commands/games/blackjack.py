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
        self.original_bet = bet_amount  # 保存原始下注金额
        self.deck = self._create_deck()
        self.player_hand = []
        self.dealer_hand = []
        self.game_over = False
        self.result = None
        self.doubled_down = False  # 是否已加倍下注
        self.is_split = False  # 是否已分牌
        self.split_hands = []  # 分牌后的多手牌 [(hand, bet_amount), ...]
        self.current_hand_index = 0  # 当前处理的手牌索引（用于分牌）
        self.insurance_bought = False  # 是否购买保险
        self.insurance_amount = 0  # 保险金额
        self.surrendered = False  # 是否投降

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
        标准21点规则：
        - 庄家点数 < 17：必须要牌
        - 庄家点数 >= 17：必须停牌（无论输赢）

        这是全球赌场使用的标准规则，确保游戏公平性
        """
        dealer_value = self._calculate_hand_value(self.dealer_hand)
        return dealer_value < 17

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

    def can_double_down(self):
        """检查是否可以加倍下注（仅限首次发牌后2张牌，包括分牌后的每手牌 - DAS规则）"""
        if self.is_split:
            # 分牌模式：检查当前手牌是否只有2张且未加倍
            current = self.get_current_split_hand()
            if current:
                return len(current["hand"]) == 2 and not current.get("doubled", False)
            return False
        else:
            # 普通模式
            return len(self.player_hand) == 2 and not self.doubled_down

    def can_split(self):
        """检查是否可以分牌（两张牌点数相同）"""
        if len(self.player_hand) != 2 or self.is_split:
            return False
        # 检查两张牌的点数是否相同（J、Q、K都算10点）
        card1_value = self._card_value(self.player_hand[0])
        card2_value = self._card_value(self.player_hand[1])
        return card1_value == card2_value

    def can_buy_insurance(self):
        """检查是否可以购买保险（庄家明牌是A且尚未购买）"""
        if self.insurance_bought or len(self.dealer_hand) < 2:
            return False
        # 检查庄家明牌（第一张）是否为A
        return self.dealer_hand[0][0] == 'A'

    def can_surrender(self):
        """检查是否可以投降（首次发牌后2张牌且未进行其他操作）"""
        return (len(self.player_hand) == 2 and
                not self.doubled_down and
                not self.is_split and
                not self.insurance_bought and
                not self.surrendered)

    def split(self):
        """执行分牌操作"""
        if not self.can_split():
            raise RuntimeError("当前无法分牌")

        self.is_split = True
        # 将当前手牌分成两手
        card1 = self.player_hand[0]
        card2 = self.player_hand[1]

        # 创建两手牌，每手牌各一张，然后各发一张新牌
        hand1 = [card1, self.deck.pop()]
        hand2 = [card2, self.deck.pop()]

        # 保存到 split_hands
        self.split_hands = [
            {"hand": hand1, "bet": self.bet_amount, "doubled": False},
            {"hand": hand2, "bet": self.bet_amount, "doubled": False}
        ]

        # 清空原手牌（现在使用 split_hands）
        self.player_hand = []
        self.current_hand_index = 0

    def get_current_split_hand(self):
        """获取当前处理的分牌手牌"""
        if not self.is_split or self.current_hand_index >= len(self.split_hands):
            return None
        return self.split_hands[self.current_hand_index]

    def hit_split_hand(self):
        """为当前分牌手牌要牌"""
        if not self.is_split:
            raise RuntimeError("当前不在分牌状态")
        current = self.get_current_split_hand()
        if current:
            current["hand"].append(self.deck.pop())
            return self._calculate_hand_value(current["hand"])
        return 0

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

        # 玩家的牌显示
        if self.is_split:
            # 分牌模式：显示多手牌
            player_section = "**👤 你的牌**\n\n"
            for i, hand_data in enumerate(self.split_hands):
                hand = hand_data["hand"]
                bet = hand_data["bet"]
                doubled = hand_data.get("doubled", False)
                hand_str = self._format_hand(hand)
                hand_value = self._calculate_hand_value(hand)

                status = ""
                if i == self.current_hand_index and not game_over:
                    status = " ← 当前"
                if doubled:
                    status += " [已加倍]"

                player_section += f"手牌 {i+1}{status}\n{hand_str}\n点数: `{hand_value}` | 下注: `{bet}` 积分\n\n"
        else:
            # 普通模式
            player_hand_str = self._format_hand(self.player_hand)
            player_value = self._calculate_hand_value(self.player_hand)

            double_status = " **[已加倍]**" if self.doubled_down else ""
            player_section = f"""**👤 你的牌**{double_status}

{player_hand_str}

点数: `{player_value}`"""

        # 保险状态显示
        insurance_info = ""
        if self.insurance_bought:
            insurance_info = f"\n**🛡️ 保险:** `{self.insurance_amount}` 积分"

        # 使用更宽的描述字段，增加空行让排版更舒服
        description = f"""
**🤖 庄家的牌**

{dealer_hand_str}

点数: `{dealer_value}`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{player_section}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**💰 总下注金额:** `{self.bet_amount}` 积分{insurance_info}
"""

        embed.description = description.strip()

        if not game_over:
            embed.set_footer(text="使用按钮选择你的行动 | 2分钟内有效")

        return embed


class BlackjackView(discord.ui.View):
    """二十一点游戏交互按钮"""

    def __init__(self, game: BlackjackGame, user_id: int, guild_id: int, current_points: int):
        super().__init__(timeout=120)
        self.game = game
        self.user_id = user_id
        self.guild_id = guild_id
        self.current_points = current_points  # 当前积分（用于检查是否能加倍/分牌）
        self.message = None

        # 根据游戏状态动态设置按钮可用性
        self._update_button_states()

    def _update_button_states(self):
        """根据游戏状态更新按钮可用性"""
        # Double Down 按钮：仅在首次发牌（2张牌）且有足够积分时可用
        # 在分牌模式下，需要检查当前手牌的下注金额
        if self.game.is_split:
            current_hand = self.game.get_current_split_hand()
            required_bet = current_hand["bet"] if current_hand else self.game.bet_amount
        else:
            required_bet = self.game.bet_amount

        can_double = self.game.can_double_down() and self.current_points >= required_bet

        # Split 按钮：仅在可以分牌且有足够积分时可用
        can_split = self.game.can_split() and self.current_points >= self.game.bet_amount

        # Insurance 按钮：庄家明牌是A且有足够积分（保险费用是下注的一半）
        insurance_cost = self.game.original_bet // 2
        can_insurance = self.game.can_buy_insurance() and self.current_points >= insurance_cost

        # Surrender 按钮：首次发牌后可用
        can_surrender = self.game.can_surrender()

        # 查找并设置按钮状态
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "double_down":
                    item.disabled = not can_double
                elif item.custom_id == "split":
                    item.disabled = not can_split
                elif item.custom_id == "insurance":
                    item.disabled = not can_insurance
                elif item.custom_id == "surrender":
                    item.disabled = not can_surrender

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

        # 根据是否分牌选择不同的逻辑
        if self.game.is_split:
            # 分牌模式：为当前手牌要牌
            player_value = self.game.hit_split_hand()

            # 检查是否爆牌
            if player_value > 21:
                # 当前手牌爆牌，移动到下一手牌
                await self._next_split_hand(interaction)
                return

            # 要牌后更新按钮状态（可能不能再加倍了）
            self._update_button_states()
        else:
            # 普通模式：玩家要牌
            player_value = self.game.hit(is_player=True)

            # 检查是否爆牌
            if player_value > 21:
                await self._end_game(interaction, "player_bust")
                return

            # 要牌后不能再加倍或分牌
            self._update_button_states()

        # 更新显示
        embed = self.game.get_game_state_embed(show_dealer_card=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="停牌 (Stand)", style=discord.ButtonStyle.success, emoji="✋")
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """停牌按钮"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("这不是你的游戏！", ephemeral=True)
            return

        # 根据是否分牌选择不同的逻辑
        if self.game.is_split:
            # 分牌模式：移动到下一手牌
            await self._next_split_hand(interaction)
        else:
            # 普通模式：玩家停牌，庄家开始要牌
            await self._dealer_turn(interaction)

    async def _next_split_hand(self, interaction: discord.Interaction):
        """处理分牌时移动到下一手牌"""
        self.game.current_hand_index += 1

        # 检查是否还有手牌需要处理
        if self.game.current_hand_index < len(self.game.split_hands):
            # 更新按钮状态（新手牌可能有不同的加倍条件）
            self._update_button_states()

            # 更新显示，显示下一手牌
            embed = self.game.get_game_state_embed(show_dealer_card=False)
            embed.set_footer(text=f"正在处理手牌 {self.game.current_hand_index + 1}/{len(self.game.split_hands)}")
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            # 所有手牌处理完毕，进入庄家回合
            await self._dealer_turn(interaction)

    @discord.ui.button(label="加倍 (Double)", style=discord.ButtonStyle.secondary, emoji="🎲", custom_id="double_down", row=1)
    async def double_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """加倍下注按钮（支持DAS - Double After Split）"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("这不是你的游戏！", ephemeral=True)
            return

        # 检查是否可以加倍
        if not self.game.can_double_down():
            await interaction.response.send_message("❌ 当前无法加倍下注！", ephemeral=True)
            return

        user_internal_id = get_user_internal_id_with_guild_and_discord_id(
            self.guild_id,
            self.user_id
        )

        # 根据是否分牌选择不同的逻辑
        if self.game.is_split:
            # 分牌模式 - DAS规则
            current_hand = self.game.get_current_split_hand()
            if not current_hand:
                await interaction.response.send_message("❌ 获取当前手牌失败！", ephemeral=True)
                return

            additional_bet = current_hand["bet"]

            # 检查积分是否足够
            if self.current_points < additional_bet:
                await interaction.response.send_message(
                    f"❌ 积分不足！加倍需要额外 {additional_bet} 积分。",
                    ephemeral=True
                )
                return

            # 扣除额外的下注金额
            try:
                await UserCache.update_points(
                    self.guild_id,
                    self.user_id,
                    user_internal_id,
                    -additional_bet
                )
            except Exception as e:
                print(f"扣除加倍积分失败: {e}")
                await interaction.response.send_message("❌ 扣除积分失败，请稍后重试。", ephemeral=True)
                return

            # 更新当前手牌状态
            current_hand["bet"] *= 2
            current_hand["doubled"] = True
            self.game.bet_amount += additional_bet  # 更新总下注金额
            self.current_points -= additional_bet

            # 为当前手牌发一张牌
            player_value = self.game.hit_split_hand()

            # 检查是否爆牌
            if player_value > 21:
                # 当前手牌爆牌，移动到下一手牌
                await self._next_split_hand(interaction)
                return

            # 加倍后自动停牌，移动到下一手牌
            await self._next_split_hand(interaction)

        else:
            # 普通模式
            # 检查积分是否足够
            if self.current_points < self.game.bet_amount:
                await interaction.response.send_message(
                    f"❌ 积分不足！加倍需要额外 {self.game.bet_amount} 积分。",
                    ephemeral=True
                )
                return

            # 扣除额外的下注金额
            try:
                await UserCache.update_points(
                    self.guild_id,
                    self.user_id,
                    user_internal_id,
                    -self.game.bet_amount
                )
            except Exception as e:
                print(f"扣除加倍积分失败: {e}")
                await interaction.response.send_message("❌ 扣除积分失败，请稍后重试。", ephemeral=True)
                return

            # 更新游戏状态
            self.game.bet_amount *= 2
            self.game.doubled_down = True
            self.current_points -= self.game.bet_amount // 2

            # 自动要一张牌
            player_value = self.game.hit(is_player=True)

            # 检查是否爆牌
            if player_value > 21:
                await self._end_game(interaction, "player_bust")
                return

            # 加倍后自动停牌，进入庄家回合
            await self._dealer_turn(interaction)

    @discord.ui.button(label="分牌 (Split)", style=discord.ButtonStyle.secondary, emoji="✂️", custom_id="split", row=1)
    async def split_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """分牌按钮"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("这不是你的游戏！", ephemeral=True)
            return

        # 检查是否可以分牌
        if not self.game.can_split():
            await interaction.response.send_message("❌ 当前无法分牌！", ephemeral=True)
            return

        # 检查积分是否足够（需要额外下注相同金额）
        if self.current_points < self.game.bet_amount:
            await interaction.response.send_message(
                f"❌ 积分不足！分牌需要额外 {self.game.bet_amount} 积分。",
                ephemeral=True
            )
            return

        # 扣除额外的下注金额
        user_internal_id = get_user_internal_id_with_guild_and_discord_id(
            self.guild_id,
            self.user_id
        )

        try:
            await UserCache.update_points(
                self.guild_id,
                self.user_id,
                user_internal_id,
                -self.game.bet_amount
            )
        except Exception as e:
            print(f"扣除分牌积分失败: {e}")
            await interaction.response.send_message("❌ 扣除积分失败，请稍后重试。", ephemeral=True)
            return

        # 执行分牌
        self.game.split()
        self.game.bet_amount *= 2  # 总下注金额翻倍
        self.current_points -= self.game.bet_amount // 2

        # 更新按钮状态（分牌后不能再加倍或分牌）
        self._update_button_states()

        # 更新显示
        embed = self.game.get_game_state_embed(show_dealer_card=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="保险 (Insurance)", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="insurance", row=2)
    async def insurance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """保险按钮"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("这不是你的游戏！", ephemeral=True)
            return

        # 检查是否可以购买保险
        if not self.game.can_buy_insurance():
            await interaction.response.send_message("❌ 当前无法购买保险！", ephemeral=True)
            return

        # 计算保险费用（原下注金额的一半）
        insurance_cost = self.game.original_bet // 2

        # 检查积分是否足够
        if self.current_points < insurance_cost:
            await interaction.response.send_message(
                f"❌ 积分不足！购买保险需要 {insurance_cost} 积分。",
                ephemeral=True
            )
            return

        # 扣除保险费用
        user_internal_id = get_user_internal_id_with_guild_and_discord_id(
            self.guild_id,
            self.user_id
        )

        try:
            await UserCache.update_points(
                self.guild_id,
                self.user_id,
                user_internal_id,
                -insurance_cost
            )
        except Exception as e:
            print(f"扣除保险费用失败: {e}")
            await interaction.response.send_message("❌ 扣除积分失败，请稍后重试。", ephemeral=True)
            return

        # 更新游戏状态
        self.game.insurance_bought = True
        self.game.insurance_amount = insurance_cost
        self.current_points -= insurance_cost

        # 检查庄家是否是BlackJack
        dealer_value = self.game._calculate_hand_value(self.game.dealer_hand)
        if dealer_value == 21:
            # 庄家是BlackJack，保险赔付2:1（返还保险费+赔付）
            insurance_payout = insurance_cost * 3  # 返还本金 + 2倍赔付
            await UserCache.update_points(
                self.guild_id,
                self.user_id,
                user_internal_id,
                insurance_payout
            )
            result_msg = f"🛡️ **保险成功！**\n\n庄家是BlackJack，保险赔付 `{insurance_cost * 2}` 积分！"
        else:
            result_msg = f"🛡️ **已购买保险**\n\n保险费用: `{insurance_cost}` 积分"

        # 更新按钮状态
        self._update_button_states()

        # 更新显示
        embed = self.game.get_game_state_embed(show_dealer_card=False)
        embed.set_footer(text=result_msg)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="投降 (Surrender)", style=discord.ButtonStyle.danger, emoji="🏳️", custom_id="surrender", row=2)
    async def surrender_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """投降按钮"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("这不是你的游戏！", ephemeral=True)
            return

        # 检查是否可以投降
        if not self.game.can_surrender():
            await interaction.response.send_message("❌ 当前无法投降！", ephemeral=True)
            return

        # 标记为投降
        self.game.surrendered = True

        # 返还一半下注金额
        surrender_return = self.game.bet_amount // 2
        user_internal_id = get_user_internal_id_with_guild_and_discord_id(
            self.guild_id,
            self.user_id
        )

        try:
            await UserCache.update_points(
                self.guild_id,
                self.user_id,
                user_internal_id,
                surrender_return
            )
        except Exception as e:
            print(f"返还投降积分失败: {e}")

        # 禁用所有按钮
        for item in self.children:
            item.disabled = True

        # 显示最终结果
        embed = self.game.get_game_state_embed(show_dealer_card=True, game_over=True)
        loss_amount = self.game.bet_amount - surrender_return
        result_text = f"🏳️ **投降！**\n\n返还 `{surrender_return}` 积分\n损失 `{loss_amount}` 积分"

        embed.description += f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**🎮 游戏结果**\n\n{result_text}"
        embed.set_footer(text="游戏结束 | 感谢游玩")

        # 保存游戏记录到数据库
        await self._save_game_record("surrender", surrender_return)

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def _save_game_record(self, result_type: str, points_change: int):
        """保存游戏记录到数据库

        Args:
            result_type: 游戏结果类型 (win/lose/tie/blackjack/surrender/dealer_blackjack)
            points_change: 总积分变化（返还给玩家的积分，不含本金）
        """
        try:
            supabase = get_connection()
            user_internal_id = get_user_internal_id_with_guild_and_discord_id(
                self.guild_id,
                self.user_id
            )

            # 计算净盈亏（points_change - original_bet = 实际盈亏）
            # 例如：赢了返还200，本金100，净盈亏=200-100=100
            # 输了返还0，本金100，净盈亏=0-100=-100
            profit = points_change - self.game.original_bet

            # 准备手牌数据（转换为JSON格式）
            if self.game.is_split:
                # 分牌模式：保存所有手牌
                player_hand_json = [
                    [{"rank": card[0], "suit": card[1]} for card in hand_data["hand"]]
                    for hand_data in self.game.split_hands
                ]
            else:
                # 普通模式：保存单手牌
                player_hand_json = [
                    {"rank": card[0], "suit": card[1]}
                    for card in self.game.player_hand
                ]

            dealer_hand_json = [
                {"rank": card[0], "suit": card[1]}
                for card in self.game.dealer_hand
            ]

            # 保存记录到数据库
            record_data = {
                "user_id": user_internal_id,
                "bet_amount": self.game.original_bet,
                "result": result_type,
                "profit": profit,
                "player_hand": player_hand_json,
                "dealer_hand": dealer_hand_json,
                "is_split": self.game.is_split,
                "is_doubled": self.game.doubled_down,
                "had_insurance": self.game.insurance_bought,
                "insurance_amount": self.game.insurance_amount,
                "surrendered": self.game.surrendered
            }

            supabase.table('blackjack_games').insert(record_data).execute()

        except Exception as e:
            print(f"保存游戏记录失败: {e}")
            # 即使保存失败，也不影响游戏继续

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

    async def _end_game(self, interaction: discord.Interaction, reason: str = None, winner: str = None):
        """结束游戏"""
        # 禁用所有按钮
        for item in self.children:
            item.disabled = True

        # 显示最终牌面
        embed = self.game.get_game_state_embed(show_dealer_card=True, game_over=True)

        # 检查 interaction 是否已经被响应
        already_responded = interaction.response.is_done()

        # 计算奖励
        user_internal_id = get_user_internal_id_with_guild_and_discord_id(
            self.guild_id,
            self.user_id
        )

        # 判断是普通模式还是分牌模式
        if self.game.is_split:
            # 分牌模式：判断每手牌的输赢
            dealer_value = self._calculate_hand_value(self.game.dealer_hand)
            result_text = "**📊 每手牌结果：**\n\n"
            total_points_change = 0
            wins = 0
            losses = 0
            ties = 0

            for i, hand_data in enumerate(self.game.split_hands):
                hand = hand_data["hand"]
                bet = hand_data["bet"]
                player_value = self._calculate_hand_value(hand)

                # 判断每手牌的输赢
                if player_value > 21:
                    result = "💥 爆牌"
                    hand_result = "lose"
                    hand_points = 0
                    losses += 1
                elif dealer_value > 21:
                    result = "🎉 庄家爆牌"
                    hand_result = "win"
                    hand_points = bet * 2
                    wins += 1
                elif player_value > dealer_value:
                    result = "🎉 赢了"
                    hand_result = "win"
                    hand_points = bet * 2
                    wins += 1
                elif dealer_value > player_value:
                    result = "😢 输了"
                    hand_result = "lose"
                    hand_points = 0
                    losses += 1
                else:
                    result = "🤝 平局"
                    hand_result = "tie"
                    hand_points = bet
                    ties += 1

                total_points_change += hand_points
                hand_str = self._format_hand(hand)
                result_text += f"手牌 {i+1}: {hand_str} (`{player_value}`点)\n{result}\n\n"

            # 计算净盈亏（已扣除本金）
            net_profit = total_points_change - self.game.bet_amount
            if net_profit > 0:
                profit_text = f"总计赢了 `{net_profit}` 积分 ✨"
            elif net_profit < 0:
                profit_text = f"总计输了 `{abs(net_profit)}` 积分"
            else:
                profit_text = "总计打平"

            result_text += f"━━━━━━━━━\n\n{profit_text}\n胜: {wins} | 负: {losses} | 平: {ties}"
            points_change = total_points_change

        else:
            # 普通模式：原有逻辑
            # 积分结算逻辑（开始游戏时已经扣除了下注金额）
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

        # 确定游戏结果类型
        if self.game.is_split:
            # 分牌模式：根据整体输赢判断
            if wins > losses:
                result_type = "win"
            elif losses > wins:
                result_type = "lose"
            else:
                result_type = "tie"
        else:
            # 普通模式：根据reason判断
            if reason == "player_bust":
                result_type = "lose"
            elif reason == "dealer_bust" or winner == "player":
                result_type = "win"
            elif winner == "dealer":
                result_type = "lose"
            else:  # tie
                result_type = "tie"

        # 保存游戏记录到数据库
        await self._save_game_record(result_type, points_change)

        # 根据 interaction 状态选择合适的方法
        if already_responded:
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

        self.stop()

    def _format_hand(self, hand):
        """格式化手牌显示（辅助方法）"""
        return self.game._format_hand(hand)

    def _calculate_hand_value(self, hand):
        """计算手牌点数（辅助方法）"""
        return self.game._calculate_hand_value(hand)


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

        # 保存开局BlackJack的游戏记录
        try:
            supabase = get_connection()

            # 准备手牌数据（转换为JSON格式）
            player_hand_json = [
                {"rank": card[0], "suit": card[1]}
                for card in game.player_hand
            ]
            dealer_hand_json = [
                {"rank": card[0], "suit": card[1]}
                for card in game.dealer_hand
            ]

            # 计算净盈亏
            profit = points_change - bet_amount

            # 确定结果类型
            if blackjack_check == "player_blackjack":
                result_type = "blackjack"
            elif blackjack_check == "dealer_blackjack":
                result_type = "dealer_blackjack"
            else:  # tie
                result_type = "tie"

            # 保存记录
            record_data = {
                "user_id": user_internal_id,
                "bet_amount": bet_amount,
                "result": result_type,
                "profit": profit,
                "player_hand": player_hand_json,
                "dealer_hand": dealer_hand_json,
                "is_split": False,
                "is_doubled": False,
                "had_insurance": False,
                "insurance_amount": 0,
                "surrendered": False
            }

            supabase.table('blackjack_games').insert(record_data).execute()
        except Exception as e:
            print(f"保存开局BlackJack游戏记录失败: {e}")

        await interaction.response.send_message(embed=embed)
        return

    # 创建交互视图（传入剩余积分用于检查是否能加倍/分牌）
    remaining_points = current_points - bet_amount
    view = BlackjackView(game, interaction.user.id, interaction.guild.id, remaining_points)
    embed = game.get_game_state_embed(show_dealer_card=False)
    await interaction.response.send_message(embed=embed, view=view)


@app_commands.command(name="blackjack_stats", description="📊 查看你的二十一点游戏统计数据")
@app_commands.guild_only()
async def blackjack_stats(interaction: discord.Interaction):
    """
    查看玩家的二十一点游戏统计信息

    Args:
        interaction: Discord交互
    """
    supabase = get_connection()

    # 获取用户内部ID
    user_internal_id = get_user_internal_id_with_guild_and_discord_id(
        interaction.guild.id,
        interaction.user.id
    )

    if not user_internal_id:
        await interaction.response.send_message(
            "❌ 找不到你的用户信息！请先玩一局二十一点游戏。",
            ephemeral=True
        )
        return

    try:
        # 查询该用户的所有游戏记录
        games_result = supabase.table('blackjack_games') \
            .select('*') \
            .eq('user_id', user_internal_id) \
            .execute()

        if not games_result.data:
            await interaction.response.send_message(
                "❌ 你还没有玩过二十一点游戏！使用 `/blackjack` 开始你的第一局游戏。",
                ephemeral=True
            )
            return

        games = games_result.data

        # 统计数据
        total_games = len(games)
        wins = sum(1 for g in games if g['result'] in ['win', 'blackjack'])
        losses = sum(1 for g in games if g['result'] in ['lose', 'dealer_blackjack'])
        ties = sum(1 for g in games if g['result'] == 'tie')
        surrenders = sum(1 for g in games if g['result'] == 'surrender')

        # 计算胜率
        win_rate = (wins / total_games * 100) if total_games > 0 else 0
        tie_rate = (ties / total_games * 100) if total_games > 0 else 0
        loss_rate = (losses / total_games * 100) if total_games > 0 else 0

        # 总盈亏
        total_profit = sum(g['profit'] for g in games)

        # 最大单局盈利和亏损
        max_win = max((g['profit'] for g in games if g['profit'] > 0), default=0)
        max_loss = min((g['profit'] for g in games if g['profit'] < 0), default=0)

        # Double Down/Split次数
        double_count = sum(1 for g in games if g.get('is_doubled', False))
        split_count = sum(1 for g in games if g.get('is_split', False))

        # 平均下注金额
        avg_bet = sum(g['bet_amount'] for g in games) / total_games if total_games > 0 else 0

        # 特殊统计
        blackjack_count = sum(1 for g in games if g['result'] == 'blackjack')

        # 创建embed显示统计信息
        embed = discord.Embed(
            title="📊 二十一点游戏统计",
            description=f"**{interaction.user.display_name}** 的游戏数据",
            color=0xdc143c  # 红色
        )

        # 基本统计
        embed.add_field(
            name="🎮 基本数据",
            value=f"""
**总局数:** `{total_games}` 局
**胜场:** `{wins}` 场 ({win_rate:.1f}%)
**败场:** `{losses}` 场 ({loss_rate:.1f}%)
**平局:** `{ties}` 场 ({tie_rate:.1f}%)
**投降:** `{surrenders}` 场
**BlackJack:** `{blackjack_count}` 次 🎰
""",
            inline=False
        )

        # 积分统计
        profit_emoji = "📈" if total_profit >= 0 else "📉"
        profit_text = f"+{total_profit}" if total_profit >= 0 else str(total_profit)

        embed.add_field(
            name="💰 积分统计",
            value=f"""
**总盈亏:** `{profit_text}` 积分 {profit_emoji}
**最大单局盈利:** `+{max_win}` 积分 ✨
**最大单局亏损:** `{max_loss}` 积分 💸
**平均下注:** `{avg_bet:.1f}` 积分
""",
            inline=False
        )

        # 高级操作统计
        embed.add_field(
            name="🎲 高级操作",
            value=f"""
**Double Down 次数:** `{double_count}` 次
**Split 次数:** `{split_count}` 次
**使用保险次数:** `{sum(1 for g in games if g.get('had_insurance', False))}` 次
""",
            inline=False
        )

        # 设置缩略图和底部信息
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="继续游戏并提升你的技巧！🎰")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        print(f"查询统计数据失败: {e}")
        await interaction.response.send_message(
            "❌ 查询统计数据时发生错误，请稍后重试。",
            ephemeral=True
        )


def setup(bot):
    """注册斜杠命令"""
    bot.tree.add_command(blackjack)
    bot.tree.add_command(blackjack_stats)
