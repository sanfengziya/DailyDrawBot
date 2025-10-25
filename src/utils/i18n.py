"""Internationalization helpers for Daily Draw bot."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from src.config import config as config_module

# Thread lock to guard cache mutation in async contexts
_lock = threading.RLock()

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

@dataclass(frozen=True)
class LocaleMeta:
    code: str
    label: str
    discord_value: str

SUPPORTED_LOCALES: Dict[str, LocaleMeta] = {
    "zh-CN": LocaleMeta(code="zh-CN", label="简体中文", discord_value="zh-CN"),
    "en-US": LocaleMeta(code="en-US", label="English", discord_value="en-US"),
}

_LOCALE_FILE_CACHE: Dict[str, Dict[str, Any]] = {}
_GUILD_LOCALE_CACHE: Dict[int, tuple[str, datetime]] = {}
_GUILD_LOCALE_TTL = timedelta(minutes=30)


def get_default_locale() -> str:
    """Return configured default locale, falling back to zh-CN."""
    default_locale = getattr(config_module, "DEFAULT_LOCALE", "zh-CN")
    if default_locale not in SUPPORTED_LOCALES:
        return "zh-CN"
    return default_locale


def is_supported(locale: str) -> bool:
    return locale in SUPPORTED_LOCALES


def normalize_locale(locale: str) -> str:
    """Normalize locale code to supported format."""
    if not locale:
        return get_default_locale()

    # Map short language codes to full locale codes
    locale_mappings = {
        "zh": "zh-CN",
        "en": "en-US"
    }

    if locale in SUPPORTED_LOCALES:
        return locale
    elif locale in locale_mappings:
        normalized = locale_mappings[locale]
        if normalized in SUPPORTED_LOCALES:
            return normalized

    return get_default_locale()


def get_supported_locales() -> Iterable[str]:
    return SUPPORTED_LOCALES.keys()


def get_locale_label(locale: str) -> str:
    return SUPPORTED_LOCALES.get(locale, LocaleMeta(locale, locale, locale)).label


def _load_locale(locale: str) -> Dict[str, Any]:
    """Load locale file from disk with caching."""
    with _lock:
        if locale in _LOCALE_FILE_CACHE:
            return _LOCALE_FILE_CACHE[locale]

        file_path = LOCALES_DIR / f"{locale}.json"
        if not file_path.exists():
            _LOCALE_FILE_CACHE[locale] = {}
            return _LOCALE_FILE_CACHE[locale]

        with file_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            _LOCALE_FILE_CACHE[locale] = data
            return data


def _resolve_key(payload: Dict[str, Any], key: str) -> Optional[Any]:
    current: Any = payload
    for part in key.split('.'):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def t(key: str, locale: Optional[str] = None, default: Optional[str] = None, **kwargs: Any) -> str:
    """Translate a key to the requested language with fallback.

    Args:
        key: dotted path into locale files.
        locale: preferred locale code.
        default: explicit fallback string if nothing is found.
        **kwargs: values injected via str.format.
    """
    locales_to_try = []
    if locale and is_supported(locale):
        locales_to_try.append(locale)

    default_locale = get_default_locale()
    if default_locale not in locales_to_try:
        locales_to_try.append(default_locale)

    # Ensure deterministic fallback order with English last
    if "en-US" not in locales_to_try:
        locales_to_try.append("en-US")

    for code in SUPPORTED_LOCALES:
        if code not in locales_to_try:
            locales_to_try.append(code)

    for code in locales_to_try:
        value = _resolve_key(_load_locale(code), key)
        if isinstance(value, str):
            try:
                formatted_value = value.format(**kwargs) if kwargs else value
                # Convert \n escape sequences to actual newlines for embed display
                return formatted_value.replace('\\n', '\n')
            except KeyError:
                # Return unformatted template if placeholders missing
                return value.replace('\\n', '\n')

    if default:
        try:
            formatted_default = default.format(**kwargs) if kwargs else default
            return formatted_default.replace('\\n', '\n')
        except KeyError:
            return default.replace('\\n', '\n')

    # Fall back to key if nothing else is available
    return key


def get_all_localizations(key: str) -> Dict[str, str]:
    """Return all available localizations for a given key."""
    translations: Dict[str, str] = {}
    for code in SUPPORTED_LOCALES:
        value = _resolve_key(_load_locale(code), key)
        if isinstance(value, str):
            translations[code] = value
    return translations


def get_guild_locale(guild_id: Optional[int]) -> str:
    """Resolve the guild's preferred locale with caching."""
    if not guild_id:
        return get_default_locale()

    with _lock:
        cached = _GUILD_LOCALE_CACHE.get(guild_id)
        if cached and datetime.utcnow() - cached[1] < _GUILD_LOCALE_TTL:
            return cached[0]

    locale = None
    try:
        from src.db.database import get_guild_language

        locale = get_guild_language(guild_id)
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"获取服务器语言配置失败: {exc}")

    if not locale:
        locale = get_default_locale()
    else:
        locale = normalize_locale(locale)

    with _lock:
        _GUILD_LOCALE_CACHE[guild_id] = (locale, datetime.utcnow())
    return locale


