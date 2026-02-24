# Echo

Echo is a Discord bot that listens to voice channels and responds to voice commands.  
It uses **Open Ai's Whisper** for speech-to-text and can move users, disconnect them, or respond to a wake word.

## Features

- **Voice Recognition:** Detects when a user is speaking in a voice channel.  
- **Wake Word:** Responds to "Hey Echo" to start listening for commands.  
- **Voice Commands:** 
  - Move users to another voice channel (`"move me to [channel name]"`)
  - Move all users in current voice channel to another voice channel (`"move us to [channel name]"`)
  - Server Deafen/Undeafen (`"silence/listen"`)
  - Drag users to another call (`"drag [user] to [channel name]"`)
  - Disconnect from voice channel (`"disconnect"` or `"leave"`) 
- **Automatic Cleanup:** Clear audio buffers when users leave a channel to prevent memory leaks/inconsistent state.  

## Requirements

- Python 3.12+  
- `discord.py`, `fuzzywuzzy`, `webrtcvad`, `numpy`, `faster-whisper`  
- A valid Discord bot token  

## Usage

1. Create venv & Install dependencies:  
```bash
python3 -m venv venv            # create venv
source venv/bin/activate        # activate venv
pip install -r requirements.txt # install dependencies
```

2. Add your Discord token to .env:
```
DISCORD_TOKEN=your_token_here
```
3. Run the Bot:
```
python3 main.py
```

4. Join a voice channel and use the `/listen` command to start talking to Echo.

## Notes
- Bot only processes when you say `hey echo` first
- Handles short pauses and only processes complete phrases to avoid partial transcripts.
- Work In Progress

## Planned / Upcoming Commands

- **Volume Control:** Command to Mute/unmute specific users.
- **Manage Chat:** Command to delete messages.  
- **Timers / Reminders:** Set a timer or remind users in VC.  
- **Music Control:** Play/pause/skip music in voice channels.  

*(More features will be added over time!)*
