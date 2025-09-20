# Daily Draw Bot

一个Discord抽奖机器人，支持每日抽奖、积分系统、身份组购买和答题游戏。

## 功能特点

- 每日免费抽奖
- 付费额外抽奖（每天最多10次）
- 积分排行榜
- 身份组商店
- 答题游戏系统

## 项目结构

```
Daily Draw/
├── bot.py                  # 入口点
├── src/                    # 源代码目录
│   ├── __init__.py
│   ├── main.py             # 主程序
│   ├── config/             # 配置模块
│   │   ├── __init__.py
│   │   └── config.py       # 配置参数
│   ├── db/                 # 数据库模块
│   │   ├── __init__.py
│   │   └── database.py     # 数据库操作
│   ├── utils/              # 工具模块
│   │   ├── __init__.py
│   │   ├── helpers.py      # 辅助函数
│   │   └── ui.py           # UI组件
│   └── commands/           # 命令模块
│       ├── __init__.py
│       ├── draw_commands.py      # 抽奖命令
│       ├── debug_commands.py     # 调试命令
│       ├── role_commands.py      # 角色命令
│       ├── quiz_commands.py      # 答题命令
│       ├── ranking_commands.py   # 排行榜命令
│       └── help_commands.py      # 帮助命令
├── requirements.txt        # 依赖项
├── Procfile               # 部署配置
└── README.md              # 项目说明
```

## 环境变量

- `TOKEN`: Discord机器人令牌
- `SUPABASE_URL`: Supabase项目URL
- `SUPABASE_KEY`: Supabase匿名密钥

## 安装

1. 克隆仓库
2. 安装依赖：`pip install -r requirements.txt`
3. 设置环境变量
4. 运行：`python bot.py`

## 命令列表

### 用户命令

- `!draw` - 每日抽奖（免费1次，付费最多10次/天）
- `!check [用户]` - 查看积分和抽奖状态
- `!ranking` - 查看积分排行榜
- `!roleshop` - 查看身份组商店
- `!buytag <身份组名>` - 购买身份组
- `!quizlist` - 查看题库类别
- `!quiz <类别> <题目数>` - 开始答题游戏
- `/help` - 显示帮助信息

### 管理员命令

- `!givepoints <用户> <积分>` - 给予用户积分
- `!setpoints <用户> <积分>` - 设置用户积分
- `!resetdraw <用户>` - 重置用户抽奖状态
- `!resetall --confirm` - 清空所有用户数据
- `!fixdb` - 修复数据库结构
- `!checkdb` - 检查数据库结构
- `!debuguser <用户>` - 调试用户付费抽奖信息
- `!detailedebug <用户>` - 详细调试付费抽奖逻辑
- `!testupdate <用户>` - 测试数据库更新功能
- `!addtag <价格> <身份组>` - 添加可购买身份组
- `!rewardinfo` - 查看抽奖概率系统
- `!testdraw [次数]` - 测试抽奖系统
- `!importquiz` - 导入题库文件
- `!deletequiz <类别>` - 删除题库题目
