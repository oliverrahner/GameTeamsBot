import discord
import re
from pprint import pprint
import logging
import config
from config import logger
from discord.ext import commands
import json
import asyncio
from discord.ext.ipc import Server
import random

state = {}
logger = config.logger
bot = commands.Bot(command_prefix='?gt.')
schimpfwords = open('schimpfwörter.txt', encoding="utf-8").read().splitlines()

class APIKeyException(Exception):
    pass

class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_cog(BotCog(self))
    

class BotCog(commands.Cog):
    CONFIG_FILE = "discordbotdata.json"

    CONFIG_LOBBY = "channel_lobby"
    CONFIG_TEAM1 = "channel_team1"
    CONFIG_TEAM2 = "channel_team2"
    CONFIG_USERMAPPING = "user_mapping"

    default_config = {
        CONFIG_LOBBY: "Allgemein",
        CONFIG_TEAM1: "team-1",
        CONFIG_TEAM2: "team-2",
        CONFIG_USERMAPPING: {}
    }
    
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        try:
            with open(self.CONFIG_FILE, 'r', encoding="utf8") as fp:
                self.globalstate = json.load(fp)
        except Exception:
            print("Couldn't load config file, proceeding with default")

    def write_config(self):
        with open(self.CONFIG_FILE, 'w', encoding="utf8") as fp:
            json.dump(self.globalstate, fp)

    @commands.Cog.listener()
    async def on_ready(self):
        print('Logged on as {0}!'.format(self.bot.user))
        print('I am member of {0} guilds'.format(len(self.bot.guilds)))

    @commands.command(name="unite")
    async def unite(self, ctx):
        state = self.get_state(ctx.guild.id)

        guild = ctx.guild
        team1 = self.get_voice_members(guild, state["channel_team1"])
        team2 = self.get_voice_members(guild, state["channel_team2"])
        # move all team1 users to lobby
        for member in team1:
            logger.debug("Trying to move user {} to lobby channel".format(member.name))
            await member.move_to(discord.utils.get(guild.voice_channels, name=state["channel_lobby"]))
        # move all team2 users to lobby
        for member in team2:
            logger.debug("Trying to move user {} to lobby channel".format(member.name))
            await member.move_to(discord.utils.get(guild.voice_channels, name=state["channel_lobby"]))




    @commands.group(name="channel")
    async def channel(self, ctx):
        pass

    @channel.command(name="status")
    async def status(self, ctx):
        await self.post_status(ctx)

    @channel.command(name="lobby")
    @commands.has_permissions(administrator=True)
    async def set_lobby(self, ctx, *, channame):
        state = self.get_state(ctx.guild.id)
        state["channel_lobby"] = channame
        self.write_config()
        await self.post_status(ctx)

    @channel.command(name="team1")
    @commands.has_permissions(administrator=True)
    async def set_team1(self, ctx, *, channame):
        state = self.get_state(ctx.guild.id)
        state["channel_team1"] = channame
        self.write_config()
        await self.post_status(ctx)

    @channel.command(name="team2")
    @commands.has_permissions(administrator=True)
    async def set_team2(self, ctx, *, channame):
        state = self.get_state(ctx.guild.id)
        state["channel_team2"] = channame
        self.write_config()
        await self.post_status(ctx)

    async def post_status(self, ctx):
        err = False
        state = self.get_state(ctx.guild.id)
        message = ctx.message
        guild = message.guild
        channels = guild.voice_channels
        lobby = next((chan for chan in channels if chan.name == state["channel_lobby"]), None)
        lobby_exists = lobby is not None

        team1 = next((chan for chan in channels if chan.name == state["channel_team1"]), None)
        team1_exists = team1 is not None

        team2 = next((chan for chan in channels if chan.name == state["channel_team2"]), None)
        team2_exists = team2 is not None
        
        embed = discord.Embed(title="Status")

        err = not (lobby_exists and team1_exists and team2_exists)
        if err:
            embed.colour = 15158332 # RED / #e74c3c
        else:
            embed.colour = 65280 # GREEN / #00ff00

        embed.add_field(name="Lobby Channel", value=state["channel_lobby"], inline=not lobby_exists)
        if not lobby_exists:
            embed.add_field(name="Exists", value="NO", inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Team 1 Channel", value=state["channel_team1"], inline=not team1_exists)
        if not team1_exists:
            embed.add_field(name="Exists", value="NO", inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Team 2 Channel", value=state["channel_team2"], inline=not team2_exists)
        if not team2_exists:
            embed.add_field(name="Exists", value="NO", inline=True)
        await ctx.channel.send(embed=embed)

    def get_state(self, guildid):
        guildid = str(guildid)
        if not hasattr(self, "globalstate"):
            self.globalstate = {}
        if self.globalstate.get(guildid) is None:
            self.globalstate[guildid] = {}
        state = self.globalstate[guildid]
        if state.get("teams") is None:
            state["teams"] = {}
        if state.get("usermapping") is None:
            state["usermapping"] = {}
        if state.get("mappingquestions") is None:
            state["mappingquestions"] = {}
        if state.get("channel_lobby") is None:
            state["channel_lobby"] = "Allgemein"
        if state.get("channel_team1") is None:
            state["channel_team1"] = "team-1"
        if state.get("channel_team2") is None:
            state["channel_team2"] = "team-2"
        return self.globalstate[guildid]

    @commands.command(name = "team")
    async def cmd_set_team(self, ctx, teamnum: int, *args):
        members = await self.set_team(ctx.channel, teamnum, args)

        await ctx.channel.send("Team {} ist nun: {}".format(teamnum, ", ".join([m.name for m in members])))

    async def set_team(self, channel, teamnum: int, names: list):
        state = self.get_state(channel.guild.id)
        members = ""
        teamnum = str(teamnum)
        state["teams"][teamnum] = []

        # clean up old clearing messages
        logger.debug("Cleaning up old clearing messages...")
        deletions = []
        for msgid, q in state["mappingquestions"].items():
            if q["team"] == teamnum:
                try:
                    message = await channel.fetch_message(msgid)
                except discord.NotFound:
                    message = None
                else:
                    deletions.append(message.delete())
        if len(deletions) > 0:
            await asyncio.wait(deletions)
        state["mappingquestions"] = {k: v for k, v in state["mappingquestions"].items() if v["team"] != teamnum}

        members, unmatchednames = await self.match_names(channel, names)

        for member in members:
            self.add_teammember(channel.guild, teamnum, member)
        self.write_config()

        logger.debug("Sending clearing messages...")
        for name in unmatchednames:
            # post clarification message
            await self.post_nameclearing(channel, name, teamnum)

        return members

    def add_teammember(self, guild, team, user):
        state = self.get_state(guild.id)
        if not state["teams"].get(str(team)):
            state["teams"][str(team)] = []
        state["teams"][str(team)].append(user.id)
        state["teams"][str(team)] = list(set(state["teams"][str(team)]))

        self.write_config()
        # TODO: move user to channel

    async def add_usermapping(self, state, user, name):
        if not state["usermapping"].get(str(user.id)):
            state["usermapping"][str(user.id)] = []
        
        if not name in state["usermapping"][str(user.id)]:
            state["usermapping"][str(user.id)].append(name)
        
        self.write_config()

    async def post_nameclearing(self, channel, name, teamnum: int):
        state = self.get_state(channel.guild.id)
        msg = await channel.send("Welche{} ist **{}**?".format(random.choice(schimpfwords),name))
        await msg.add_reaction("👋")
        state["mappingquestions"][str(msg.id)] = {}
        state["mappingquestions"][str(msg.id)]["name"] = name
        state["mappingquestions"][str(msg.id)]["team"] = teamnum
        self.write_config()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, event):
        user = event.member
        if user == self.bot.user:
            return

        guild = self.bot.get_guild(event.guild_id)
        channel = self.bot.get_channel(event.channel_id)
        message = await channel.fetch_message(event.message_id)
        emoji = event.emoji

        state = self.get_state(guild.id)
        if str(message.id) in state["mappingquestions"]:
            q = state["mappingquestions"][str(message.id)]
            if emoji.name == '👋':
                await self.add_usermapping(state, user, q["name"])
                self.add_teammember(guild, q["team"], user)
                await message.clear_reaction('👋')
                await message.edit(content="~~{}~~ Es ist {}".format(message.content, user.name))
                del state["mappingquestions"][str(message.id)]
                if user.voice is not None:
                    await user.move_to(discord.utils.get(guild.voice_channels, name=state["channel_team{}".format(q["team"])]))
                self.write_config()

    async def match_names(self, channel, names: list):
        guildmembers = channel.guild.members
        members = []
        unmatchednames = []
        state = self.get_state(channel.guild.id)
        for name in names:

            # check if name has already been mapped
            founduser = None
            for userid, aliases in state["usermapping"].items():
                if name.lower() in [a.lower() for a in aliases]:
                    founduser = userid
                    break
        
            if founduser:
                member = channel.guild.get_member(int(founduser))
                members.append(member)
                continue

            # check if name is identical to username or nickname
            founduser = discord.utils.get(guildmembers, name=name)
            if founduser:
                await self.add_usermapping(state, founduser, name)
                members.append(founduser)
                continue

            # add name to unmatched list
            unmatchednames.append(name)

            #ctx.guild.
        return members, unmatchednames

    @commands.command(name = "sort")
    @commands.has_permissions(administrator=True)
    async def cmd_sort(self, ctx):
        await self.sort(ctx.channel)

    async def sort(self, channel):
        state = self.get_state(channel.guild.id)
        await self.sort_users(channel, state["teams"]["1"], state["teams"]["2"])

    def get_voice_members(self, guild, channelname):
        voice_channel = discord.utils.get(guild.channels, name=channelname)
        members = voice_channel.members
        return members

    def get_all_voice_members(self, guild):
        members = []
        for v in guild.voice_channels:
            members.extend(v.members)
        return members

    def get_members_from_ids(self, guild, ids):
        members = []
        for curid in ids:
            members.append(guild.get_member(curid))
        return members

    async def sort_users(self, channel, team1: list, team2: list):
        guild = channel.guild
        state = self.get_state(guild.id)

        team1_members = self.get_members_from_ids(guild, team1)
        team2_members = self.get_members_from_ids(guild, team2)

        clients = self.get_all_voice_members(guild)
        team1 = self.get_voice_members(guild, state["channel_team1"])
        team2 = self.get_voice_members(guild, state["channel_team2"])

        offline_members = []
        # put all team 1 members in team 1
        for member in team1_members:
            if member not in clients:
                offline_members.append(member)
            elif member not in team1:
                logger.debug("Trying to move user {} to team 1 channel".format(member.name))
                await member.move_to(discord.utils.get(guild.voice_channels, name=state["channel_team1"]))
        # put all team 2 members in team 2
        for member in team2_members:
            if member not in clients:
                offline_members.append(member)
            elif member not in team2 and member in clients:
                logger.debug("Trying to move user {} to team 2 channel".format(member.name))
                await member.move_to(discord.utils.get(guild.voice_channels, name=state["channel_team2"]))

        team1 = self.get_voice_members(guild, state["channel_team1"])
        team2 = self.get_voice_members(guild, state["channel_team2"])
        # remove non-team 1 members from team 1
        for member in team1:
            if member not in team1_members:
                logger.debug("Trying to move user {} to lobby channel".format(member.name))
                await member.move_to(discord.utils.get(guild.voice_channels, name=state["channel_lobby"]))
        # remove non-team 2 members from team 2
        for member in team2:
            if member not in team2_members:
                logger.debug("Trying to move user {} to lobby channel".format(member.name))
                await member.move_to(discord.utils.get(guild.voice_channels, name=state["channel_lobby"]))

        if len(offline_members) > 0:
            content = "Die folgenden Member sind in keinem Voice-Channel:"
            for member in offline_members:
                content = "{}\n{}".format(content, member.mention)

            await channel.send(content=content)

intents = discord.Intents.default()
intents.members = True

b = Bot(command_prefix = commands.when_mentioned_or("?gt."), case_insensitive=True, intents=intents)
b_ipc = Server(bot, "0.0.0.0", 8765, config.API_TOKEN)

@b_ipc.route()
async def sort_users(request):
    try:
        cog = b.cogs["BotCog"]
        data = request.data
        guildid = data["guild"]
        guild = b.get_guild(guildid)
        print(f"Guild is {guild}")
        channel = guild.text_channels[0]

        await cog.set_team(channel, 1, data["team1"])
        await cog.set_team(channel, 2, data["team2"])
        await cog.sort(channel)
    except Exception as ex:
        logging.exception(ex)
        
    return {}

b_ipc.start()
b.run(config.BOT_TOKEN)