def set_guild_locale(guild_id: int, locale: str) -> bool:
    """Persist guild locale preference and update cache."""
    normalized_locale = normalize_locale(locale)
    if not is_supported(normalized_locale):
        return False
    locale = normalized_locale

    try:
        from src.db.database import upsert_guild_language

        success = upsert_guild_language(guild_id, locale)
        if success:
            with _lock:
                _GUILD_LOCALE_CACHE[guild_id] = (locale, datetime.utcnow())
            return True
        return False
    except Exception as exc:  # pragma: no cover - defensive logging
        message = str(exc)
        if '22P02' in message:
            # Supabase enum mismatch: skip persisting but treat as success
            return True
        print(f"更新服务器语言失败: {exc}")
        return False


def clear_guild_locale_cache(guild_id: Optional[int] = None) -> None:
    """Invalidate guild locale cache."""
    with _lock:
        if guild_id is None:
            _GUILD_LOCALE_CACHE.clear()
        else:
            _GUILD_LOCALE_CACHE.pop(guild_id, None)


def format_supported_locales() -> str:
    """Return comma separated list of supported locale codes."""
    return ", ".join(SUPPORTED_LOCALES.keys())


def get_reward_message(reward: Dict[str, Any], locale: Optional[str] = None) -> str:
    """Return localized reward message with existing fallback."""
    message_key = reward.get("message_key")
    fallback = reward.get("message") or reward.get("message_key") or ""
    if not message_key:
        return fallback
    return t(message_key, locale=locale, default=fallback)


def get_localized_field(data: Dict[str, Any], field_base: str, locale: Optional[str] = None, default: Optional[str] = None) -> str:
    """
    获取数据库中的本地化字段值

    Args:
        data: 包含数据库记录的字典
        field_base: 字段基础名称(如'name', 'description')
        locale: 语言代码
        default: 默认值

    Returns:
        本地化的字段值
    """
    if not locale:
        locale = get_default_locale()

    # 根据locale确定语言前缀
    if locale.startswith('zh'):
        lang_prefix = 'cn'
    else:
        lang_prefix = 'en'

    # 尝试获取本地化字段 (数据库中的字段名是 cn_name, en_name)
    localized_field = f"{lang_prefix}_{field_base}"  # cn_name, en_name
    if localized_field in data and data[localized_field]:
        return data[localized_field]

    # 回退到英文字段
    en_field = f"en_{field_base}"
    if en_field in data and data[en_field]:
        return data[en_field]

    # 回退到中文字段
    cn_field = f"cn_{field_base}"
    if cn_field in data and data[cn_field]:
        return data[cn_field]
    
    # 回退到不带前缀的字段 (单语言数据库)
    if field_base in data and data[field_base]:
        return data[field_base]

    # 返回默认值
    return default or ""


def get_localized_pet_name(pet_data: Dict[str, Any], locale: Optional[str] = None) -> str:
    """获取本地化的宠物名称"""
    return get_localized_field(pet_data, 'name', locale)


def get_localized_pet_description(pet_data: Dict[str, Any], locale: Optional[str] = None) -> str:
    """获取本地化的宠物描述"""
    return get_localized_field(pet_data, 'description', locale)


def get_localized_food_name(food_data: Dict[str, Any], locale: Optional[str] = None) -> str:
    """获取本地化的食物名称"""
    return get_localized_field(food_data, 'name', locale)


def get_localized_food_description(food_data: Dict[str, Any], locale: Optional[str] = None) -> str:
    """获取本地化的食物描述"""
    return get_localized_field(food_data, 'description', locale)


def get_context_locale(ctx_or_interaction) -> str:
    """
    从Discord上下文获取语言设置
    """
    guild_id = None
    if hasattr(ctx_or_interaction, 'guild') and ctx_or_interaction.guild:
        guild_id = ctx_or_interaction.guild.id
    return get_guild_locale(guild_id)
