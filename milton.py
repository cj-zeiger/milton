import asyncio
import discord
import logging
import functools
import os
import youtube_dl
import pprint
from gmusicapi import Mobileclient
from discord.ext import commands

if not discord.opus.is_loaded():
    # the 'opus' library here is opus.dll on windows
    # or libopus.so on linux in the current directory
    # you should replace this with the location the
    # opus library is located in and with the proper filename.
    # note that on windows this DLL is automatically provided for you
    discord.opus.load_opus('opus')

logging.basicConfig(level=logging.ERROR)

class VoiceEntry:
    def __init__(self, message, player):
        self.requester = message.author
        self.channel = message.channel
        self.player = player

    def __str__(self):
        fmt = '*{0.title}* requested by {1.display_name}'
        duration = self.player.duration
        if duration:
            fmt = fmt + ' [length: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))
        return fmt.format(self.player, self.requester)

class VoiceState:
    def __init__(self, bot):
        self.current = None
        self.voice = None
        self.bot = bot
        self.play_next_song = asyncio.Event()
        self.songs = asyncio.Queue()
        self.skip_votes = set() # a set of user_ids that voted
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())

    def is_playing(self):
        if self.voice is None or self.current is None:
            return False

        player = self.current.player
        return not player.is_done()

    @property
    def player(self):
        return self.current.player

    def skip(self):
        self.skip_votes.clear()
        if self.is_playing():
            self.player.stop()

    def toggle_next(self):
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)

    async def audio_player_task(self):
        while True:
            self.play_next_song.clear()
            self.current = await self.songs.get()
            await self.bot.send_message(self.current.channel, 'Now playing ' + str(self.current))
            self.current.player.start()
            await self.play_next_song.wait()

