"""
德州扑克游戏命令
"""

from __future__ import annotations

import datetime
import json
import random
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import List, Optional, Sequence, Tuple

import discord
from discord import app_commands

from src.db.database import get_connection
from src.utils.cache import UserCache
from src.utils.helpers import get_user_internal_id_with_guild_and_discord_id
from src.utils.i18n import get_guild_locale, t

# 牌面与花色
SUITS = ['♠️', '♥️', '♣️', '♦️']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANK_VALUES = {rank: index for index, rank in enumerate(RANKS)}

DEFAULT_BIG_BLIND = 100
MIN_RAISE = 100

HAND_RANKINGS = {
    'high_card': 1,
    'one_pair': 2,
    'two_pair': 3,
    'three_of_a_kind': 4,
    'straight': 5,
    'flush': 6,
    'full_house': 7,
    'four_of_a_kind': 8,
    'straight_flush': 9,
    'royal_flush': 10
}

STARTING_HAND_STRENGTH = {
    'AA': 10, 'KK': 9.5, 'QQ': 9, 'JJ': 8.5, 'AKs': 8,
    'AQs': 7.5, 'AJs': 7, 'KQs': 7, 'TT': 6.5,
    '99': 6, 'ATs': 5.5, 'KJs': 5.5, 'QJs': 5,
    '22': 2, '72o': 1, '82o': 1.5
}

AI_FOLD_THRESHOLDS = {
    'easy': {'preflop': 3.0, 'flop': 3.8, 'turn': 4.2, 'river': 4.5},
    'medium': {'preflop': 3.5, 'flop': 4.5, 'turn': 5.0, 'river': 5.5},
    'hard': {'preflop': 4.0, 'flop': 5.0, 'turn': 5.5, 'river': 6.0}
}


@dataclass
class HandEvaluation:
    """保存牌型评估结果"""
    rank_name: str
    score: Tuple[int, ...]
    best_cards: Sequence[Tuple[str, str]]
    kicker: Tuple[int, ...]


@dataclass
class TexasHoldemPlayer:
    """玩家或AI的数据"""
    name: str
    is_human: bool
    stack: int
    difficulty: str = "medium"
    hole_cards: List[Tuple[str, str]] = field(default_factory=list)
    contribution: int = 0
    folded: bool = False
    last_action: str = ""
    best_hand: Optional[HandEvaluation] = None

    def invest(self, amount: int) -> int:
        """向底池投入筹码"""
        invest_amount = max(0, min(amount, self.stack))
        self.stack -= invest_amount
        self.contribution += invest_amount
        return invest_amount


def _format_card(card: Tuple[str, str]) -> str:
    """格式化单张牌"""
    rank, suit = card
    return f"{suit}{rank}"


def _hand_code(cards: Sequence[Tuple[str, str]]) -> str:
    """生成起手牌编码"""
    if len(cards) < 2:
        return ""
    r1 = cards[0][0]
    r2 = cards[1][0]
    alias = {'10': 'T'}
    c1 = alias.get(r1, r1)
    c2 = alias.get(r2, r2)
    suited = cards[0][1] == cards[1][1]
    if c1 == c2:
        return f"{c1}{c2}"
    ordered = ''.join(sorted([c1, c2], reverse=True))
    suffix = 's' if suited else 'o'
    return f"{ordered}{suffix}"


def _estimate_starting_strength(cards: Sequence[Tuple[str, str]]) -> float:
    """估算起手牌强度"""
    code = _hand_code(cards)
    if not code:
        return 3.0
    return STARTING_HAND_STRENGTH.get(code, 4.0)


def _describe_hand(rank_name: str, locale: str) -> str:
    """返回牌型描述"""
    return t(f"texas_holdem.hands.{rank_name}", locale=locale, default=rank_name)


def _format_points(locale: str, amount: int) -> str:
    """格式化积分显示"""
    return t("texas_holdem.embed.points_value", locale=locale).format(amount=amount)


