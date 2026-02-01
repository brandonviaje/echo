import discord
import os
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv() # load env variables

class Bot(commands.Bot):

    def __init__(self):
        # intents config
        intents = discord.Intents.default()
        intents.message_content = True 
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)
        
    async def on_ready(self):
        print(f"Logged on as {self.user}!")
        guild = discord.Object(id=1467314035585450155)

        # sync commands to dev server
        try:
            synced = await self.tree.sync(guild=guild)
            print(f'Synced {len(synced)} commands to guild {guild.id}')
        except Exception as e:
            print(f'ERROR Syncing Commands: {e}')

    async def on_message(self, message):
        # ignore itself
        if message.author == self.user:
            return
        
        await self.process_commands(message)

# init bot and guild ID 
bot = Bot()
GUILD_ID = discord.Object(id=1467314035585450155)

# slash commands
@bot.tree.command(name="hello", description="Say Wassup", guild=GUILD_ID)
async def sayHello(interaction : discord.Interaction):
    await interaction.response.send_message("Sup Twin")

@bot.tree.command(name="echo", description="Echo what you type", guild=GUILD_ID)
async def echo(interaction : discord.Interaction, message : str):
    await interaction.response.send_message(message)

bot.run(os.getenv('DISCORD_TOKEN')) # run bot