class Music:
    """Voice related commands.
    Works in multiple servers at once.
    """
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, server):
        state = self.voice_states.get(server.id)
        if state is None:
            state = VoiceState(self.bot)
            self.voice_states[server.id] = state

        return state

    async def create_voice_client(self, channel):
        voice = await self.bot.join_voice_channel(channel)
        state = self.get_voice_state(channel.server)
        state.voice = voice

    def __unload(self):
        for state in self.voice_states.values():
            try:
                state.audio_player.cancel()
                if state.voice:
                    self.bot.loop.create_task(state.voice.disconnect())
            except:
                pass

    @commands.command(pass_context=True, no_pm=True)
    async def join(self, ctx, *, channel : discord.Channel):
        """Joins a voice channel."""
        try:
            await self.create_voice_client(channel)
        except discord.ClientException:
            await self.bot.say('Already in a voice channel...')
        except discord.InvalidArgument:
            await self.bot.say('This is not a voice channel...')
        else:
            await self.bot.say('Ready to play audio in ' + channel.name)

    @commands.command(pass_context=True, no_pm=True)
    async def summon(self, ctx):
        """Summons the bot to join your voice channel."""
        summoned_channel = ctx.message.author.voice_channel
        if summoned_channel is None:
            await self.bot.say('You are not in a voice channel.')
            return False

        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            state.voice = await self.bot.join_voice_channel(summoned_channel)
        else:
            await state.voice.move_to(summoned_channel)

        return True

    @commands.command(pass_context=True, no_pm=True)
    async def play(self, ctx, *, song : str):
        """Plays a song.
        If there is a song currently in the queue, then it is
        queued until the next song is done playing.
        This command automatically searches as well from YouTube.
        The list of supported sites can be found here:
        https://rg3.github.io/youtube-dl/supportedsites.html
        """
        state = self.get_voice_state(ctx.message.server)
        opts = {
            'default_search': 'auto',
            'quiet': True,
        }

        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return

        try:
            if "http" in song:
                player = await state.voice.create_ytdl_player(song, ytdl_options=opts, after=state.toggle_next)
            else:
                player = await self.create_gmusic_player(song, state)
        except Exception as e:
            fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
            await self.bot.send_message(ctx.message.channel, fmt.format(type(e).__name__, e))
        else:
            player.volume = 0.6
            entry = VoiceEntry(ctx.message, player)
            await self.bot.say('Enqueued ' + str(entry))
            await state.songs.put(entry)

    @commands.command(pass_context=True, no_pm=True)
    async def radio(self, ctx, *, station_str : str):
        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return
        
        #search all radio stations
        loop = state.voice.loop
        func = functools.partial(api.search, station_str)
        result = await loop.run_in_executor(None, func)
        
        if result["station_hits"] is None:
            raise Exception("No Station Hits")
            
            
        station_hits = result["station_hits"]
        station = station_hits[0]["station"]
        print("picking first station: " + str(station["name"]))
        
        pp = pprint.PrettyPrinter(indent=1)
        pp.pprint(station)
        
        #get actualy station from search
        loop = state.voice.loop
        func = functools.partial(api.get_all_stations)
        result = await loop.run_in_executor(None, func)
        real_station = None
        for r in result:
            if r["name"] == station["name"]:
                real_station = r
        id = 0
        if real_station is None:
            #create the station by curation id
            seed = station["seed"]
            func = None
            if "curationStationId" in seed:
                func = functools.partial(api.create_station, station["name"], curated_station_id=seed["curationStationId"])
            elif "songId" in seed:
                func = functools.partial(api.create_station, station["name"], song_id=seed["songId"])
            elif "artistId" in seed:
                func = functools.partial(api.create_station, station["name"], artist_id=seed["artistId"])
            else:
                raise Exception("cannot create station")
            
            result = await loop.run_in_executor(None, func)
            id = result
        else:
            id = real_station["id"]
        
        print("ID: " + str(id))
                
        #get 10 tracks from the station
        loop = state.voice.loop
        func = functools.partial(api.get_station_tracks, id, num_tracks=10)
        result = await loop.run_in_executor(None, func)
        
        
        for track in result:
            try:
                player = await self.create_gmusic_player_by_id(track, state)
            except Exception as e:
                fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
                await self.bot.send_message(ctx.message.channel, fmt.format(type(e).__name__, e))
            else:
                player.volume = 0.6
                entry = VoiceEntry(ctx.message, player)
                await self.bot.say('Enqueued ' + str(entry))
                await state.songs.put(entry)
            
    async def create_gmusic_player_by_id(self, track, state):
        loop = state.voice.loop
        id = track['nid']
        realname = track['title'] + ' - ' + track['artist']
        func = functools.partial(api.get_stream_url,id)
        url = await loop.run_in_executor(None, func)
        if url is None:
            raise Exception("error retrieving song url")

        player = state.voice.create_ffmpeg_player(url,after=state.toggle_next)

        player.download_url = url
        player.title = realname
        player.duration = int(track['durationMillis'])

        return player
        
    async def create_gmusic_player(self, song, state):
        loop = state.voice.loop
        func = functools.partial(api.search,song,max_results=2)
        result = await loop.run_in_executor(None, func)
        print(result['song_hits'])
        if result['song_hits'] == []:
            raise Exception('Song not found')
        #checking for explicit version
        if (len(result['song_hits']) > 1) and (result['song_hits'][0]['track']['explicitType'] == '2') and (result['song_hits'][1]['track']['explicitType'] == '1') and (result['song_hits'][0]['track']['title'] == result['song_hits'][1]['track']['title']) and (result['song_hits'][0]['track']['albumArtist'] == result['song_hits'][1]['track']['albumArtist']):
        	#found explicit version
        	track = result['song_hits'][1]['track']
        else:
        	track = result['song_hits'][0]['track']

        id = track['nid']
        realname = track['title'] + ' - ' + track['artist']
        func = functools.partial(api.get_stream_url,id)
        url = await loop.run_in_executor(None, func)
        if url is None:
            raise Exception("error retrieving song url")

        player = state.voice.create_ffmpeg_player(url,after=state.toggle_next)

        player.download_url = url
        player.title = realname
        player.duration = int(track['durationMillis'])

        return player
    @commands.command(pass_context=True, no_pm=True)
    async def volume(self, ctx, value : int):
        """Sets the volume of the currently playing song."""

        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.volume = value / 100
            await self.bot.say('Set the volume to {:.0%}'.format(player.volume))

    @commands.command(pass_context=True, no_pm=True)
    async def pause(self, ctx):
        """Pauses the currently played song."""
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.pause()

    @commands.command(pass_context=True, no_pm=True)
    async def resume(self, ctx):
        """Resumes the currently played song."""
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.resume()

    @commands.command(pass_context=True, no_pm=True)
    async def stop(self, ctx):
        """Stops playing audio and leaves the voice channel.
        This also clears the queue.
        """
        server = ctx.message.server
        state = self.get_voice_state(server)

        if state.is_playing():
            player = state.player
            player.stop()

        try:
            state.audio_player.cancel()
            del self.voice_states[server.id]
            await state.voice.disconnect()
        except:
            pass

    @commands.command(pass_context=True, no_pm=True)
    async def skip(self, ctx):
        """Vote to skip a song. The song requester can automatically skip.
        3 skip votes are needed for the song to be skipped.
        """

        state = self.get_voice_state(ctx.message.server)
        if not state.is_playing():
            await self.bot.say('Not playing any music right now...')
            return
            
        await self.bot.say('Requester requested skipping song...')
        state.skip()
        

    @commands.command(pass_context=True, no_pm=True)
    async def playing(self, ctx):
        """Shows info about the currently played song."""

        state = self.get_voice_state(ctx.message.server)
        if state.current is None:
            await self.bot.say('Not playing anything.')
        else:
            skip_count = len(state.skip_votes)
            await self.bot.say('Now playing {} [skips: {}/3]'.format(state.current, skip_count))

bot = commands.Bot(command_prefix=commands.when_mentioned_or('!'), description='A playlist example for discord.py')
bot.add_cog(Music(bot))

@bot.event
async def on_ready():
    print('Logged in as:\n{0} (ID: {0.id})'.format(bot.user))

key = os.environ['MILTON_KEY']
email = os.environ['MILTON_GOOGLE_EMAIL']
app_password = os.environ['MILTON_APP_PASSWORD']
device_id = os.environ['MILTON_DEVICE_ID']

api = Mobileclient()
logged_in = api.login(email, app_password, device_id)
bot.run(key)

#Google music debugging

#pp = pprint.PrettyPrinter(indent=1)
#pp.pprint(api.get_all_playlists())