def _classify_hand(cards: Sequence[Tuple[str, str]]) -> HandEvaluation:
    """评估5张牌的牌型"""
    values = [RANK_VALUES[card[0]] for card in cards]
    suits = [card[1] for card in cards]
    counts = Counter(values)
    unique_counts = sorted(counts.items(), key=lambda x: (-x[1], -x[0]))
    is_flush = len(set(suits)) == 1

    unique_values = sorted(set(values))
    straight_high = None
    if len(unique_values) == 5:
        if unique_values == [0, 1, 2, 3, 12]:
            straight_high = 3
        elif unique_values[-1] - unique_values[0] == 4:
            straight_high = unique_values[-1]

    if is_flush and straight_high is not None:
        if straight_high == RANK_VALUES['A']:
            score = (HAND_RANKINGS['royal_flush'], straight_high)
            return HandEvaluation('royal_flush', score, cards, (straight_high,))
        score = (HAND_RANKINGS['straight_flush'], straight_high)
        return HandEvaluation('straight_flush', score, cards, (straight_high,))

    if unique_counts[0][1] == 4:
        four = unique_counts[0][0]
        kicker = max([v for v in values if v != four])
        score = (HAND_RANKINGS['four_of_a_kind'], four, kicker)
        return HandEvaluation('four_of_a_kind', score, cards, (four, kicker))

    if unique_counts[0][1] == 3 and unique_counts[1][1] == 2:
        trips = unique_counts[0][0]
        pair = unique_counts[1][0]
        score = (HAND_RANKINGS['full_house'], trips, pair)
        return HandEvaluation('full_house', score, cards, (trips, pair))

    if is_flush:
        sorted_values = tuple(sorted(values, reverse=True))
        score = (HAND_RANKINGS['flush'],) + sorted_values
        return HandEvaluation('flush', score, cards, sorted_values)

    if straight_high is not None:
        score = (HAND_RANKINGS['straight'], straight_high)
        return HandEvaluation('straight', score, cards, (straight_high,))

    if unique_counts[0][1] == 3:
        trips = unique_counts[0][0]
        kickers = sorted([v for v in values if v != trips], reverse=True)
        score = (HAND_RANKINGS['three_of_a_kind'], trips) + tuple(kickers)
        return HandEvaluation('three_of_a_kind', score, cards, (trips, *kickers))

    if unique_counts[0][1] == 2 and unique_counts[1][1] == 2:
        pair_high = max(unique_counts[0][0], unique_counts[1][0])
        pair_low = min(unique_counts[0][0], unique_counts[1][0])
        kicker = max([v for v in values if v != pair_high and v != pair_low])
        score = (HAND_RANKINGS['two_pair'], pair_high, pair_low, kicker)
        return HandEvaluation('two_pair', score, cards, (pair_high, pair_low, kicker))

    if unique_counts[0][1] == 2:
        pair = unique_counts[0][0]
        kickers = sorted([v for v in values if v != pair], reverse=True)
        score = (HAND_RANKINGS['one_pair'], pair) + tuple(kickers)
        return HandEvaluation('one_pair', score, cards, (pair, *kickers))

    sorted_values = tuple(sorted(values, reverse=True))
    score = (HAND_RANKINGS['high_card'],) + sorted_values
    return HandEvaluation('high_card', score, cards, sorted_values)


def evaluate_cards(cards: Sequence[Tuple[str, str]]) -> HandEvaluation:
    """从7张牌中评估最佳5张组合"""
    best: Optional[HandEvaluation] = None
    for combo in combinations(cards, 5):
        evaluation = _classify_hand(combo)
        if not best or evaluation.score > best.score:
            best = evaluation
    return best


