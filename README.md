# Daily Draw Bot

**🌐 Language:** [English](README.md) | [中文](README_ZH.md)

A feature-rich Discord multi-functional bot with daily lottery, complete pet raising system, multiple shops, quiz games, and points economy system.

## 🌟 Core Features

### 🎰 Economy System
- **Daily Lottery System** - Free 1 draw + 30 paid draws daily mechanism
- **Points Management** - Complete points gifting, transfer, and management system
- **Leaderboards** - Real-time points ranking and wealth statistics

### 🐾 Pet Raising System
- **Pet Egg System** - Multi-rarity pet egg drawing (C/R/SR/SSR)
- **Pet Management** - Feeding, upgrading, equipping, and interaction system
- **Fragment Forge** - Pet fragment collection and synthesis mechanism
- **Star Evolution** - Pet star upgrading and attribute growth system

### 🛍️ Shop System
- **Role Shop** - Discord role purchasing and management
- **Item Shop** - Consumables and props shop
- **Subscription System** - Premium features and privilege subscriptions

### 🎮 Game System
- **Quiz Game** - Educational quiz game with multi-category question bank
- **Probability System** - Fair random reward mechanism

### 🌍 Multi-language Support
- **Internationalization** - Supports Chinese (zh-CN) and English (en-US)
- **Dynamic Switching** - Admins can switch server language in real-time

## 🏗️ Technical Architecture

### Tech Stack
- **Python 3.12+** - Main programming language
- **Discord.py 2.4+** - Discord API framework
- **Supabase** - Cloud PostgreSQL database
- **Redis** - Cache and session management

### Project Structure

```
Daily Draw/
├── bot.py                          # Application entry point
├── requirements.txt                # Python dependencies
├── Procfile                        # Deployment configuration
└── src/                            # Source code directory
    ├── __init__.py
    ├── main.py                     # Bot main program
    ├── config/                     # Configuration module
    │   ├── __init__.py
    │   └── config.py               # Global configuration and environment variables
    ├── db/                         # Database layer
    │   ├── __init__.py
    │   └── database.py             # Supabase client and query helpers
    ├── utils/                      # Utility modules
    │   ├── __init__.py
    │   ├── helpers.py              # Timezone, probability, ID utilities
    │   └── ui.py                   # Discord UI components
    ├── locales/                    # Multi-language packages
    │   ├── zh-CN.json              # Chinese language pack
    │   └── en-US.json              # English language pack
    └── commands/                   # Command system (modular)
        ├── __init__.py
        ├── economy/                # Economy system
        │   ├── __init__.py
        │   ├── daily_draw.py       # Daily lottery (!draw, /draw)
        │   ├── balance.py          # Points inquiry (!check, /balance)
        │   └── points.py           # Points management (!giftpoints, /give)
        ├── pets/                   # Pet system
        │   ├── __init__.py
        │   ├── eggs.py             # Pet egg drawing (/egg)
        │   ├── management.py       # Pet management (/pet)
        │   └── forge.py            # Fragment forge (/forge)
        ├── shop/                   # Shop system
        │   ├── __init__.py
        │   ├── roles.py            # Role shop (!roleshop, /tag)
        │   └── items.py            # Item shop (/shop)
        ├── games/                  # Game system
        │   ├── __init__.py
        │   └── quiz.py             # Quiz game (!quiz, /quiz)
        ├── rankings/               # Ranking system
        │   ├── __init__.py
        │   └── leaderboard.py      # Points leaderboard (!ranking)
        └── system/                 # System functions
            ├── __init__.py
            ├── help.py             # Help system (/help)
            └── admin.py            # Admin tools (!admin)
```

## ⚙️ Configuration Requirements

### Required Environment Variables
```env
TOKEN=discord_bot_token                   # Discord bot token
SUPABASE_URL=your_supabase_project_url    # Supabase project URL
SUPABASE_KEY=your_supabase_anon_key       # Supabase anonymous key
REDIS_URL=your_redis_server_url           # Redis connection URL (required for production)
```

### Database Architecture
The project uses Supabase (PostgreSQL 17.6) as the backend database, containing 22 data tables:

## 📋 Detailed Database Structure

