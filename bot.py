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

bot = commands.Bot(command_prefix='!', intents=intents)


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

        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://discord.com/api/v10/users/{user_id}', headers=headers) as resp:
                if resp.status == 200:
                    user_data = await resp.json()
                    logger.debug(f"API response for {user_id}: {user_data}")

                    if user_data.get('clan') and user_data['clan'].get('tag') == REQUIRED_TAG and user_data['clan'].get('identity_guild_id') == REQUIRED_GUILD_ID:
                        role = discord.utils.get(interaction.guild.roles, id=ROLE_ID)

                        if not role:
                            logger.error(f"Role with ID {ROLE_ID} not found")
                            embed = discord.Embed(
                                title="Configuration Error",
                                description="The configured role was not found. Please contact an administrator.",
                                color=discord.Color.red()
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                            return

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
                                    description=f"You have been given the {role.name} role!",
                                    color=discord.Color.green()
                                )
                                await interaction.followup.send(embed=embed, ephemeral=True)
                            except discord.Forbidden:
                                logger.error(f"Missing permissions to add role to user {user_id}")
                                embed = discord.Embed(
                                    title="Permission Error",
                                    description="I don't have permission to assign this role. Please contact an administrator.",
                                    color=discord.Color.red()
                                )
                                embed.add_field(name="Possible fixes:",
                                                value="1. Make sure the bot has 'Manage Roles' permission\n2. Make sure the bot's role is higher than the role being assigned in the role hierarchy")
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


@tasks.loop(hours=8)
async def daily_clan_check():
    logger.info("Starting daily clan check")

    with open('users.json', 'r') as f:
        users = json.load(f)

    headers = {
        'Authorization': DISCORD_API_KEY
    }

    guild = bot.get_guild(DISCORD_GUILD_ID)
    role = discord.utils.get(guild.roles, id=ROLE_ID)

    removed_users = []
    rate_limit_count = 0
    base_delay = 2.0

    logger.info(f"Checking {len(users)} users")

    for index, (user_id, user_info) in enumerate(list(users.items())):
        try:
            current_delay = base_delay * (1.5 ** rate_limit_count)

            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://discord.com/api/v10/users/{user_id}', headers=headers) as resp:
                    remaining = resp.headers.get('X-RateLimit-Remaining')
                    if remaining:
                        logger.debug(f"Rate limit remaining: {remaining}")

                    if resp.status == 200:
                        user_data = await resp.json()
                        rate_limit_count = 0

                        if not (user_data.get('clan') and user_data['clan'].get('tag') == REQUIRED_TAG and user_data['clan'].get('identity_guild_id') == REQUIRED_GUILD_ID):
                            member = guild.get_member(int(user_id))
                            if member and role in member.roles:
                                await member.remove_roles(role)
                                del users[user_id]
                                removed_users.append(user_id)
                                logger.info(f"Removed role from user {user_id} - clan tag no longer valid")
                    elif resp.status == 429:
                        rate_limit_count += 1
                        retry_after = float(resp.headers.get('Retry-After', 60))
                        logger.warning(f"Rate limited (count: {rate_limit_count}) on user {index + 1}/{len(users)}, waiting {retry_after} seconds")
                        await asyncio.sleep(retry_after + 5)
                        continue
                    else:
                        logger.error(f"Failed to check user {user_id}: Status {resp.status}")

            if (index + 1) % 5 == 0:
                logger.info(f"Progress: {index + 1}/{len(users)} users checked")

            await asyncio.sleep(current_delay)

        except Exception as err:
            logger.error(f"Error checking user {user_id}: {err}")
            continue

    with open('users.json', 'w') as f:
        json.dump(users, f, indent=4)

    logger.info(f"Daily clan check completed. Removed {len(removed_users)} users")


@daily_clan_check.before_loop
async def before_daily_check():
    await bot.wait_until_ready()
    logger.info("Bot is ready, daily check will start")


try:
    bot.run(BOT_TOKEN)
except Exception as e:
    logger.critical(f"Failed to start bot: {e}")