class TexasHoldemGame:
    """德州扑克核心逻辑"""

    PHASES = ["preflop", "flop", "turn", "river", "showdown"]

    def __init__(self, user_name: str, bet_amount: int, ai_count: int, difficulty: str, locale: str):
        self.bet_amount = bet_amount
        self.ai_count = ai_count
        self.difficulty = difficulty if difficulty in AI_FOLD_THRESHOLDS else "medium"
        self.locale = locale
        self.deck = self._create_deck()
        self.community_cards: List[Tuple[str, str]] = []
        self.players: List[TexasHoldemPlayer] = []
        self.phase_index = 0
        self.current_bet = min(DEFAULT_BIG_BLIND, bet_amount)
        self.pot = 0
        self.game_over = False
        self.ended_reason: Optional[str] = None
        self.started_at = datetime.datetime.now(datetime.timezone.utc)
        self.action_logs: List[dict] = []

        self._create_players(user_name)
        self._deal_hole_cards()
        self._post_blinds()

    def _create_deck(self) -> List[Tuple[str, str]]:
        deck = [(rank, suit) for rank in RANKS for suit in SUITS]
        random.shuffle(deck)
        return deck

    def _draw_cards(self, count: int) -> List[Tuple[str, str]]:
        if len(self.deck) < count:
            raise RuntimeError("牌堆已空，无法继续游戏")
        drawn = [self.deck.pop() for _ in range(count)]
        return drawn

    def _create_players(self, user_name: str) -> None:
        human = TexasHoldemPlayer(name=user_name, is_human=True, stack=self.bet_amount)
        self.players.append(human)
        for index in range(1, self.ai_count + 1):
            ai_name = t("texas_holdem.ai.default_name", locale=self.locale).format(index=index)
            ai_player = TexasHoldemPlayer(
                name=ai_name,
                is_human=False,
                stack=self.bet_amount,
                difficulty=self.difficulty
            )
            self.players.append(ai_player)

    def _deal_hole_cards(self) -> None:
        for _ in range(2):
            for player in self.players:
                player.hole_cards.append(self._draw_cards(1)[0])

    def _post_blinds(self) -> None:
        """只让小盲和大盲投入筹码，避免玩家默认全下"""
        ai_players = self.players[1:]
        if ai_players:
            small_blind_player = ai_players[0]
            big_blind_player = ai_players[1] if len(ai_players) > 1 else self.player
        else:
            small_blind_player = self.player
            big_blind_player = self.player

        self._apply_blind(small_blind_player, DEFAULT_BIG_BLIND // 2)
        self._apply_blind(big_blind_player, DEFAULT_BIG_BLIND)
        self.current_bet = min(DEFAULT_BIG_BLIND, big_blind_player.contribution)

        for player in self.players:
            if player not in (small_blind_player, big_blind_player) and player.stack > 0:
                player.last_action = t("texas_holdem.actions.call", locale=self.locale)

    def _apply_blind(self, player: TexasHoldemPlayer, amount: int) -> None:
        actual = player.invest(min(amount, player.stack))
        if actual <= 0:
            return
        self.pot += actual
        player.last_action = t("texas_holdem.actions.post_blind", locale=self.locale)
        self._record_action("human" if player.is_human else "ai", "call", actual, self.current_phase)

    @property
    def player(self) -> TexasHoldemPlayer:
        return self.players[0]

    @property
    def current_phase(self) -> str:
        return self.PHASES[self.phase_index]

    def can_raise(self) -> bool:
        return not self.game_over and self.player.stack >= MIN_RAISE

    def can_all_in(self) -> bool:
        return not self.game_over and self.player.stack > 0

    def can_check(self) -> bool:
        return not self.game_over

    def player_fold(self) -> None:
        self.player.folded = True
        self.player.last_action = t("texas_holdem.actions.folded", locale=self.locale)
        self._record_action("human", "fold", None, self.current_phase)
        self.game_over = True
        self.ended_reason = "player_fold"

    def player_raise(self, amount: int) -> int:
        if not self.can_raise():
            return 0
        actual = self.player.invest(amount)
        if actual <= 0:
            return 0
        self.player.last_action = t("texas_holdem.actions.raise", locale=self.locale).format(amount=actual)
        self.pot += actual
        self.current_bet = self.player.contribution
        self._ai_react_to_raise(actual, is_all_in=False)
        self._record_action("human", "raise", actual, self.current_phase)
        return actual

    def player_all_in(self) -> int:
        if not self.can_all_in():
            return 0
        actual = self.player.invest(self.player.stack)
        self.player.last_action = t("texas_holdem.actions.all_in", locale=self.locale)
        self.pot += actual
        self.current_bet = self.player.contribution
        self._ai_react_to_raise(actual, is_all_in=True)
        self._record_action("human", "all_in", actual, self.current_phase)
        self._reveal_remaining_board()
        self.game_over = True
        self.ended_reason = "all_in"
        return actual

    def _reveal_remaining_board(self) -> None:
        remaining = 5 - len(self.community_cards)
        if remaining > 0:
            self.community_cards.extend(self._draw_cards(remaining))
        self.phase_index = len(self.PHASES) - 1
        for player in self.active_players():
            player.best_hand = evaluate_cards(player.hole_cards + self.community_cards)

    def player_check_or_call(self) -> None:
        if self.phase_index >= len(self.PHASES) - 1:
            self.game_over = True
            self.ended_reason = "showdown"
            for player in self.active_players():
                player.best_hand = evaluate_cards(player.hole_cards + self.community_cards)
            return
        self._advance_phase()
        self._record_action("human", "check", None, self.current_phase)
        self._ai_post_phase_logic()

    def _advance_phase(self) -> None:
        if self.current_phase == "preflop":
            self.community_cards.extend(self._draw_cards(3))
        elif self.current_phase in {"flop", "turn"}:
            self.community_cards.extend(self._draw_cards(1))
        if self.phase_index < len(self.PHASES) - 1:
            self.phase_index += 1

    def _ai_react_to_raise(self, amount: int, is_all_in: bool) -> None:
        for ai in self.players[1:]:
            if ai.folded:
                continue
            strength = self._estimate_ai_strength(ai)

            threshold = AI_FOLD_THRESHOLDS[self.difficulty].get(self.current_phase, 4.5)

            # 大额加注/All-in 提升恐惧系数
            bet_pressure = amount / max(1, ai.stack + ai.contribution)
            fear_factor = 0.2 if is_all_in else min(0.15, bet_pressure * 0.4)
            fold_base = max(0.05, (threshold - strength) / 10 + fear_factor)

            # 底池赔率：下注相对底池越便宜，越愿意跟注
            pot_odds = self.pot / max(1, amount)
            fold_base -= min(0.1, pot_odds * 0.02)

            if random.random() < fold_base:
                ai.folded = True
                ai.last_action = t("texas_holdem.actions.folded", locale=self.locale)
                self._record_action("ai", "fold", None, self.current_phase)
            else:
                self._ai_call(ai)
        self._check_ai_folded()

    def _ai_call_current_bet(self) -> None:
        for ai in self.players[1:]:
            if ai.folded:
                continue
            self._ai_call(ai)

    def _ai_call(self, ai: TexasHoldemPlayer) -> None:
        if ai.contribution >= self.current_bet:
            return
        required = max(0, self.current_bet - ai.contribution)
        invest = ai.invest(required)
        self.pot += invest
        if invest > 0:
            ai.last_action = t("texas_holdem.actions.call", locale=self.locale)
            self._record_action("ai", "call", invest, self.current_phase)

    def _ai_post_phase_logic(self) -> None:
        for ai in self.players[1:]:
            if ai.folded:
                continue
            strength = self._estimate_ai_strength(ai)
            threshold = AI_FOLD_THRESHOLDS[self.difficulty].get(self.current_phase, 4.5)
            if random.random() < max(0, (threshold - strength) / 12):
                ai.folded = True
                ai.last_action = t("texas_holdem.actions.folded", locale=self.locale)
                self._record_action("ai", "fold", None, self.current_phase)
        self._check_ai_folded()

    def _estimate_ai_strength(self, ai: TexasHoldemPlayer) -> float:
        if self.current_phase == "preflop":
            return _estimate_starting_strength(ai.hole_cards)
        if len(self.community_cards) < 3:
            return _estimate_starting_strength(ai.hole_cards)
        cards = ai.hole_cards + self.community_cards
        ai.best_hand = evaluate_cards(cards)
        base = ai.best_hand.score[0]
        kickers = sum(ai.best_hand.kicker) / (len(ai.best_hand.kicker) or 1)
        return base + kickers / 15

    def _check_ai_folded(self) -> None:
        if not any(not ai.folded for ai in self.players[1:]):
            self.game_over = True
            self.ended_reason = "ai_fold"
            self._reveal_remaining_board()

    def _record_action(self, player_type: str, action: str, amount: Optional[int], phase: str) -> None:
        self.action_logs.append({
            "player_type": player_type,
            "action": action,
            "amount": amount,
            "game_phase": phase,
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        })

    def active_players(self) -> List[TexasHoldemPlayer]:
        return [player for player in self.players if not player.folded]

    def determine_winners(self) -> Tuple[List[TexasHoldemPlayer], Optional[HandEvaluation]]:
        contenders = [p for p in self.players if not p.folded]
        if not contenders:
            return [], None
        for player in contenders:
            if not player.best_hand and len(self.community_cards) >= 3:
                player.best_hand = evaluate_cards(player.hole_cards + self.community_cards)
        best_score = None
        winners: List[TexasHoldemPlayer] = []
        for player in contenders:
            if not player.best_hand:
                continue
            if not best_score or player.best_hand.score > best_score:
                winners = [player]
                best_score = player.best_hand.score
            elif player.best_hand.score == best_score:
                winners.append(player)
        reference = winners[0].best_hand if winners and winners[0].best_hand else None
        return winners, reference

    def calculate_player_payout(self, winners: List[TexasHoldemPlayer]) -> Tuple[int, str]:
        payout = self.player.stack
        result_type = "lose"
        if self.player in winners:
            share = self.pot // max(1, len(winners))
            remainder = self.pot % max(1, len(winners))
            payout += share
            if remainder and winners.index(self.player) == 0:
                payout += remainder
            if len(winners) == 1:
                result_type = "win"
            else:
                result_type = "tie"
        else:
            result_type = "lose" if self.player.folded else "lose"
        return payout, result_type

    def settle(self) -> dict:
        winners, reference_hand = self.determine_winners()
        payout, result_type = self.calculate_player_payout(winners) if self.game_over else (self.player.stack, "lose")
        return {
            "winners": winners,
            "reference_hand": reference_hand,
            "payout": payout,
            "result_type": result_type
        }

    def build_embed(
        self,
        locale: str,
        reveal_all: bool = False,
        result: Optional[dict] = None,
        action_text: Optional[str] = None
    ) -> discord.Embed:
        embed = discord.Embed(
            title=t("texas_holdem.embed.title", locale=locale),
            color=discord.Color(0x1E88E5)
        )
        embed.add_field(
            name=t("texas_holdem.embed.pot", locale=locale),
            value=_format_points(locale, self.pot),
            inline=True
        )
        embed.add_field(
            name=t("texas_holdem.embed.current_bet", locale=locale),
            value=_format_points(locale, self.current_bet),
            inline=True
        )
        embed.add_field(
            name=t("texas_holdem.embed.phase", locale=locale),
            value=t(f"texas_holdem.phases.{self.current_phase}", locale=locale),
            inline=True
        )

        embed.add_field(
            name=t("texas_holdem.embed.player_field", locale=locale),
            value=self._format_player_block(self.player, locale, reveal=True),
            inline=False
        )

        embed.add_field(
            name=t("texas_holdem.embed.ai_field", locale=locale),
            value=self._format_ai_section(locale, reveal_all or bool(result)),
            inline=False
        )

        embed.add_field(
            name=t("texas_holdem.embed.community", locale=locale),
            value=self._format_community_cards(locale, reveal_all or bool(result)),
            inline=False
        )

        if result:
            result_text = result.get("text")
            embed.add_field(
                name=t("texas_holdem.results.title", locale=locale),
                value=result_text,
                inline=False
            )
            embed.color = discord.Color.green() if result.get("result_key") == "win" else discord.Color.red()
        else:
            embed.add_field(
                name=t("texas_holdem.embed.action_label", locale=locale),
                value=action_text or t("texas_holdem.embed.default_action", locale=locale),
                inline=False
            )
        return embed

    def _format_player_block(self, player: TexasHoldemPlayer, locale: str, reveal: bool) -> str:
        emoji = "👤" if player.is_human else "🤖"
        line = t("texas_holdem.embed.player_line", locale=locale).format(
            emoji=emoji,
            name=player.name,
            points=_format_points(locale, player.stack)
        )
        if player.contribution:
            bet_text = t("texas_holdem.embed.bet_value", locale=locale).format(
                amount=_format_points(locale, player.contribution)
            )
            line = f"{line} ({bet_text})"
        cards = " ".join(_format_card(card) for card in player.hole_cards) if reveal else "🎴 🎴"
        cards_line = t("texas_holdem.embed.cards_line", locale=locale).format(cards=cards)
        status_key = "folded" if player.folded else "thinking"
        if player.stack == 0 and not player.folded:
            status_key = "all_in"
        status = t(f"texas_holdem.embed.status.{status_key}", locale=locale)
        status_line = t("texas_holdem.embed.status_line", locale=locale).format(status=status)
        return "\n".join([line, cards_line, status_line])

    def _format_ai_section(self, locale: str, reveal: bool) -> str:
        ai_blocks = [
            self._format_player_block(player, locale, reveal)
            for player in self.players[1:]
        ]
        if not ai_blocks:
            return t("texas_holdem.embed.no_ai", locale=locale)
        return "\n\n".join(ai_blocks)

    def _format_community_cards(self, locale: str, reveal: bool) -> str:
        if not self.community_cards:
            return t("texas_holdem.embed.community_unknown", locale=locale)
        cards = " ".join(_format_card(card) for card in self.community_cards)
        remaining = 5 - len(self.community_cards)
        if remaining > 0 and not reveal:
            cards = f"{cards} " + " ".join("🎴" for _ in range(remaining))
        return cards


class TexasHoldemView(discord.ui.View):
    """交互式德州扑克控制面板"""

    def __init__(
        self,
        game: TexasHoldemGame,
        user_id: int,
        guild_id: int,
        user_internal_id: int,
        locale: str
    ):
        super().__init__(timeout=180)
        self.game = game
        self.user_id = user_id
        self.guild_id = guild_id
        self.user_internal_id = user_internal_id
        self.locale = locale
        self.message: Optional[discord.Message] = None
        self.finished = False
        self.action_text = t("texas_holdem.actions.start", locale=locale)
        self._set_button_labels()

    def _set_action_text(self, key: str, **kwargs) -> None:
        self.action_text = t(f"texas_holdem.actions.{key}", locale=self.locale, **kwargs)

    def _build_embed(self, reveal_all: bool = False, result: Optional[dict] = None) -> discord.Embed:
        return self.game.build_embed(
            self.locale,
            reveal_all=reveal_all,
            result=result,
            action_text=None if result else self.action_text
        )

    def _sync_button_states(self) -> None:
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if child.custom_id == "raise_button":
                child.disabled = not self.game.can_raise()
            elif child.custom_id == "all_in_button":
                child.disabled = not self.game.can_all_in()
            elif child.custom_id in {"fold_button", "check_button"}:
                child.disabled = self.game.game_over or self.finished

    def _set_button_labels(self) -> None:
        """根据语言设置按钮文本"""
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if child.custom_id == "fold_button":
                child.label = t("texas_holdem.buttons.fold", locale=self.locale)
            elif child.custom_id == "check_button":
                child.label = t("texas_holdem.buttons.check", locale=self.locale)
            elif child.custom_id == "raise_button":
                child.label = t("texas_holdem.buttons.raise", locale=self.locale)
            elif child.custom_id == "all_in_button":
                child.label = t("texas_holdem.buttons.all_in", locale=self.locale)

    async def on_timeout(self) -> None:
        if self.finished:
            return
        self.game.player_fold()
        result = self._build_result_payload(timeout=True)
        await self._finalize_message(result, reason="timeout")

    async def _finalize_message(self, result_payload: dict, reason: str) -> None:
        self.finished = True
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        embed = self._build_embed(reveal_all=True, result=result_payload)
        if self.message:
            await self.message.edit(embed=embed, view=self)
        else:
            # 安全降级：若message未设置，直接忽略
            pass
        await self._settle_points(result_payload.get("payout", 0), result_payload.get("result_key", "lose"), reason)

    async def _settle_points(self, payout: int, result_key: str, reason: str) -> None:
        try:
            net_change = payout
            if net_change:
                await UserCache.update_points(
                    self.guild_id,
                    self.user_id,
                    self.user_internal_id,
                    net_change
                )
        except Exception as exc:
            print(f"德州扑克结算失败: {exc}")

        try:
            self._save_game_record(payout, result_key, reason)
        except Exception as exc:
            print(f"保存德州扑克记录失败: {exc}")

    def _save_game_record(self, payout: int, result_key: str, reason: str) -> None:
        supabase = get_connection()
        duration = int((datetime.datetime.now(datetime.timezone.utc) - self.game.started_at).total_seconds())
        player_cards = [_format_card(card) for card in self.game.player.hole_cards]
        community = [_format_card(card) for card in self.game.community_cards]
        record_data = {
            "user_id": self.user_internal_id,
            "ai_count": self.game.ai_count,
            "ai_difficulty": self.game.difficulty,
            "starting_chips": self.game.bet_amount,
            "final_chips": payout,
            "hole_cards": json.dumps(player_cards),
            "community_cards": json.dumps(community),
            "result": result_key,
            "profit": payout - self.game.bet_amount,
            "game_duration": duration,
            "ended_reason": reason
        }
        try:
            insert_result = supabase.table("texas_holdem_games").insert(record_data).execute()
            game_id = insert_result.data[0]["id"] if insert_result.data else None

            # 保存行动日志
            if game_id and self.game.action_logs:
                action_rows = []
                for log in self.game.action_logs:
                    action_rows.append({
                        "game_id": game_id,
                        "player_type": log["player_type"],
                        "action": log["action"],
                        "amount": log["amount"],
                        "game_phase": log["game_phase"],
                        "created_at": log["recorded_at"]
                    })
                supabase.table("texas_players_actions").insert(action_rows).execute()
        except Exception as exc:
            print(f"记录德州扑克失败: {exc}")

    def _build_result_payload(self, timeout: bool = False) -> dict:
        if timeout and not self.game.game_over:
            self.game.player_fold()
        settlement = self.game.settle()
        winners = settlement.get("winners", [])
        payout = settlement.get("payout", 0)
        reference = settlement.get("reference_hand")
        result_key = "lose"
        if timeout:
            result_key = "timeout"
        elif self.game.player in winners:
            result_key = "win" if len(winners) == 1 else "tie"
        else:
            result_key = "fold" if self.game.player.folded else "lose"

        if reference:
            hand_desc = _describe_hand(reference.rank_name, self.locale)
        else:
            hand_desc = t("texas_holdem.results.default_hand", locale=self.locale)

        if result_key == "win":
            text = t("texas_holdem.results.win", locale=self.locale).format(amount=payout - self.game.bet_amount, hand=hand_desc)
        elif result_key == "tie":
            text = t("texas_holdem.results.tie", locale=self.locale).format(amount=payout - self.game.bet_amount, hand=hand_desc)
        elif result_key == "timeout":
            text = t("texas_holdem.results.timeout", locale=self.locale)
        elif result_key == "fold":
            text = t("texas_holdem.results.fold", locale=self.locale)
        else:
            text = t("texas_holdem.results.lose", locale=self.locale)

        return {
            "text": text,
            "payout": payout,
            "result_key": result_key
        }

    async def _validate_user(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                t("texas_holdem.messages.not_your_game", locale=self.locale),
                ephemeral=True
            )
            return False
        if self.finished or self.game.game_over:
            await interaction.response.send_message(
                t("texas_holdem.messages.game_already_finished", locale=self.locale),
                ephemeral=True
            )
            return False
        return True

    async def _refresh_message(self, interaction: discord.Interaction) -> None:
        embed = self._build_embed()
        self._sync_button_states()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="❌", custom_id="fold_button")
    async def fold_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user(interaction):
            return
        self.game.player_fold()
        result = self._build_result_payload()
        self._sync_button_states()
        await interaction.response.edit_message(embed=self._build_embed(reveal_all=True, result=result), view=self)
        await self._settle_points(result.get("payout", 0), result.get("result_key", "lose"), "fold")
        self.finished = True
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="✅", custom_id="check_button")
    async def check_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user(interaction):
            return
        self.game.player_check_or_call()
        if self.game.game_over:
            result = self._build_result_payload()
            self._sync_button_states()
            await interaction.response.edit_message(embed=self._build_embed(reveal_all=True, result=result), view=self)
            await self._settle_points(result.get("payout", 0), result.get("result_key", "lose"), "showdown")
            self.finished = True
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            return
        self._set_action_text("prompt")
        await self._refresh_message(interaction)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="📈", custom_id="raise_button")
    async def raise_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user(interaction):
            return
        if not self.game.can_raise():
            await interaction.response.send_message(
                t("texas_holdem.messages.cannot_raise", locale=self.locale),
                ephemeral=True
            )
            return
        invested = self.game.player_raise(MIN_RAISE)
        if invested <= 0:
            await interaction.response.send_message(
                t("texas_holdem.messages.raise_failed", locale=self.locale),
                ephemeral=True
            )
            return
        if self.game.game_over:
            result = self._build_result_payload()
            self._sync_button_states()
            await interaction.response.edit_message(embed=self._build_embed(reveal_all=True, result=result), view=self)
            await self._settle_points(result.get("payout", 0), result.get("result_key", "lose"), "ai_fold")
            self.finished = True
            for child in self.children:
                child.disabled = True
            return
        self._set_action_text("prompt")
        await self._refresh_message(interaction)

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="💎", custom_id="all_in_button")
    async def all_in_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validate_user(interaction):
            return
        if not self.game.can_all_in():
            await interaction.response.send_message(
                t("texas_holdem.messages.cannot_all_in", locale=self.locale),
                ephemeral=True
            )
            return
        self.game.player_all_in()
        result = self._build_result_payload()
        self._sync_button_states()
        await interaction.response.edit_message(embed=self._build_embed(reveal_all=True, result=result), view=self)
        await self._settle_points(result.get("payout", 0), result.get("result_key", "lose"), "all_in")
        self.finished = True
        for child in self.children:
            child.disabled = True