### 👥 Core User Tables
#### `users`
**Purpose:** Store user basic information, points, and game status
```sql
Main fields:
- id (bigint, PK) - Internal user ID
- discord_user_id (bigint) - Discord user ID
- guild_id (bigint) - Server ID
- points (integer) - Current points
- paid_draws_today (integer) - Today's paid draw count
- last_draw_date (date) - Last draw date
- equipped_pet_id (bigint) - Equipped pet ID
- egg_pity_counter (integer) - Egg draw pity counter (0-49)
- legendary_egg_pity_counter (integer) - Legendary egg pity counter
```

### 🐾 Pet System Tables
#### `pet_templates`
**Purpose:** Pet template library, defining pet attributes
```sql
Main fields:
- id (bigint, PK) - Pet template ID
- cn_name (varchar, unique) - Chinese name
- en_name (varchar) - English name
- rarity (rarity_enum) - Rarity: C/R/SR/SSR
- cn_description/en_description (text) - Pet description
```

#### `user_pets`
**Purpose:** User-owned pet instances
```sql
Main fields:
- id (bigint, PK) - Pet instance ID
- user_id (bigint, FK) - Owner ID
- pet_template_id (bigint, FK) - Pet template ID
- level (integer) - Level (>=1)
- stars (integer) - Star rating
- xp_current/xp_total (integer) - Experience points
- satiety (integer) - Satiety (0-100)
- favorite_flavor/dislike_flavor (flavor_enum) - Flavor preferences
- last_feeding (timestamptz) - Last feeding time
```

#### `user_eggs`
**Purpose:** User pet egg inventory and hatching status
```sql
Main fields:
- id (bigint, PK) - Egg ID
- user_id (bigint, FK) - Owner ID
- rarity (rarity_enum) - Egg rarity: C/R/SR/SSR
- status (egg_status_enum) - Status: pending/hatching/completed/claimed
- hatch_started_at (timestamptz) - Hatch start time
- hatch_completed_at (timestamptz) - Hatch completion time
```

#### `user_pet_fragments`
**Purpose:** User pet fragment inventory
```sql
Main fields:
- id (bigint, PK) - Fragment ID
- user_id (bigint, FK) - Owner ID
- rarity (rarity_enum) - Fragment rarity
- amount (integer) - Fragment quantity
```

### 🍜 Food Shop System Tables
#### `food_templates`
**Purpose:** Food template definitions
```sql
Main fields:
- id (bigint, PK) - Food template ID
- cn_name/en_name (varchar) - Food name
- rarity (rarity_enum) - Rarity
- flavor (flavor_enum) - Flavor: SWEET/SALTY/SOUR/SPICY/UMAMI
- base_xp/xp_flow (integer) - Base experience points
- price (integer) - Price
```

#### `user_food_inventory`
**Purpose:** User food inventory
```sql
Main fields:
- id (bigint, PK) - Inventory ID
- user_id (bigint, FK) - User ID
- food_template_id (bigint, FK) - Food template ID
- quantity (integer) - Quantity (>=0)
```

#### `daily_shop_catalog`
**Purpose:** Daily shop product catalog
```sql
Main fields:
- refresh_date (date) - Refresh date
- food_template_id (bigint, FK) - Food ID
```

### 🎰 Game System Tables
#### `quiz_questions`
**Purpose:** Question bank
```sql
Main fields:
- id (bigint, PK) - Question ID
- category (varchar) - Question category
- language (quiz_language_enum) - Language: chinese/english
- question (text) - Question content
- option_a/b/c/d (varchar) - Options
- answer (char) - Correct answer (A/B/C/D)
```

#### `blackjack_games`
**Purpose:** Blackjack game history records
```sql
Main fields:
- id (bigint, PK) - Game ID
- user_id (bigint, FK) - Player ID
- bet_amount (integer) - Bet amount
- result (blackjack_result_enum) - Result: win/lose/tie/blackjack/surrender/dealer_blackjack
- profit (integer) - Net profit/loss
- player_hand/dealer_hand (jsonb) - Player/dealer hands
- had_insurance/is_split/is_doubled (boolean) - Game options
```

#### `user_game_statistics`
**Purpose:** User game statistics
```sql
Main fields:
- id (varchar, PK) - Statistics ID
- user_id (bigint, FK) - User ID
- game_type (game_type_enum) - Game type: quiz/memory/reaction/puzzle/snake/tetris
- best_score (integer) - Best score
- games_played (integer) - Games played count
```

### 🏷️ Shop System Tables
#### `tags`
**Purpose:** Role shop
```sql
Main fields:
- id (bigint, PK) - Role ID
- guild_id (text) - Server ID
- role_id (text) - Discord role ID
- price (integer) - Price (points)
```

