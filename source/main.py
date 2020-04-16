import discord
from discord import Colour, Embed
from discord.ext import commands

import datetime

import ladderdb

# Reads Discord bot token from token file
try:
    discordTokenFile = open('Discord.token', 'r')
    discordToken = discordTokenFile.read()
    discordTokenFile.close()
except:
    print('Could not read Discord token file')
    sys.exit('Invalid Discord token file or data')

# Initializes Bot
prefix = '.1v1'
bot = commands.Bot(command_prefix=prefix)


# Initializes database
db = ladderdb.LadderDatabase('MySQL.token')
print('Successfully connected to database')


### HELP FUNCTIONS ###

# Returns true if the author of the message has admin or owner rights and sends a message if not
async def hasAdminRights(ctx: commands.Context, bot: commands.Bot):
    if not db.isLadderAdmin(ctx.author) and not await bot.is_owner(ctx.author):
        await ctx.send("You must be an admin to use this command!")
        return False
    else:
        return True

# Returns true if the author of the message is signed up for the ladder and sends a message if not
async def isLadderPlayer(ctx: commands.Context):
    if not db.isLadderPlayer(ctx.author):
        await ctx.send("You must participate in the 1v1 ladder to use this command. Sign up using .1v1signup!")
        return False
    else:
        return True

async def isOnlySignupAllowed(ctx: commands.Context):
    if int(db.getConfig('signup_only')) == 1:
        await ctx.send("Currently you can only sign up. Challenges will be enabled after the signup-period.")
        return True
    else:
        return False

def timeToString(date: datetime.datetime) -> str:
    return f"{date.day}.{date.month}.{date.year}, {date.hour}:{date.minute}"


# Kicks the given player from the ladder and removes their role
async def kickPlayer(ctx, player, kickedBy: str, reason = ''):
    # Remove target's ladder role
    ladderRole = discord.utils.get(ctx.guild.roles, id = int(db.getConfig('ladder_role')))
    kickReason = f"Kicked from the ladder by {kickedBy}"
    if not reason == '':
        kickReason += f". Reason: '{reason}'"
    await player.remove_roles(ladderRole, reason = kickReason)

    # Remove player from database
    db.kickPlayer(player.id)
    
    # Update standings message
    await updateRankingMessage(ctx)

# Edits the ranking message with the new standings, or posts a new message if it doesn't exist
def generateRankingEmbed(ctx):

    # Initializes Embed
    embed = Embed(
        title = '1v1 Ladder',
        type = 'rich',
        colour = discord.Colour.blue()
    )

    embed.set_thumbnail(url = 'https://i.imgur.com/hr90KaS.png')
    embed.set_footer(text = 'European Community Championship', icon_url = 'https://i.imgur.com/u2HPdEi.png')

    # Gets current ranking and column paddings
    rankedPlayers = db.getRanking()
    rankPadding = getRankPadding(rankedPlayers)
    namePadding = getNamePadding(ctx, rankedPlayers)
    winlossPadding = getWinLossPadding(rankedPlayers)
    titlePadding = getTitlesPadding(rankedPlayers)

    # Generates all tier fields
    previousTier = 1
    tierMessage = ''

    for player in rankedPlayers:
        if player.tier > previousTier:
            embed.add_field(name = f"Tier {previousTier}", value = f"```{tierMessage}```", inline = False)
            tierMessage = ''
            previousTier = player.tier
        
        member = ctx.guild.get_member(player.discordID)

        rankStr = pad(str(player.rank) + '.', rankPadding + 1)
        nameStr = pad(member.name, namePadding)
        winlossStr = pad(f"{player.wins}-{player.losses}", winlossPadding)

        titleStr = ''
        if player.titles > 0:
            titleStr = str(player.titles) + 'P'
        titleStr = pad(titleStr, titlePadding + 1)

        tierMessage += f"\n{rankStr} {nameStr} | {winlossStr} | {titleStr}"

    if not tierMessage == '':
        embed.add_field(name = f"Tier {previousTier}", value = f"```{tierMessage}```", inline = False)
    
    return embed

# Retrieves ranking message and updates it with the new ranking    
async def updateRankingMessage(ctx):
    rankingEmbed = generateRankingEmbed(ctx)
    rankingMessage = await getRankingMessage(ctx)

    if rankingMessage is None:
        rankingChannelID = int(db.getConfig('ranking_channel'))
        rankingChannel = ctx.guild.get_channel(rankingChannelID)

        rankingMessage = await rankingChannel.send(embed = rankingEmbed)
        db.setConfig('ranking_message', rankingMessage.id)
    else:
        await rankingMessage.edit(embed = rankingEmbed)

