import discord
from discord import Colour, Embed
from discord.ext import commands

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
bot = commands.Bot(command_prefix='.1v1')


# Initializes database
db = ladderdb.LadderDatabase('MySQL.token')
print('Successfully connected to database')


### HELP FUNCTIONS ###
async def hasAdminRights(ctx: commands.Context, bot: commands.Bot):
    if not db.isLadderAdmin(ctx.author) and not await bot.is_owner(ctx.author):
        await ctx.send("You must be an admin to use this command!")
        return False
    else:
        return True

async def isLadderPlayer(ctx: commands.Context):
    if not db.isLadderPlayer(ctx.author):
        await ctx.send("You must participate in the 1v1 ladder to use this command. Sign up using .1v1signup!")
        return False
    else:
        return True

### BOT COMMANDS ###
@bot.command()
async def ping(ctx):
    
    if await bot.is_owner(ctx.author):
        await ctx.send('Owner')
    elif db.isLadderAdmin(ctx.author):
        await ctx.send('Admin')
    elif db.isLadderPlayer(ctx.author):
        await ctx.send('Player')
    else:
        await ctx.send('pong')

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

    # 5. Display success message
    await ctx.send("Welcome to the 1v1 ladder!")


# Used by users to challenge other users in the ladder
@bot.command()
async def challenge(ctx, opponent):
    # 1. Check if user has ladder role to use this command
    if not await isLadderPlayer(ctx):
        return

    # 2. Check if user can challenge other user:
    # 2a. Is user in timeout?
    # 2b. Is challenged user in universal timeout?
    # 2c. Is user already challenging someone?
    # 2d. Is user already being challenged?
    # 2e. Is opponent already challenging someone?
    # 2f. Is opponent already being challenged by someone?
    # 2g. Is the other player in a rank or tier that allows the challenge?
    # 3a. No: Display why and quit
    # 3b. Yes: Continue
    # 4. Add challenge to database
    # 5. Display success message
    await ctx.send('challenge')

# Used by users or admins to cancel challenges
@bot.command()
async def cancel(ctx, player = None):
    # 1. Check if user has either permission to run this command:
    # 1a. Ladder role if no player arugment is given
    # 1b. Admin role if player argument is given
    # 2. Check if user has a challenge to be cancelled
    # 3. Update the challenge to cancelled/denied state in the database
    # 4. Update number of cancellations for the player
    # 5. Kick the player if the number of cancellations exceeds the maximum permitted number
    # 6. Display success message, @ both users
    await ctx.send('cancel')

# Used by users or admins to report game results
@bot.command()
async def report(ctx, result, player = None):
    # 1. Check if user has either permission to run this command:
    # 1a. Ladder role if no player arugment is given
    # 1b. Admin role if player argument is given
    # 2. Check if user has a challenge that can be reported
    # 3. Check if result string is valid (either W(in) or L(oss))
    # 4. Update challenge in the database
    # 5. Update rankings in the database
    # 6. Timeout the challenging player from challenging for the configured time
    # 7. Edit ranking message
    # 8. Display success message: Maybe information if someone gets promoted to a new tier, who got timeout
    await ctx.send('report')

# Used by admins to cancel all overdue challenges
@bot.command()
async def clear(ctx):
    # 1. Check if user has the admin role
    # 2. Fetch all outstanding challenges from the database that are overdue
    # 3. Cancel all overdue challenges
    # 4. Display success message: @ users whose challenges got cancelled by this
    await ctx.send('clear')


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

    # 3. Remove target's ladder role
    ladderRole = discord.utils.get(ctx.guild.roles, id = int(db.getConfig('ladder_role')))
    kickReason = f"Kicked from the ladder by {ctx.author.name}"
    if not reason == '':
        kickReason += f". Reason: '{reason}'"
    await ctx.author.remove_roles(ladderRole, reason = kickReason)

    # 4. Remove player from database
    db.kickPlayer(player.id)

    # 5. Display success message
    kickMessage = f"{player.name} was kicked from the ladder."
    if not reason == '':
        kickMessage += f" Reason: '{reason}'"
    await ctx.send(kickMessage)
    await ctx.message.delete()


# Used by admins to time out users from the ladder
@bot.command()
async def timeout(ctx, player, duration):
    # TODO
    # 1. Check if user has admin role
    # 2. Check if target is part of the ladder
    # 3. Add timeout to the database for outgoing and incoming challenges
    # 4. Display success message
    await ctx.send('timeout')

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