### ⚙️ System Configuration Tables
#### `guild_settings`
**Purpose:** Server settings
```sql
Main fields:
- guild_id (bigint, PK) - Server ID
- language (language_enum) - Language: en/zh/ja/ko/es/fr/de
```

#### `egg_draw_probabilities`
**Purpose:** Egg draw probability configuration
```sql
Main fields:
- rarity (rarity_enum) - Rarity
- probability (numeric) - Probability value
```

#### `egg_hatch_probabilities`
**Purpose:** Egg hatching probability configuration
```sql
Main fields:
- egg_rarity (rarity_enum) - Egg rarity
- pet_rarity (rarity_enum) - Hatched pet rarity
- probability (numeric) - Probability value
```

#### `pet_rarity_configs`
**Purpose:** Pet rarity configuration
```sql
Main fields:
- rarity (rarity_enum) - Rarity
- min_initial_stars/max_initial_stars (integer) - Initial star range
- max_stars (integer) - Maximum stars
```

## 🚀 Quick Start

```bash
# Clone the project
git clone <repository-url>
cd Daily Draw

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env file with your configuration

# Run the bot
python bot.py
```

## 🎮 Command List

### 💰 Economy System Commands
**Traditional Commands:**
- `!draw [count]` - Daily draw (1 free, max 30 paid/day, 100 points each)
- `!check [user]` - Check points and draw status
- `!giftpoints <user> <points>` - Gift points to other users

**Draw Rules:**
- 🎉 **Free Draw**: 1 time daily, completely free
- 🎰 **Paid Draw**: Max 30 times daily, 100 points each
- ⏰ **Reset Time**: Automatically resets at 0:00 daily
- 💰 **Reward Range**: 10-1000 points, average return rate 103.8%

### 🥚 Egg System
**Slash Commands:**
- `/egg action:draw` - Draw pet eggs (single 250 points, 10-draw 2250 points)
- `/egg action:list` - View owned egg inventory
- `/egg action:hatch` - Select egg for hatching
- `/egg action:claim` - Claim completed hatched pets

### 🐾 Pet System
**Slash Commands:**
- `/pet action:list [page]` - View pet list (paginated)
- `/pet action:info` - View detailed pet information
- `/pet action:upgrade` - Upgrade pet star level (requires fragments and points)
- `/pet action:dismantle` - Dismantle pet for fragments and points
- `/pet action:fragments` - View owned pet fragment inventory
- `/pet action:equip` - Equip pet to start auto-earning points
- `/pet action:unequip` - Unequip current equipped pet
- `/pet action:status` - View current equipment status and pending points
- `/pet action:claim` - Claim auto-earned points from pets
- `/pet action:feed` - Feed pets to gain experience

**Auto Feeding:**
- `/feed auto [pet] [mode] [quantity]` - One-click pet feeding

### 🏪 Food Shop System
**Slash Commands:**
- `/shop action:view menu` - View today's food shop items
- `/shop action:buy item:<item_name> quantity:<quantity>` - Buy specified food
- `/inventory item_type:food` - View food inventory

### 🔨 Forge System
**Slash Commands:**
- `/forge action:view` - View fragment inventory and synthesis rules
- `/forge action:craft from_rarity:<source_rarity> to_rarity:<target_rarity> quantity:<quantity>` - Synthesize pet fragments

**Synthesis Rules:**
- C fragments → R fragments: 10:1 + 50 points
- R fragments → SR fragments: 5:1 + 80 points
- SR fragments → SSR fragments: 3:1 + 100 points

### 🏷️ Role System
**Slash Commands:**
- `/tag action:shop` - View role shop
- `/tag action:buy role_name:<role_name>` - Buy specified role

### 🎮 Quiz System
**Traditional Commands:**
- `!quizlist [language]` - View question bank categories
  • `!quizlist` or `!quizlist all` - Show all languages
  • `!quizlist chinese` - Show Chinese question banks only
  • `!quizlist english` - Show English question banks only

**Tips:**
- 20 points reward for each correct answer
- Wait for admin to start quiz!

### 🎰 Blackjack Game
**Slash Commands:**
- `/blackjack play <bet_amount>` - Start blackjack game
  • Bet amount can be a number or `all` (all points)
  • Example: `/blackjack play 100` or `/blackjack play all`
- `/blackjack stats` - View game statistics

