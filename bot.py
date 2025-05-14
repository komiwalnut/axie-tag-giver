import discord
from discord.ext import commands, tasks
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
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='', intents=intents)


def ensure_json_files():
    if not os.path.exists('users.json'):
        with open('users.json', 'w') as f:
            json.dump({}, f)
        logger.info("Created users.json")

    if not os.path.exists('message_id.json'):
        with open('message_id.json', 'w') as f:
            json.dump({}, f)
        logger.info("Created message_id.json")


class ClaimRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label='Join Server', style=discord.ButtonStyle.link, url=SERVER_LINK))

    @discord.ui.button(label='Claim Role', style=discord.ButtonStyle.danger, custom_id='claim_role_button')
    async def claim_role(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer()

        user_id = str(interaction.user.id)
        logger.info(f"User {user_id} ({interaction.user.name}) attempting to claim role")

        headers = {
            'Authorization': DISCORD_API_KEY
        }

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(f'https://discord.com/api/v10/users/{user_id}', headers=headers) as resp:
                    if resp.status == 200:
                        user_data = await resp.json()
                        logger.debug(f"API response for {user_id}: {user_data}")

                        if user_data.get('clan') and user_data['clan'].get('tag') == REQUIRED_TAG and user_data['clan'].get('identity_guild_id') == REQUIRED_GUILD_ID:
                            role = discord.utils.get(interaction.guild.roles, id=ROLE_ID)

                            if role not in interaction.user.roles:
                                try:
                                    await interaction.user.add_roles(role)
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
                                        description=f"You have been given the <@&1371506589806100590> role!",
                                        color=discord.Color.green()
                                    )
                                    await interaction.followup.send(embed=embed, ephemeral=True)
                                except Exception as err:
                                    logger.error(f"Unexpected error when adding role to user {user_id}: {err}")
                                    embed = discord.Embed(
                                        title="Error",
                                        description="An unexpected error occurred. Please try again later.",
                                        color=discord.Color.red()
                                    )
                                    await interaction.followup.send(embed=embed, ephemeral=True)
                            else:
                                logger.info(f"User {user_id} already has the role")
                                embed = discord.Embed(
                                    title="Already Have Role",
                                    description="You already have this role!",
                                    color=discord.Color.orange()
                                )
                                await interaction.followup.send(embed=embed, ephemeral=True)
                        else:
                            logger.info(f"User {user_id} does not have required clan tag")
                            embed = discord.Embed(
                                title="Clan Tag Not Found",
                                description=f"You need to have the [{REQUIRED_TAG}] clan tag to claim this role.\n\n[Join our server]({SERVER_LINK})",
                                color=discord.Color.red()
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        logger.error(f"API request failed for user {user_id}: Status {resp.status}")
                        embed = discord.Embed(
                            title="Error",
                            description="Failed to check your clan tag. Please try again later.",
                            color=discord.Color.red()
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
            except asyncio.TimeoutError:
                logger.error(f"Request timeout for user {user_id}")
                embed = discord.Embed(
                    title="Error",
                    description="Request timed out. Please try again later.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    logger.info(f'{bot.user} is ready!')
    bot.add_view(ClaimRoleView())
    ensure_json_files()
    daily_clan_check.start()
    logger.info("Daily clan check task started")

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
        description=f"Claim your <@&1371506589806100590> role if you have the `[{REQUIRED_TAG}]` server tag!",
        color=discord.Color.blue()
    )
    sent_message = await channel.send(embed=embed, view=ClaimRoleView())
    logger.info(f"Created new claim message with ID: {sent_message.id}")

    with open('message_id.json', 'w') as f:
        json.dump({'message_id': sent_message.id}, f)


async def check_user_clan_tag(session, user_id, headers):
    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            async with session.get(f'https://discord.com/api/v10/users/{user_id}', headers=headers) as resp:
                remaining = resp.headers.get('X-RateLimit-Remaining')
                if remaining:
                    logger.debug(f"Rate limit remaining: {remaining}")

                if resp.status == 200:
                    user_data = await resp.json()
                    return user_data, None
                elif resp.status == 429:
                    retry_after = float(resp.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited for user {user_id}, waiting {retry_after} seconds")
                    await asyncio.sleep(retry_after + 1)
                    continue
                else:
                    return None, f"Status {resp.status}"

        except asyncio.TimeoutError:
            logger.error(f"Timeout for user {user_id} on attempt {attempt + 1}")
            if attempt < max_retries - 1:
                await asyncio.sleep(base_delay * (attempt + 1))
                continue
            return None, "Timeout"
        except Exception as err:
            logger.error(f"Error checking user {user_id}: {err}")
            return None, str(err)

    return None, "Max retries exceeded"


@tasks.loop(hours=12)
async def daily_clan_check():
    logger.info("Starting daily clan check")

    with open('users.json', 'r') as f:
        users = json.load(f)

    if not users:
        logger.info("No users to check")
        return

    headers = {
        'Authorization': DISCORD_API_KEY
    }

    guild = bot.get_guild(DISCORD_GUILD_ID)
    if not guild:
        logger.error(f"Guild {DISCORD_GUILD_ID} not found")
        return

    role = discord.utils.get(guild.roles, id=ROLE_ID)
    if not role:
        logger.error(f"Role {ROLE_ID} not found")
        return

    chunk_size = 10
    user_ids = list(users.keys())
    total_users = len(user_ids)
    removed_users = []

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for chunk_start in range(0, total_users, chunk_size):
            chunk_end = min(chunk_start + chunk_size, total_users)
            chunk = user_ids[chunk_start:chunk_end]

            logger.info(f"Processing users {chunk_start + 1}-{chunk_end} of {total_users}")

            tasks = []
            for user_id in chunk:
                tasks.append(check_user_clan_tag(session, user_id, headers))

            results = await asyncio.gather(*tasks)

            for i, (user_id, (user_data, error)) in enumerate(zip(chunk, results)):
                if error:
                    logger.error(f"Failed to check user {user_id}: {error}")
                    continue

                if user_data:
                    has_valid_tag = (
                            user_data.get('clan') and
                            user_data['clan'].get('tag') == REQUIRED_TAG and
                            user_data['clan'].get('identity_guild_id') == REQUIRED_GUILD_ID
                    )

                    if not has_valid_tag:
                        member = guild.get_member(int(user_id))
                        if member and role in member.roles:
                            try:
                                await member.remove_roles(role)
                                removed_users.append(user_id)
                                logger.info(f"Removed role from user {user_id} - clan tag no longer valid")
                            except Exception as err:
                                logger.error(f"Failed to remove role from user {user_id}: {err}")

            if chunk_end < total_users:
                await asyncio.sleep(2)

    if removed_users:
        for user_id in removed_users:
            if user_id in users:
                del users[user_id]

        with open('users.json', 'w') as f:
            json.dump(users, f, indent=4)

    logger.info(f"Daily clan check completed. Removed {len(removed_users)} users from {total_users} total")


@daily_clan_check.before_loop
async def before_daily_check():
    await bot.wait_until_ready()
    logger.info("Bot is ready, daily check will start")


try:
    bot.run(BOT_TOKEN)
except Exception as e:
    logger.critical(f"Failed to start bot: {e}")
