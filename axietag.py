import discord
from discord.ext import tasks
import aiohttp
import json
import os
from datetime import datetime
from config import *
import logging
import asyncio

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('axie-tag-bot')

intents = discord.Intents.default()
intents.guilds = True

bot = discord.Client(intents=intents)

session = None


def ensure_json_files():
    if not os.path.exists('users.json'):
        with open('users.json', 'w') as f:
            json.dump({}, f)
        logger.info("Created users.json")

    if not os.path.exists('message_id.json'):
        with open('message_id.json', 'w') as f:
            json.dump({}, f)
        logger.info("Created message_id.json")


async def add_role_via_api(guild_id, user_id, role_id):
    headers = {
        'Authorization': f'Bot {BOT_TOKEN}',
        'Content-Type': 'application/json'
    }
    url = f'https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{role_id}'

    async with session.put(url, headers=headers) as resp:
        if resp.status == 204:
            return True
        else:
            text = await resp.text()
            logger.error(f"Failed to add role: {resp.status} - {text}")
            return False


async def remove_role_via_api(guild_id, user_id, role_id):
    headers = {
        'Authorization': f'Bot {BOT_TOKEN}',
        'Content-Type': 'application/json'
    }
    url = f'https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{role_id}'

    async with session.delete(url, headers=headers) as resp:
        if resp.status == 204:
            return True
        else:
            text = await resp.text()
            logger.error(f"Failed to remove role: {resp.status} - {text}")
            return False


async def check_user_has_role(guild_id, user_id, role_id):
    headers = {
        'Authorization': f'Bot {BOT_TOKEN}',
        'Content-Type': 'application/json'
    }
    url = f'https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}'

    async with session.get(url, headers=headers) as resp:
        if resp.status == 200:
            data = await resp.json()
            return str(role_id) in data.get('roles', [])
        else:
            return False


class ClaimRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Claim Role', style=discord.ButtonStyle.danger, custom_id='claim_role_button')
    async def claim_role(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer()

        user_id = str(interaction.user.id)
        logger.info(f"User {user_id} ({interaction.user.name}) attempting to claim role")

        headers = {
            'Authorization': DISCORD_API_KEY
        }

        async with session.get(f'https://discord.com/api/v10/users/{user_id}', headers=headers) as resp:
            if resp.status == 200:
                user_data = await resp.json()
                logger.debug(f"API response for {user_id}: {user_data}")

                if user_data.get('clan') and user_data['clan'].get('tag') == REQUIRED_TAG and user_data['clan'].get('identity_guild_id') == REQUIRED_GUILD_ID:
                    has_role = await check_user_has_role(interaction.guild.id, user_id, ROLE_ID)

                    if has_role:
                        logger.info(f"User {user_id} already has the role")
                        embed = discord.Embed(
                            description="You already have this role!",
                            color=discord.Color.orange()
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        success = await add_role_via_api(interaction.guild.id, user_id, ROLE_ID)

                        if success:
                            logger.info(f"Added role to user {user_id}")

                            with open('users.json', 'r') as f:
                                users = json.load(f)

                            users[user_id] = {
                                'username': interaction.user.name,
                                'added_date': datetime.now().isoformat()
                            }

                            with open('users.json', 'w') as f:
                                json.dump(users, f, indent=4)

                            embed = discord.Embed(
                                title="Success!",
                                description=f"You have been given the <@&{ROLE_ID}> role!",
                                color=discord.Color.green()
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                        else:
                            logger.error(f"Failed to add role to user {user_id}")
                            embed = discord.Embed(
                                title="Error",
                                description="Failed to assign the role. Please try claiming again.",
                                color=discord.Color.red()
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    logger.info(f"User {user_id} does not have required server tag")
                    embed = discord.Embed(
                        title="You Don't Have the Required Server Tag",
                        description=f"You need to have the `[{REQUIRED_TAG}]` server tag to claim this role.\n\n[Go check this post](https://discord.com/channels/410537146672349205/414758518101639188/1372449656721903647)",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                logger.error(f"API request failed for user {user_id}: Status {resp.status}")
                embed = discord.Embed(
                    title="Error",
                    description="Failed to check your server tag. Please try again later.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    global session
    logger.info(f'{bot.user} is ready!')

    connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
    session = aiohttp.ClientSession(connector=connector)

    bot.add_view(ClaimRoleView())
    ensure_json_files()
    server_check.start()
    logger.info("Server tag check task started")

    await setup_claim_message()


async def setup_claim_message():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        logger.error(f"Channel with ID {CHANNEL_ID} not found")
        return

    message_id = None

    try:
        with open('message_id.json', 'r') as f:
            data = json.load(f)
            message_id = data.get('message_id')
            logger.info(f"Found existing message ID: {message_id}")
    except FileNotFoundError:
        logger.info("No message_id.json found, will create new message")

    if message_id:
        try:
            _ = await channel.fetch_message(message_id)
            logger.info("Existing claim message found, not creating new one")
            return
        except discord.NotFound:
            logger.warning(f"Message {message_id} not found, creating new one")

    embed = discord.Embed(
        title="Claim Your Role",
        description=f"Claim your <@&{ROLE_ID}> role if you have the `[{REQUIRED_TAG}]` server tag!",
        color=discord.Color.blue()
    )
    sent_message = await channel.send(embed=embed, view=ClaimRoleView())
    logger.info(f"Created new claim message with ID: {sent_message.id}")

    with open('message_id.json', 'w') as f:
        json.dump({'message_id': sent_message.id}, f)


@tasks.loop(hours=8)
async def server_check():
    logger.info("Starting server tag check")

    with open('users.json', 'r') as f:
        users = json.load(f)

    headers = {
        'Authorization': DISCORD_API_KEY
    }

    guild = bot.get_guild(DISCORD_GUILD_ID)
    if not guild:
        logger.error(f"Guild with ID {DISCORD_GUILD_ID} not found")
        return

    removed_users = []
    readded_users = []
    rate_limit_count = 0
    base_delay = 2.0

    logger.info(f"Checking {len(users)} users")

    for index, (user_id, user_info) in enumerate(list(users.items())):
        try:
            current_delay = base_delay * (1.5 ** rate_limit_count)

            async with session.get(f'https://discord.com/api/v10/users/{user_id}', headers=headers) as resp:
                remaining = resp.headers.get('X-RateLimit-Remaining')
                if remaining:
                    logger.debug(f"Rate limit remaining: {remaining}")

                if resp.status == 200:
                    user_data = await resp.json()
                    rate_limit_count = 0

                    if user_data.get('clan') and user_data['clan'].get('tag') == REQUIRED_TAG and user_data['clan'].get('identity_guild_id') == REQUIRED_GUILD_ID:
                        has_role = await check_user_has_role(guild.id, user_id, ROLE_ID)

                        if not has_role:
                            success = await add_role_via_api(guild.id, user_id, ROLE_ID)
                            if success:
                                readded_users.append(user_id)
                                logger.info(f"Re-added role to user {user_id} - has correct server tag but was missing role")
                            else:
                                logger.error(f"Failed to re-add role to user {user_id}")
                        else:
                            logger.debug(f"User {user_id} has correct tag and role")
                    else:
                        has_role = await check_user_has_role(guild.id, user_id, ROLE_ID)

                        if has_role:
                            success = await remove_role_via_api(guild.id, user_id, ROLE_ID)
                            if success:
                                del users[user_id]
                                removed_users.append(user_id)
                                logger.info(f"Removed role from user {user_id} - server tag no longer valid")
                            else:
                                logger.error(f"Failed to remove role from user {user_id}")
                        else:
                            del users[user_id]
                            logger.info(f"User {user_id} already doesn't have the role, removed from tracking")
                elif resp.status == 429:
                    rate_limit_count += 1
                    retry_after = float(resp.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited (count: {rate_limit_count}) on user {index + 1}/{len(users)}, waiting {retry_after} seconds")
                    await asyncio.sleep(retry_after + 5)
                    continue
                else:
                    logger.error(f"Failed to check user {user_id}: Status {resp.status}")

            if (index + 1) % 10 == 0:
                logger.info(f"Progress: {index + 1}/{len(users)} users checked")

            await asyncio.sleep(current_delay)

        except Exception as err:
            logger.error(f"Error checking user {user_id}: {err}")
            continue

    with open('users.json', 'w') as f:
        json.dump(users, f, indent=4)

    logger.info(f"Server tag check completed. Removed {len(removed_users)} users, re-added {len(readded_users)} users")


@server_check.before_loop
async def before_tag_check():
    await bot.wait_until_ready()
    logger.info("Bot is ready, server tag check will start")


@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"Error in {event}: {args}, {kwargs}")


async def cleanup():
    logger.info("Shutting down bot...")
    if session and not session.closed:
        await session.close()
    logger.info("Bot shutdown complete")


try:
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(bot.start(BOT_TOKEN))
    except KeyboardInterrupt:
        loop.run_until_complete(cleanup())
        loop.run_until_complete(bot.close())
    finally:
        loop.close()
except Exception as e:
    logger.critical(f"Failed to start bot: {e}")