**Game Features:**
- 🎴✋ **Basic Actions**: Hit, Stand
- 🎲 **Double Down**: Double bet after first deal
- ✂️ **Split**: Split pairs into two hands
- 🎲✂️ **DAS Rule**: Double after split (reduces house edge by 0.14%)
- 🛡️ **Insurance**: Buy insurance when dealer shows Ace
- 🏳️ **Surrender**: Surrender with very bad hand

**Special Features:**
- ✅ Standard casino rules (dealer stands on 17)
- ✅ Blackjack special reward (2.5x payout)
- ✅ Complete game records and statistics

### 🏆 Leaderboard System
**Slash Commands:**
- `/leaderboard [type]` - View server leaderboard (shows top 10)

**Leaderboard Types:**
- `points` - Points leaderboard (default)
- `pets` - Pet count leaderboard
- `hatched eggs` - Hatched eggs count leaderboard
- `blackjack wins` - Blackjack wins leaderboard

**Examples:**
• `/leaderboard` - View points leaderboard
• `/leaderboard type:pets` - View pet leaderboard
• `/leaderboard type:hatched eggs` - View hatched eggs leaderboard
• `/leaderboard type:blackjack wins` - View blackjack wins leaderboard

### ⚙️ Admin Commands
**System Management:**
- `/language` - Set server language
- `!rewardinfo` - Display prize probability information
- `!checksubscription` - Check server subscription status

**Role Management:**
- `!addtag <price> <role>` - Add purchasable role
- `!removetag <role>` - Remove role from shop
- `!updatetagprice <role> <new_price>` - Update role price
- `!listtags` - View all added roles

**Quiz Management:**
- `!quiz "<category>" <question_count>` - Start quiz game
  • Supports exact match: `!quiz 动漫 5`
  • Supports fuzzy match: `!quiz study 5` (matches all study:xxx)
  • 20 points reward for each correct answer

**Points Management:**
- `!givepoints <user> <points>` - Give points to user
- `!setpoints <user> <points>` - Set user points

## 🌍 Internationalization Support

### Multi-language Architecture
- **Language Pack Location**: `src/locales/`
- **Supported Languages**: Chinese (zh-CN), English (en-US)
- **Dynamic Switching**: Admins can switch server language in real-time
- **Extensibility**: Can add new languages following the same format

### Language Management
- Environment variable `DEFAULT_LOCALE` sets default language
- `/settings language` command switches server language
- All user interface texts are fully localized
- Please update language packs simultaneously when developing new features

## 🛠️ Development Guide

### Adding New Features
1. **Choose Module**: Determine feature category (economy/pets/shop/games/rankings/system)
2. **Create Command**: Add function to corresponding module file
3. **Update Export**: Export new function in module's `__init__.py`
4. **Register Command**: Register traditional and slash commands in `src/main.py`
5. **Add Translation**: Add multi-language support in `src/locales/`
6. **Test Feature**: Use built-in test commands to verify functionality

### Command System Architecture
- **Hybrid Commands**: Support both `!command` and `/command`
- **Permission Control**: Use `@commands.has_permissions()` for permissions
- **Error Handling**: Unified error handling and user feedback mechanism
- **Async Operations**: All database operations use async/await

### Database Operations
```python
# Get database connection
from src.db.database import get_connection
supabase = get_connection()

# User operation example
from src.utils.helpers import get_missing_user_id
user_id = await get_missing_user_id(discord_user.id)
```

### UI Component Usage
```python
# Create interactive selection menu
from src.utils.ui import create_pet_selector, create_confirmation
view = create_pet_selector(pets, "Select a pet")
await ctx.send_message(view=view)
```

## 📊 Project Statistics

**System Features:**
- ✅ Modular architecture design
- ✅ Complete permission management
- ✅ Redis cache optimization
- ✅ Multi-language internationalization
- ✅ Comprehensive error handling
- ✅ Rich management tools

## 🔧 Troubleshooting

### Common Issues
1. **Bot fails to start**: Check environment variable configuration and Discord token
2. **Database connection failure**: Verify Supabase URL and key
3. **Redis connection error**: Redis URL must be configured in production environment
4. **Commands not responding**: Check if bot has server permissions

### Log Debugging
```bash
# View bot running logs
python bot.py  # Logs will be output to console
```

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing Guidelines

1. Fork this project
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Create Pull Request

## 📞 Support

For questions or suggestions, please:
- Create an [Issue](../../issues)
- Contact project maintainers

---

**⭐ If this project helps you, please give it a star!**