# Returns the width required for a column to fit all names
def getNamePadding(ctx, players):
    longestName = 0
    for playerInfo in players:
        player = ctx.guild.get_member(playerInfo.discordID)

        if len(player.name) > longestName:
            longestName = len(player.name)
    
    return longestName

# Returns the width required for a column to fit all rankings
def getRankPadding(players):
    rankStr = str(players[-1].rank)
    return len(rankStr)

# Returns the width required for a column to fit all win-loss records
def getWinLossPadding(players):
    longestWinLoss = 0
    for playerInfo in players:
        winLossStr = f"{playerInfo.wins}-{playerInfo.losses}"

        if len(winLossStr) > longestWinLoss:
            longestWinLoss = len(winLossStr)

    return longestWinLoss

def getTitlesPadding(players):
    longestTitle = 0
    for playerInfo in players:
        titleStr = str(playerInfo.titles)
        
        if len(titleStr) > longestTitle:
            longestTitle = len(titleStr)
    
    return longestTitle

# Pads a string with whitespaces so that it matches the given character count
def pad(text: str, characters: int) -> str:
    padding = characters - len(text)

    if padding > 0:
        return text + ' '*padding
    else:
        return text

# Returns the ranking message object or None if it can't be found
async def getRankingMessage(ctx):
    rankingChannelID = int(db.getConfig('ranking_channel'))
    rankingMessageID = int(db.getConfig('ranking_message'))

    rankingChannel = ctx.guild.get_channel(rankingChannelID)

    try:
        rankingMessage = await rankingChannel.fetch_message(rankingMessageID)
        return rankingMessage
    except discord.errors.NotFound:
        return None

### BOT COMMANDS ###
@bot.command()
async def ping(ctx):
    # 1. Checks if posted in general channel
    if not db.isGeneralChannel(ctx.channel):
        return

    # 2. Checks for admin permissions
    if not await hasAdminRights(ctx, bot):
        return

    # 3. Sends pong and updates ranking
    await ctx.send('pong')
    await updateRankingMessage(ctx)

# Used by users to enter the ladder
@bot.command()
async def signup(ctx):
    # 1. Check if posted in general channel
    if not db.isGeneralChannel(ctx.channel):
        return

    # 2. Check if user already is in the ladder
    alreadySignedUp = db.isPlayerSignedUp(ctx.author.id)

    # 2a. Yes: Display message and quit
    if alreadySignedUp:
        await ctx.send("You're already signed up!")
        return

    # 2b. No: Continue

    # 3. Add user to database and gives them a rank
    db.addPlayer(ctx.author.id)

    # 4. Give user ladder role
    ladderRole = discord.utils.get(ctx.guild.roles, id = int(db.getConfig('ladder_role')))
    await ctx.author.add_roles(ladderRole, reason = 'Signed up for 1v1 ladder')

    # 5. Add user to ranking
    await updateRankingMessage(ctx)

    # 6. Display success message
    await ctx.send("Welcome to the 1v1 ladder!")


