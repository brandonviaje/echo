from bot import Bot
import discord
from discord.ext import voice_recv
from dotenv import load_dotenv
from faster_whisper import WhisperModel
import logging
import os
from discord.ext.voice_recv import BasicSink
import discord.opus
import warnings

_original_opus_decode = discord.opus.Decoder.decode

def safe_opus_decode(self, *args, **kwargs):
    try:
        return _original_opus_decode(self, *args, **kwargs)
    except discord.opus.OpusError:
        print("[Anti-Crash] Blocked corrupted audio packet.")
        return bytes(3840)

discord.opus.Decoder.decode = safe_opus_decode

# schedule async on_speech coroutine
def on_speech_wrapper(recognizer, audio, user):
    bot.loop.create_task(bot.on_speech(recognizer, audio, user))

if __name__ == "__main__":
    # load env variables, model, logger, ignore warning
    load_dotenv() 
    whisper_model = WhisperModel("base.en", device="cpu", download_root="./models", compute_type="int8")
    logging.getLogger("discord.ext.voice_recv.reader").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", category=UserWarning, module='webrtcvad')

    # init bot and guild ID 
    bot = Bot(whisper_model)
    GUILD_ID = discord.Object(id=1467314035585450155)

    # commands
    @bot.tree.command(name="listen", description="Join call and give me commands!", guild=GUILD_ID)
    async def listen(interaction: discord.Interaction):
        if interaction.user.voice:
            await interaction.response.defer()
            vc = await interaction.user.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
            
            def simple_callback(user, voice_data):
                bot.loop.create_task(bot.on_speech(user, voice_data))

            vc.listen(BasicSink(simple_callback)) 
            
            await interaction.followup.send("I am now listening to you!")
        else:
            await interaction.response.send_message("You need to be in a VC first!", ephemeral=True)

    bot.run(os.getenv('DISCORD_TOKEN')) # run bot
