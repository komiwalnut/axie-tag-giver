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

bot = commands.Bot(command_prefix=None, intents=intents)


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
                                description="`Axie Tag Bearer` role was not found. Please contact a mod.",
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
                                    description=f"You have been given the `{role.name}` role!",
                                    color=discord.Color.green()
                                )
                                await interaction.followup.send(embed=embed, ephemeral=True)
                            except discord.Forbidden:
                                logger.error(f"Missing permissions to add role to user {user_id}")
                                embed = discord.Embed(
                                    title="Permission Error",
                                    description="I don't have permission to assign this role. Please contact a mod.",
                                    color=discord.Color.red()
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
                                description="You already have the `Axie Tag Bearer` role!",
                                color=discord.Color.orange()
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        logger.info(f"User {user_id} does not have required server tag")
                        embed = discord.Embed(
                            title="Server Tag Not Found",
                            description=f"You need to have the `[{REQUIRED_TAG}]` server tag to claim this role.\n\n[Join our server]({SERVER_LINK})",
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
    logger.info(f'{bot.user} is ready!')
    bot.add_view(ClaimRoleView())
    ensure_json_files()
    daily_clan_check.start()
    logger.info("Daily server check task started")

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
        description=f"Click the button below to claim your role if you have the `[{REQUIRED_TAG}]` server tag!",
        color=discord.Color.blue()
    )
    sent_message = await channel.send(embed=embed, view=ClaimRoleView())
    logger.info(f"Created new claim message with ID: {sent_message.id}")

    with open('message_id.json', 'w') as f:
        json.dump({'message_id': sent_message.id}, f)


@tasks.loop(hours=24)
async def daily_clan_check():
    logger.info("Starting daily server check")

    with open('users.json', 'r') as f:
        users = json.load(f)

    headers = {
        'Authorization': DISCORD_API_KEY
    }

    guild = bot.get_guild(DISCORD_GUILD_ID)
    role = discord.utils.get(guild.roles, id=ROLE_ID)

    removed_users = []

    logger.info(f"Checking {len(users)} users")

    for user_id, user_info in list(users.items()):
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://discord.com/api/v10/users/{user_id}', headers=headers) as resp:
                if resp.status == 200:
                    user_data = await resp.json()

                    if not (user_data.get('clan') and user_data['clan'].get('tag') == REQUIRED_TAG and user_data['clan'].get('identity_guild_id') == REQUIRED_GUILD_ID):
                        member = guild.get_member(int(user_id))
                        if member and role in member.roles:
                            await member.remove_roles(role)
                            del users[user_id]
                            removed_users.append(user_id)
                            logger.info(f"Removed role from user {user_id} - server tag no longer valid")
                elif resp.status == 429:
                    retry_after = int(resp.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited, waiting {retry_after} seconds")
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    logger.error(f"Failed to check user {user_id}: Status {resp.status}")

        await asyncio.sleep(0.5)

    with open('users.json', 'w') as f:
        json.dump(users, f, indent=4)

    logger.info(f"Daily server check completed. Removed {len(removed_users)} users")


@daily_clan_check.before_loop
async def before_daily_check():
    await bot.wait_until_ready()
    logger.info("Bot is ready, daily check will start")


try:
    bot.run(BOT_TOKEN)
except Exception as e:
    logger.critical(f"Failed to start bot: {e}")