# Used by users to challenge other users in the ladder
@bot.command()
async def challenge(ctx, opponent: commands.MemberConverter = None):
    # 1. Checks if posted in general channel
    if not db.isGeneralChannel(ctx.channel):
        return

    # 2. Check if user has ladder role to use this command
    if not await isLadderPlayer(ctx):
        return

    # 3. Check if signup-only mode is active
    if await isOnlySignupAllowed(ctx):
        return
        
    ladder = db.getConfig('current_ladder')

    # 4. If no opponent was given, display the currently active challenge for the user
    if opponent is None:
        activeChallenge = db.getActiveChallenge(ctx.author.id, ladder)
        message = ''

        # If user has no active challenge, display potential candidates
        if activeChallenge is None:
            message += "You don't have any outstandings challenges!"

            possibleChallenges = db.getPossibleChallenges(ctx.author.id)

            if len(possibleChallenges) > 0:
                message += "\nPlayers you could challenge: "

                for potentialOpponentID in possibleChallenges:
                    potentialOpponent = ctx.guild.get_member(potentialOpponentID)
                    message += f"\n{potentialOpponent.name}"

        elif activeChallenge.challenger == ctx.author.id:
            opponent = ctx.guild.get_member(activeChallenge.opponent)
            message += f"You challenged {opponent.name}. Play your game until {timeToString(activeChallenge.deadline)}!"
        else:
            opponent = ctx.guild.get_member(activeChallenge.challenger)
            message += f"{opponent.name} challenged you! Play your game until {timeToString(activeChallenge.deadline)}."

        timeouts = db.getTimeoutInfo(ctx.author.id, ladder)

        if timeouts is not None and timeouts.outgoingTimeout is not None:
            message += f"\nYou're on timeout and can't challenge others until {timeToString(timeouts.outgoingTimeout)}."
        
        if timeouts is not None and timeouts.incomingTimeout is not None:
            message += f"\nYou're protected from challenges until {timeToString(timeouts.incomingTimeout)}."

        await ctx.send(message)
        return

    # 5. Check if user can challenge other user:
    # 5a. Is user trying to challenge themself?
    isChallengingThemself = (ctx.author.id == opponent.id)

    if isChallengingThemself:
        await ctx.send("You can't challenge yourself!")
        return

    # 5b. Is challenged user even signed up?
    isOpponentSignedUp = db.isPlayerSignedUp(opponent.id, ladder)

    if not isOpponentSignedUp:
        await ctx.send(f"{opponent.name} isn't signed up for the ladder. Please only challenge players that already play in the ladder!")
        return

    # 5c. Is user in timeout?
    hasChallengerTimeout = db.hasChallengeTimeout(ctx.author.id, ladder)

    if hasChallengerTimeout:
        await ctx.send("Slow down! You're still on cooldown from your last game, so that other players can challenge you.")
        return

    # 5d. Is the other player in a rank or tier that allows the challenge?
    isChallengePermitted = db.canChallenge(ctx.author.id, opponent.id, ladder)

    if not isChallengePermitted:
        await ctx.send(f"You can't challenge {opponent.name}! They must be either in the tier above yours, or in the same tier but higher ranked.")
        return


    # 5e. Is user already challenging someone?
    userActiveChallenge = db.getActiveChallenge(ctx.author.id, ladder)

    if userActiveChallenge is not None:
        await ctx.send(f"You can't have more than one active challenge! Use '{prefix}challenge' to get info about your current challenge.")
        return

    # 5f. Is challenged user in universal timeout?
    hasOpponentChallengeProtection = db.hasChallengeProtection(opponent.id, ladder)

    if hasOpponentChallengeProtection:
        await ctx.send(f"{opponent.name} currently has challenge protection. You can challenge them once it has expired!")
        return

    # 5g. Is opponent already challenging/getting challenged?
    opponentActiveChallenge = db.getActiveChallenge(opponent.id, ladder)

    if opponentActiveChallenge is not None:
        await ctx.send(f"{opponent.name} is already in a challenge against someone else!")
        return

    # 5h. Did the user already play against this opponent last game?
    lastChallengeInfo = db.getLastPlayedChallenge(ctx.author.id, ladder)

    didPlaySameOpponentLastGame = False

    if lastChallengeInfo is not None:
        didPlaySameOpponentLastGame = (lastChallengeInfo.challenger == opponent.id or lastChallengeInfo.opponent == opponent.id)

    if didPlaySameOpponentLastGame:
        await ctx.send(f"You already played against {opponent.name} in your previous game! You have to play at least one other player before you can challenge the same person again.")
        return

    # 6. Add challenge to database
    db.addChallenge(ctx.author.id, opponent.id)

    # 7. Display success message
    challengeTimeout = db.getConfig('challenge_timeout')
    await ctx.send(f"{ctx.author.mention} has challenged {opponent.mention}! Play your game in the next {challengeTimeout} days and report the result using {prefix}report W/L.")


# Used by users or admins to cancel challenges
@bot.command()
async def cancel(ctx, player = None):
    # 1. Check if correct channel
    if not db.isGeneralChannel(ctx.channel) and not await hasAdminRights(ctx, bot):
        return

    # 2. Check if user has either permission to run this command:
    if player is None:
        # 2a. Ladder role if no player arugment is given
        if not await isLadderPlayer(ctx):
            return
        else:
            player = ctx.author
    else:
        # 2b. Admin role if player argument is given
        if not await hasAdminRights(ctx, bot):
            return

    # 3. Check if signup-only mode is active
    if await isOnlySignupAllowed(ctx):
        return

    # 4. Get info about active challenge
    ladder = db.getConfig('current_ladder')
    activeChallenge = db.getActiveChallenge(player.id, ladder)

    if activeChallenge is None:
        await ctx.send(f"There are no active challenges for {player.name} that could be cancelled!")
        return

    # 5. Update the challenge to cancelled/denied state in the database
    db.cancelActiveChallenge(player.id, ladder)

    # 6. Update number of cancellations for the player
    cancels = db.incrementCancelCounter(player.id, ladder)

    # 7. Kick the player if the number of cancellations exceeds the maximum permitted number
    challenger = ctx.guild.get_member(activeChallenge.challenger)
    opponent = ctx.guild.get_member(activeChallenge.opponent)
    message = f"The game between {challenger.mention} and {opponent.mention} has been cancelled."

    maxCancels = int(db.getConfig('num_cancels'))
    if cancels > maxCancels:
        await kickPlayer(ctx, player, "1v1 bot", f"Exceeded maximum amount of cancellations ({maxCancels})")
        
        message += f"\n{player.mention} has been kicked from the ladder for exceeding the allowed number of cancellations ({maxCancels})."
    else:
        message += f"\nIt was cancelled by {player.mention} who has {maxCancels - cancels} out of {maxCancels} cancellations remaining."

    # 8. Display success message, @ both users
    await ctx.send(message)