@app_commands.command(name="texas_holdem", description="Play a Texas Hold'em game against AI")
@app_commands.describe(
    bet="Bet amount or 'all' to go all-in with your points",
    ai="Number of AI opponents (1-3)",
    difficulty="AI difficulty"
)
@app_commands.choices(
    difficulty=[
        app_commands.Choice(name="Easy 简单", value="easy"),
        app_commands.Choice(name="Medium 标准", value="medium"),
        app_commands.Choice(name="Hard 困难", value="hard")
    ]
)
@app_commands.guild_only()
async def texas_holdem(
    interaction: discord.Interaction,
    bet: str,
    ai: app_commands.Range[int, 1, 3] = 2,
    difficulty: Optional[app_commands.Choice[str]] = None
):
    supabase = get_connection()
    locale = get_guild_locale(interaction.guild.id)
    difficulty_value = difficulty.value if difficulty else "medium"

    user_internal_id = get_user_internal_id_with_guild_and_discord_id(
        interaction.guild.id,
        interaction.user.id
    )

    if not user_internal_id:
        try:
            response = supabase.table('users').insert({
                'guild_id': interaction.guild.id,
                'discord_user_id': interaction.user.id,
                'points': 0,
                'last_draw_date': None,
                'paid_draws_today': 0,
                'last_paid_draw_date': '1970-01-01',
                'equipped_pet_id': None,
                'last_pet_points_update': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
            }).execute()
            user_internal_id = response.data[0]['id']
        except Exception as exc:
            print(f"创建用户失败: {exc}")
            await interaction.response.send_message(
                t("texas_holdem.messages.user_fetch_failed", locale=locale),
                ephemeral=True
            )
            return

    try:
        user_result = supabase.table('users').select('points').eq('id', user_internal_id).execute()
        if not user_result.data:
            await interaction.response.send_message(
                t("texas_holdem.messages.user_fetch_failed", locale=locale),
                ephemeral=True
            )
            return
        current_points = user_result.data[0]['points']
    except Exception as exc:
        print(f"查询积分失败: {exc}")
        await interaction.response.send_message(
            t("texas_holdem.messages.user_fetch_failed", locale=locale),
            ephemeral=True
        )
        return

    if bet.lower() == "all":
        bet_amount = current_points
    else:
        try:
            bet_amount = int(bet)
        except ValueError:
            await interaction.response.send_message(
                t("texas_holdem.messages.invalid_bet", locale=locale),
                ephemeral=True
            )
            return

    if bet_amount <= 0:
        await interaction.response.send_message(
            t("texas_holdem.messages.invalid_bet", locale=locale),
            ephemeral=True
        )
        return

    if current_points < bet_amount:
        await interaction.response.send_message(
            t("texas_holdem.messages.not_enough_points", locale=locale).format(
                current=current_points,
                required=bet_amount
            ),
            ephemeral=True
        )
        return

    try:
        await UserCache.update_points(
            interaction.guild.id,
            interaction.user.id,
            user_internal_id,
            -bet_amount
        )
    except Exception as exc:
        print(f"扣除积分失败: {exc}")
        await interaction.response.send_message(
            t("texas_holdem.messages.deduct_failed", locale=locale),
            ephemeral=True
        )
        return

    game = TexasHoldemGame(
        user_name=interaction.user.display_name,
        bet_amount=bet_amount,
        ai_count=ai,
        difficulty=difficulty_value,
        locale=locale
    )
    view = TexasHoldemView(
        game=game,
        user_id=interaction.user.id,
        guild_id=interaction.guild.id,
        user_internal_id=user_internal_id,
        locale=locale
    )

    embed = game.build_embed(locale, action_text=view.action_text)
    view._sync_button_states()
    await interaction.response.send_message(embed=embed, view=view)
    view.message = await interaction.original_response()


