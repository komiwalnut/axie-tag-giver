# ServerTag Discord Bot

In a way, this is a template bot for roles gated by server tags. A Discord bot that assigns roles to users based on their Discord server tag. Users with the correct server tag can claim a specific role by clicking a button.

## Prerequisites

- Python 3.8 or higher
- Discord bot token (same as discord api key)
- A Discord server with proper permissions

## Installation

1. Clone the repository:
```bash
git clone https://github.com/komiwalnut/axie-tag-giver.git
cd axie-tag-giver
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root:

Note: Be sure to add `"Bot"` before `DISCORD_API_KEY` like `DISCORD_API_KEY="Bot abc123...key"`
```env
BOT_TOKEN=your_bot_token_here
DISCORD_API_KEY="Bot + your_bot_token_here"
```

## Configuration

Update `config.py` with your specific requirements:
```python
CHANNEL_ID = int('916398226813370419')    # The channel ID where the claim role message will be posted
ROLE_ID = int('1371506589806100590')    # Role ID of the role given to users
DISCORD_GUILD_ID = int('410537146672349205')    # The server ID where the bot is invited
SERVER_LINK = 'https://discord.gg/GkaVv8vfp3'   # The link to the server if the user does not have the correct server tag (optional if server tag belongs to another server)
REQUIRED_TAG = 'AXIE'   # The server tag users must have
REQUIRED_GUILD_ID = '1369851009827999907'   # The guild ID associated with the server tag
```

## Bot Setup

1. Create a new application on [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a bot and copy the bot token
3. Enable these bot permissions:
   - Send Messages
   - Embed Links
   - Manage Roles
   - Read Message History
   - Server Members Intent (Bot -> Privileged Gateway Intents)
4. Invite the bot to your server

## Server Configuration

**Role Hierarchy**: Make sure the bot's role is positioned ABOVE the role you want it to assign

## Usage

1. Start the bot:
```bash
nohup python3 -u bot.py > /dev/null 2>&1 &
```

2. The bot will:
   - Post an embed message with a "Claim Role" button in the specified channel
   - Allow users to click the button to claim their role if they have the correct server tag
   - Run checks to verify users still have the server tag
   - Remove roles from users who no longer have the valid server tag

## File Structure

```
axie-tag-giver/
├── bot.py              # Main bot code
├── config.py           # Configuration settings
├── requirements.txt    # Python dependencies
├── .env               # Environment variables (not in repo)
├── users.json         # Tracks users with the role (auto-created)
├── message_id.json    # Tracks the claim message ID (auto-created)
├── bot.log            # Log file (auto-created)
└── README.md          # This file
```