# Used by users or admins to report game results
@bot.command()
async def report(ctx, result, player = None):
    # 1. Check if correct channel
    if not db.isGeneralChannel(ctx.channel):
        return

    # 2. Check if user has either permission to run this command:
    if player is None:
        # 2a. Ladder role if no player arugment is given
        if not await isLadderPlayer(ctx):
            return
        else:
            player = ctx.author
    else:
        # 2b. Admin role if player argument is given
        if not await hasAdminRights(ctx, bot):
            return

    # 3. Checks if signup-only mode is active
    if await isOnlySignupAllowed(ctx):
        return

    # 4. Check if user has a challenge that can be reported
    ladder = db.getConfig('current_ladder')
    activeChallenge = db.getActiveChallenge(player.id, ladder)

    if activeChallenge is None:
        await ctx.send(f"There are no active challenges for {player.name} that could be reported.")
        return

    # 5. Check if result string is valid (either W(in) or L(oss))
    result = result.lower()

    gameWon = True
    if result.startswith('w'):
        gameWon = True
    elif result.startswith('l'):
        gameWon = False
    else:
        await ctx.send("Invalid game result: Enter 'W' if you won the game or 'L' if you lost!")
        return
    
    # 6. Makes sure "gameWon" is true if the challenger won and false if they lost
    if not activeChallenge.challenger == player.id:
        gameWon = not gameWon

    # 7. Update challenge and ranking in the database
    db.reportResult(activeChallenge, gameWon, ladder)

    # 8. Timeout the challenging player from challenging for the configured time
    outgoingCooldown = db.getConfig('outgoing_cooldown')
    db.giveChallengeCooldown(activeChallenge.challenger, outgoingCooldown, ladder)

    # 9. Give challenged player challenge protection
    challengeProtection = db.getConfig('challenge_protection')
    db.giveChallengeProtection(activeChallenge.opponent, challengeProtection, ladder)

    # 10. Edit ranking message
    await updateRankingMessage(ctx)

    # 11. Display success message: Maybe information if someone gets promoted to a new tier, who got timeout
    await ctx.send('Game result has been reported!')


# Used by admins to dispute a reported result and reverse it
@bot.command()
async def dispute(ctx, player: commands.MemberConverter):
    # 1. Check for admin rights
    if not await hasAdminRights(ctx, bot):
        return
    
    # 2. Check if player is playing in ladder
    if not db.isLadderPlayer(player):
        await ctx.send(f"{player.name} isn't signed up for the ladder!")
        return
    
    # 3. Get last played challenge
    ladder = db.getConfig('current_ladder')
    lastChallengeInfo = db.getLastPlayedChallenge(player.id, ladder)

    # 4. Reverse challenge report
    db.reverseReport(player.id, lastChallengeInfo, ladder)

    # 5. Update ranking
    await updateRankingMessage(ctx)

    # 6. Feedback
    challenger = ctx.guild.get_member(lastChallengeInfo.challenger)
    opponent = ctx.guild.get_member(lastChallengeInfo.opponent)
    await ctx.send(f"The reported result for the game between {challenger.mention} and {opponent.mention} has been disputed.")