@app_commands.command(name="texas_holdem_stats", description="View your Texas Hold'em statistics")
@app_commands.guild_only()
async def texas_holdem_stats_command(interaction: discord.Interaction):
    """查看德州扑克统计"""
    supabase = get_connection()
    locale = get_guild_locale(interaction.guild.id)

    user_internal_id = get_user_internal_id_with_guild_and_discord_id(
        interaction.guild.id,
        interaction.user.id
    )

    if not user_internal_id:
        await interaction.response.send_message(
            t("texas_holdem.stats.no_user_found", locale=locale),
            ephemeral=True
        )
        return

    try:
        games_result = supabase.table("texas_holdem_games") \
            .select("*") \
            .eq("user_id", user_internal_id) \
            .execute()

        games = games_result.data or []
        if not games:
            await interaction.response.send_message(
                t("texas_holdem.stats.no_games", locale=locale),
                ephemeral=True
            )
            return

        total_games = len(games)
        wins = sum(1 for g in games if g.get("result") == "win")
        losses = sum(1 for g in games if g.get("result") == "lose")
        ties = sum(1 for g in games if g.get("result") == "tie")

        win_rate = (wins / total_games * 100) if total_games else 0
        tie_rate = (ties / total_games * 100) if total_games else 0
        loss_rate = (losses / total_games * 100) if total_games else 0

        total_profit = sum(g.get("profit", 0) for g in games)
        max_win = max((g.get("profit", 0) for g in games if g.get("profit", 0) > 0), default=0)
        max_loss = min((g.get("profit", 0) for g in games if g.get("profit", 0) < 0), default=0)

        avg_start = sum(g.get("starting_chips", 0) for g in games) / total_games if total_games else 0
        avg_final = sum(g.get("final_chips", 0) or 0 for g in games) / total_games if total_games else 0

        embed = discord.Embed(
            title=t("texas_holdem.stats.title", locale=locale),
            description=t("texas_holdem.stats.description", locale=locale).format(user=interaction.user.display_name),
            color=discord.Color(0x1E88E5)
        )

        embed.add_field(
            name=t("texas_holdem.stats.basic_stats", locale=locale),
            value="\n".join([
                t("texas_holdem.stats.total_games", locale=locale).format(count=total_games),
                t("texas_holdem.stats.wins", locale=locale).format(count=wins, rate=win_rate),
                t("texas_holdem.stats.losses", locale=locale).format(count=losses, rate=loss_rate),
                t("texas_holdem.stats.ties", locale=locale).format(count=ties, rate=tie_rate)
            ]),
            inline=False
        )

        profit_emoji = "📈" if total_profit >= 0 else "📉"
        profit_text = f"+{total_profit}" if total_profit >= 0 else str(total_profit)
        embed.add_field(
            name=t("texas_holdem.stats.points_stats", locale=locale),
            value="\n".join([
                t("texas_holdem.stats.total_profit", locale=locale).format(amount=profit_text, emoji=profit_emoji),
                t("texas_holdem.stats.max_win", locale=locale).format(amount=max_win),
                t("texas_holdem.stats.max_loss", locale=locale).format(amount=max_loss),
                t("texas_holdem.stats.avg_start", locale=locale).format(amount=avg_start),
                t("texas_holdem.stats.avg_final", locale=locale).format(amount=avg_final)
            ]),
            inline=False
        )

        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text=t("texas_holdem.stats.footer", locale=locale))

        await interaction.response.send_message(embed=embed)
    except Exception as exc:
        print(f"查询Texas统计失败: {exc}")
        await interaction.response.send_message(
            t("texas_holdem.stats.query_failed", locale=locale),
            ephemeral=True
        )



def setup(bot):
    bot.tree.add_command(texas_holdem)
    bot.tree.add_command(texas_holdem_stats_command)
