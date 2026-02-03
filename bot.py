import asyncio
import audioop
import discord
from discord.ext import commands, tasks
from fuzzywuzzy import process
import math
import numpy as np
import re
import string
import time
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='webrtcvad')
import webrtcvad

class Bot(commands.Bot):
    def __init__(self, whisper_model):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True 
        super().__init__(command_prefix="!", intents=intents)

        # state management
        self.phrase_buffer = {}    # stores raw audio bytes for each user until they stop talking
        self.last_speech_time = {} # timestamps for silence detection 
        self.speaking_state = {}   # boolean to track if we are currently mid-sentence
        self.last_wake_time = {}   # "hey echo" wake word timer
        self.last_move_time = {}   # prevent bot from hearing its own "move" action as a new command
        self.pending_moves = {}

        # constants/models
        self.WAKE_WINDOW = 10        # how long the bot listens after "hey echo"
        self.SILENCE_THRESHOLD = 0.8 # seconds of silence before we consider a sentence "finished"
        self.whisper_model = whisper_model
        self.vad = webrtcvad.Vad(2)  # voice activity detector (VAD)

    async def on_ready(self):
        print(f"Logged on as {self.user}!")

        # run background task that watches for silence
        if not self.check_silence.is_running():
            self.check_silence.start()

        # sync slash commands to server
        try:
            guild = discord.Object(id=1467314035585450155)
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} commands to guild {guild.id}")
        except Exception as e:
            print(f"ERROR Syncing Commands: {e}")

    """
    Scan packet of audio to detect human speech vs background noise.
    WebRTC VAD requires 10ms, 20ms, or 30ms chunks.
    """
    def is_voice_active(self, audio_data):
        sample_rate = 16000
        frame_bytes = 640 # 20ms at 16kHz (16000 * 0.02 * 2 bytes/sample)

        # slice the audio into 20ms chunks
        for i in range(0, len(audio_data), frame_bytes):
            chunk = audio_data[i : i + frame_bytes]         # get a single chunk of 20ms audio

            # don't process chunks smaller than 20ms
            if len(chunk) < frame_bytes:
                break
                
            # check if chunk is speech or silence
            try:
                if self.vad.is_speech(chunk, sample_rate):
                    return True
            except Exception:
                continue

        return False
    
    """
    Wraps the Whisper model, transcribe audio. 
    """
    def transcribe(self, audio_np):

        segments_generator, info = self.whisper_model.transcribe(audio_np,beam_size=5,temperature=0.0,condition_on_previous_text=False)
        segments = list(segments_generator)

        # check for empty transcript
        if not segments:
            return None, 0.0, "Empty Transcript"

        text = " ".join(seg.text for seg in segments).strip().lower() # join segments into text

        # get confidence score
        try:
            avg_logprob = (sum(seg.avg_logprob for seg in segments) / len(segments))
            confidence = math.exp(avg_logprob)
        except Exception:
            confidence = 0.0

        if not text:
            return None, 0.0, "Empty text"

        # discard low-confidence guesses
        if confidence < 0.4:
            return None, confidence, f"Low Confidence: {text}"

        return text, confidence, "Success"
    
    """
    Converts audio -> text -> command
    Ran in a separate task to avoid blocking the bot.
    """
    async def process_complete_phrase(self, user, audio_bytes):

        print(f"Processing audio for {user.name}...")

        audio_np = (np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0) # convert raw bytes to float32 array (whisper format)

        # ignore tiny clips < 0.5 seconds
        if len(audio_np) < 8000: 
            print(f"Skipping audio for {user.name}: clip too short")
            return

        loop = asyncio.get_running_loop()

        try:
            text, prob, reason = await loop.run_in_executor(None, lambda: self.transcribe(audio_np)) # run whisper in a seperate thread
        except Exception:
            return

        # if nothing was transcribed return
        if not text:
            return

        print(f"TRANSCRIPT | {user.name}: {text}")
        await self.process_command(user, text)    # use transcript to process command

    """
    Parses text for commands like 'Hey Echo', 'Move me', 'Disconnect'.
    """
    async def process_command(self, user, full_text):
        # check for wake word, play audio feedback to indicate bot is listening
        if "hey echo" in full_text or "echo" in full_text:
            self.last_wake_time[user.id] = time.time()

            vc = user.guild.voice_client   
            # play audio feedback if connected and not already playing something else
            if vc and vc.is_connected() and not vc.is_playing():
                try:
                    source = discord.FFmpegPCMAudio("noti_sound.mp3")
                    vc.play(source)
                except Exception as e:
                    print(f"Could not play sound: {e}")

        # check if user said wake word recently
        is_awake = (user.id in self.last_wake_time and time.time() - self.last_wake_time[user.id] < self.WAKE_WINDOW)

        if not is_awake:
            return

        # command execution
        if "disconnect" in full_text or "leave" in full_text:
            if user.voice:
                await user.move_to(None)

        elif "move" in full_text and "to" in full_text:
            match = re.search(r"to\s+(.+)", full_text)
            if match:
                target_name = match.group(1).strip()
                await self.move_user(user, target_name)

    """
    Finds the closest matching channel name using fuzzy matching and moves the user.
    """
    async def move_user(self, user, raw_target):

        clean_target = raw_target.translate(str.maketrans("", "", string.punctuation))

        channel_map = {
            c.name: c for c in user.guild.voice_channels
        }

        # using fuzzy matching to allow for stuff like "gender ball" to match "general"
        best_match = process.extractOne(clean_target, list(channel_map.keys()))

        if best_match:
            name, score = best_match
            if score >= 75:
                try:
                    # mark time to prevent bot from hearing its own move action
                    self.last_move_time[user.id] = time.time()

                    # clear buffer 
                    if user.id in self.phrase_buffer:
                        self.phrase_buffer[user.id] = bytearray()

                    await user.move_to(channel_map[name])
                    print(f"Moved {user.name} to {name}")
                except Exception as e:
                    print(f"Failed to move: {e}")

    """
    Triggered every time a packet of audio arrives from Discord.
    This function handles data collection only. Logic is handled by the Watchdog.
    """
    async def on_speech(self, user, voice_data):
        # if user disconnects mid-packet
        if user is None:
            return

        # ignore users audio if we just moved this user 
        if user.id in self.last_move_time:
            if time.time() - self.last_move_time[user.id] < 3.0:
                if user.id in self.phrase_buffer:
                    self.phrase_buffer[user.id] = bytearray()
                return
        
        # get raw PCM audio from discord
        pcm_data = voice_data.pcm
        if not pcm_data:
            return

        """audio processing pipeline - convert stereo to mono, downsample discords 48Khz to 16Khz to make it compatible with whisper"""

        # discord sends stereo 48kHz. whisper requires mono 16kHz 
        try:
            mono_data = audioop.tomono(pcm_data, 2, 1, 1)                      # convert stereo to mono
            audio_16k, _ = audioop.ratecv(mono_data, 2, 1, 48000, 16000, None) # downsample 48k -> 16k
        except Exception as e:
            print(f"Conversion Error: {e}")
            return

        # init buffer if this is the user's first packet
        if user.id not in self.phrase_buffer:
            self.phrase_buffer[user.id] = bytearray()
            self.last_speech_time[user.id] = 0
            self.speaking_state[user.id] = False

        # check if this specific packet contains human speech
        is_speech = self.is_voice_active(audio_16k)
        current_time = time.time()

        if is_speech:
            self.last_speech_time[user.id] = current_time
            self.speaking_state[user.id] = True
            self.phrase_buffer[user.id].extend(audio_16k)
        else:
            # buffer silence so the recording sounds natural (pauses between words)
            # the silence function ran in the background will decide when to cut it off.
             if self.speaking_state[user.id]:
                self.phrase_buffer[user.id].extend(audio_16k)

    """
    Run when a user joins/leaves/moves channels.
    Used strictly for garbage collection to prevent memory leaks.
    """
    async def on_voice_state_update(self, member, before, after):
        # detect a disconnect, clear buffers for that user
        if before.channel is not None and after.channel is None:
            print(f"Clearing buffers for {member.name}")
            self.phrase_buffer.pop(member.id, None)
            self.last_speech_time.pop(member.id, None)
            self.last_move_time.pop(member.id, None)

    """
    Check every 0.5s if a user has stopped talking.
    """
    @tasks.loop(seconds=0.5)
    async def check_silence(self):
        # iterate over copy of user_id keys to avoid runtime errors
        for user_id in list(self.phrase_buffer.keys()):
            if user_id not in self.last_speech_time:
                continue

            # if silence duration > threshold, process the audio
            if (time.time() - self.last_speech_time[user_id] > self.SILENCE_THRESHOLD):

                if len(self.phrase_buffer[user_id]) > 0:
                    audio_to_process = bytes(self.phrase_buffer[user_id])

                    del self.phrase_buffer[user_id] # clear buffer before processing so we don't duplicate

                    guild = self.guilds[0]
                    member = guild.get_member(user_id)

                    if member:
                        # offload to background task
                        asyncio.create_task(
                            self.process_complete_phrase(
                                member, audio_to_process
                            )
                        )