# Used by admins to cancel all overdue challenges
@bot.command()
async def clear(ctx):
    # 1. Check if user has the admin role
    if not await hasAdminRights(ctx, bot):
        return

    # 2. Fetch all outstanding challenges from the database that are overdue
    affectedGames = db.cancelAllOverdueChallenges()

    # 3. Cancel all overdue challenges and kick players with too many cancellations
    message = ""

    if len(affectedGames) == 0 or affectedGames[0] is None:
        message = "No matches were overdue!"
    else:
        maxCancels = int(db.getConfig('num_cancels'))

        for game in affectedGames:
            challenger = ctx.guild.get_member(game.challenger)
            opponent = ctx.guild.get_member(game.opponent)

            message += f"{challenger.mention} vs {opponent.mention} has been cancelled.\n"

            if game.challengerCancels > maxCancels:
                await kickPlayer(ctx, challenger, "1v1 bot", f"Exceeded maximum amount of cancellations ({maxCancels})")
                message += f"{challenger.mention} has been kicked from the ladder for exceeding the allowed maximum number of cancellations ({maxCancels}).\n"
            else:
                message += f"{challenger.mention} has {maxCancels - game.challengerCancels} out of {maxCancels} cancellations remaining.\n"

            if game.opponentCancels > maxCancels:
                await kickPlayer(ctx, opponent, "1v1 bot", f"Exceeded maximum amount of cancellations ({maxCancels})")
                message += f"{opponent.mention} has been kicked from the ladder for exceeding the allowed maximum number of cancellations ({maxCancels}).\n"
            else:
                message += f"{opponent.mention} has {maxCancels - game.opponentCancels} out of {maxCancels} cancellations remaining.\n"


    # 4. Display success message: @ users whose challenges got cancelled by this
    await ctx.send(message)

# Used by admins to kick players from the ladder
@bot.command()
async def kick(ctx, player: commands.MemberConverter, reason = ''):
    # 1. Check if user has admin role
    if not await hasAdminRights(ctx, bot):
        return

    # 2. Check if target is part of the ladder
    if not db.isLadderPlayer(player):
        await ctx.send("Player isn't participating in the 1v1 ladder!")
        return

    # 3. Remove ladder role and delete player from ladder database, update ranking
    await kickPlayer(ctx, player, ctx.author.name, reason)

    # 4. Display success message
    kickMessage = f"{player.name} was kicked from the ladder."
    if not reason == '':
        kickMessage += f" Reason: '{reason}'"
    await ctx.send(kickMessage)
    await ctx.message.delete()


# Used by admins to time out users from the ladder
@bot.command()
async def timeout(ctx, player: commands.MemberConverter, duration: int):
    # 1. Check if user has admin role
    if not await hasAdminRights(ctx, bot):
        return

    # 2. Check if target is part of the ladder
    if not db.isLadderPlayer(player):
        await ctx.send(f"{player.name} isn't signed up for the ladder and therefore can't be timed out!")
        return

    # 3. Add timeout to the database for outgoing and incoming challenges
    db.giveChallengeCooldown(player.id, duration)
    db.giveChallengeProtection(player.id, duration)

    # 4. Display success message
    if duration > 0:
        await ctx.send(f"{ctx.author.name} timed out {player.mention} for {duration} days.")
    else:
        await ctx.send(f"{ctx.author.name} removed {player.mention}'s timeout.")

# Used by admins to shuffle the ladder after signups
@bot.command()
async def shuffle(ctx):
    # 1. Check if user has admin role
    if not await hasAdminRights(ctx, bot):
        return

    # 2. Check if signup-only mode is enabled
    if not int(db.getConfig('signup_only')) == 1:
        await ctx.send("The ladder can only be shuffled when signup-only mode is enabled!")
        return

    # 3. Shuffle the ladder
    db.shuffleLadder()

    # 4. Update the ranking
    await updateRankingMessage(ctx)

    # 5. Feedback
    await ctx.send("The ladder has been shuffled!")

# Used by admins to configure the bot
@bot.command()
async def config(ctx, name, value = ''):
    # 1. Check if user has admin role
    if not await hasAdminRights(ctx, bot):
        return

    # 2. Check if value should be loaded or set
    # 2a. Load and display value
    if value == '':
        try:
            value = db.getConfig(name)
        except:
            await ctx.send(f"Invalid configuration name '{name}'!")
            return
        
        if name == 'admin_role' or name == 'ladder_role':
            value = f"<@&{value}>"
        
        if name == 'general_channel' or name == 'ranking_channel':
            value = f"<#{value}>"

        await ctx.send(f"'{name}' = '{value}'")
        return

    # 2b. Update value of the configuration
    else:
        # Convert value to required datatype
        if value.startswith('<@&'):
            value = value[3:-1]
        if value.startswith('<#'):
            value = value[2:-1]

        try:
            db.setConfig(name, value)
        except:
            await ctx.send(f"Invalid configuration name '{name}'!")
            return

    # 3. Display success message
    await ctx.send(f"Set '{name}' to '{value}'!")

# Runs bot
print('Starting bot...')
bot.run(discordToken)