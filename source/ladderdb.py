import MySQLdb
import sys
import math
import datetime

class LadderDatabase:
    def __init__(self, credentialFile):
        # Reads MySQL credentials from token file
        try:
            mysqlCredentialFile = open(credentialFile, 'r')
            mysqlCredentials = [line.rstrip('\n') for line in mysqlCredentialFile]
            self.ip = mysqlCredentials[0]
            self.user = mysqlCredentials[1]
            self.password = mysqlCredentials[2]
            self.databaseName = mysqlCredentials[3]

            self.database = MySQLdb.connect(host = self.ip, user = self.user, passwd = self.password, db = self.databaseName)
            self.cursor = self.database.cursor()
        except:
            print('Failed to connect to MySQL database')
            raise

        # self.__dropAllTables()
        self.__initAllTables()
    
    # Executes the given query and returns all results.
    def __query(self, sqlCommand):
        self.cursor.execute(sqlCommand)
        return self.cursor.fetchall()

    # Checks if a table with the given name already exists in the database.
    def __doesTableExist(self, tableName):
        self.cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_name=%s LIMIT 1;", (self.databaseName, tableName,))
        result = self.cursor.fetchall()
        return result[0][0] > 0
    
    # Makes sure all necessary tables exist
    def __initAllTables(self):
        self.__initPlayersTable()
        self.__initChallengesTable()
        self.__initConfigTable()

    # Deletes all tables - for debugging only!
    def __dropAllTables(self):
        tableList = ['Players', 'Challenges', 'Config']

        for tableName in tableList:
            self.cursor.execute(f"DROP TABLE {tableName};")


##### PLAYERS ######

    # Creates 'Players' table if it doesn't exist yet
    def __initPlayersTable(self):
        if not self.__doesTableExist('Players'):
            self.cursor.execute("""
            CREATE TABLE Players (
                PlayerID INT AUTO_INCREMENT,
                DiscordID BIGINT NOT NULL,
                Ladder varchar(255) NOT NULL,
                Wins INT DEFAULT 0,
                Losses INT DEFAULT 0,
                Tier INT,
                Rank INT,
                Titles INT DEFAULT 0,
                Cancellations INT DEFAULT 0,
                OutgoingTimeoutUntil DATETIME,
                IngoingTimeoutUntil DATETIME,
                PRIMARY KEY (PlayerID)
            );""")

            print('Created table "Players".')

    # Adds new player signup
    def addPlayer(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        lowestRank = self.getLowestRank(ladder)
        newPlayerRank = lowestRank + 1
        newPlayerTier = self.convertToTier(newPlayerRank)

        self.cursor.execute("INSERT INTO Players (DiscordID, Ladder, Tier, Rank, OutgoingTimeoutUntil, IngoingTimeoutUntil) VALUES (%s, %s, %s, %s, NOW(), NOW());", 
        (discordID, ladder, newPlayerTier, newPlayerRank))
        self.database.commit()

    # Deletes player
    def kickPlayer(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        # Gets current rank of the kicked player
        self.cursor.execute("SELECT Rank FROM Players WHERE DiscordID=%s AND Ladder=%s;", (discordID, ladder,))
        result = self.cursor.fetchall()
        rank = result[0][0]

        if rank is not None and rank > 0:
            # Gets ID&rank of all players that are below the kicked player in the ladder
            self.cursor.execute("SELECT PlayerID, Rank FROM Players WHERE Rank>%s", (rank,))
            result = self.cursor.fetchall()

            for row in result:
                playerID = row[0]
                if playerID is None:
                    break

                # Moves the player up by one rank
                updatedRank = row[1] - 1
                updatedTier = self.convertToTier(updatedRank)
                self.cursor.execute("UPDATE Players SET Rank=%s, Tier=%s WHERE PlayerID=%s", (updatedRank, updatedTier, playerID,))

        # Removes the kicked player from the ladder
        self.cursor.execute("DELETE FROM Players WHERE DiscordID=%s AND Ladder=%s;", (discordID, ladder,))
        self.database.commit()

    def getPlayerByRank(self, rank, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT PlayerID, DiscordID, Tier, Wins, Losses, Titles FROM Players WHERE Rank=%s AND Ladder=%s;", (rank, ladder,))
        result = self.cursor.fetchall()

        if len(result) == 0 or result[0][0] is None:
            return None
        else:
            row = result[0]
            return PlayerInfo(row[0], row[1], rank, row[2], row[3], row[4], row[5])

    # Checks if player is signed up for the ladder
    def isPlayerSignedUp(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT COUNT(PlayerID) FROM Players WHERE DiscordID=%s AND Ladder=%s;", (discordID, ladder,))
        result = self.cursor.fetchall()
        return result[0][0] > 0

    # Calculates which tier a rank is
    def convertToTier(self, rank):
        return round(math.sqrt(2*rank - 1))

    # Gets the current lowest rank in the ladder
    def getLowestRank(self, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT MAX(Rank) FROM Players WHERE Ladder=%s;", (ladder,))
        result = self.cursor.fetchall()

        lowestRank = result[0][0]
        if lowestRank is None:
            return 0
        else:
            return lowestRank

    # Returns true if currently can't issue challenges due to being on timeout
    def hasChallengeTimeout(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT OutgoingTimeoutUntil FROM Players WHERE DiscordID=%s AND Ladder=%s;", (discordID, ladder,))
        result = self.cursor.fetchall()

        if result[0][0] is None:
            return False

        timeoutEnd = result[0][0]
        currentTime = datetime.datetime.now()

        return timeoutEnd > currentTime

    # Returns true if the user is currently protected from challenges
    def hasChallengeProtection(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT IngoingTimeoutUntil FROM Players WHERE DiscordID=%s AND Ladder=%s;", (discordID, ladder,))
        result = self.cursor.fetchall()

        if result[0][0] is None:
            return False

        timeoutEnd = result[0][0]
        currentTime = datetime.datetime.now()

        return timeoutEnd > currentTime

    # Returns if Player 1 is allowed to challenge Player 2
    def canChallenge(self, discordID1, discordID2, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        challengerInfo = self.getPlayerInfo(discordID1, ladder)
        opponentInfo = self.getPlayerInfo(discordID2, ladder)

        # The #1 player can only challenge tier 2
        if challengerInfo.rank == 1:
            return opponentInfo.tier == 2

        # Others can challenge all players below them
        if challengerInfo.rank < opponentInfo.rank:
            return True

        # You can't challenge players more than one tier above you
        if challengerInfo.tier > opponentInfo.tier + 1:
            return False

        # You can't challenge player more than 3 ranks above you
        if challengerInfo.rank > opponentInfo.rank + 3:
            return False

        # In all other cases, you can challenge!
        return True

    # Returns a list of all higher ranked players that a player could challenge
    def getPossibleChallenges(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        challenges = []
        playerInfo = self.getPlayerInfo(discordID)
        result = {}

        # Gets all possible challengers based on rank and tier
        if playerInfo.rank == 1:
            self.cursor.execute("SELECT DiscordID FROM Players WHERE Ladder=%s AND Tier=2 AND IngoingTimeoutUntil<NOW();", (ladder,))
            result = self.cursor.fetchall()
        else:
            self.cursor.execute("SELECT DiscordID FROM Players WHERE Ladder=%s AND NOT DiscordID=%s AND Rank<%s AND Rank>%s AND Tier>%s AND IngoingTimeoutUntil<NOW();",
            (ladder, discordID, playerInfo.rank, playerInfo.rank - 4, playerInfo.tier - 2))
            result = self.cursor.fetchall()

        if len(result) == 0 or result[0][0] is None:
            return []

        # Filters out all challengers that are already in a match
        for row in result:
            playerDiscordID = row[0]
            activeChallenge = self.getActiveChallenge(playerDiscordID, ladder)

            if activeChallenge is None:
                challenges += [playerDiscordID]
        
        return challenges


    # Deprecated
    # Return true if player 1 is allowed to challenge player 2 with their current ranking
    # This is the case if player 1 is either:
    # a) one tier below player 2
    # b) in the same tier as player 2, but has a lower rank
    def canChallengeOld(self, discordID1, discordID2, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT Rank, Tier FROM Players WHERE DiscordID=%s AND Ladder=%s;", (discordID1, ladder,))
        result = self.cursor.fetchall()
        rank1 = result[0][0]
        tier1 = result[0][1]

        self.cursor.execute("SELECT Rank, Tier FROM Players WHERE DiscordID=%s AND Ladder=%s;", (discordID2, ladder,))
        result = self.cursor.fetchall()
        rank2 = result[0][0]
        tier2 = result[0][1]

        if rank1 is None or tier1 is None or rank2 is None or tier2 is None:
            return False

        if tier1 == tier2:
            return rank1 > rank2
        else:
            return tier1 == tier2 + 1

    # Gets if a user has timeouts and if so, which
    def getTimeoutInfo(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT OutgoingTimeoutUntil, IngoingTimeoutUntil FROM Players WHERE DiscordID=%s AND Ladder=%s;", (discordID, ladder,))
        result = self.cursor.fetchall()

        if len(result) == 0:
            return None
        else:
            outgoingTimeout = result[0][0]
            incomingTimeout = result[0][1]
            currentTime = datetime.datetime.now()

            if outgoingTimeout is not None and outgoingTimeout < currentTime:
                outgoingTimeout = None
            if incomingTimeout is not None and incomingTimeout < currentTime:
                incomingTimeout = None

            return TimeoutInfo(outgoingTimeout, incomingTimeout)

    # Increments the number of cancellations a player used
    def updateCancelCounter(self, discordID, change: int, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT Cancellations, PlayerID FROM Players WHERE DiscordID=%s AND Ladder=%s;", (discordID, ladder,))
        result = self.cursor.fetchall()

        if len(result) == 0 or result[0][0] is None:
            return 0
        
        cancellations = result[0][0] + change

        if cancellations < 0:
            cancellations = 0

        if not change == 0:
            playerID = result[0][1]

            self.cursor.execute("""UPDATE Players SET Cancellations=%s WHERE PlayerID=%s;""", (cancellations, playerID,))
            self.database.commit()

        return cancellations

    # Returns rank and signup information of the player with the given discord id
    def getPlayerInfo(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT PlayerID, Rank, Tier, Wins, Losses, Titles FROM Players WHERE DiscordID=%s AND Ladder=%s;", (discordID, ladder,))
        result = self.cursor.fetchall()

        if len(result) == 0 or result[0][0] is None:
            return None
        else:
            row = result[0]
            return PlayerInfo(row[0], discordID, row[1], row[2], row[3], row[4], row[5])

    # Prohibits the given player from issueing challenges for the given number of days
    def giveChallengeCooldown(self, discordID, days, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("UPDATE Players SET OutgoingTimeoutUntil=(NOW() + INTERVAL %s DAY) WHERE DiscordID=%s AND Ladder=%s;", (days, discordID, ladder,))
        self.database.commit()

    # Protects the given player from being challenged for the given number of days
    def giveChallengeProtection(self, discordID, days, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("UPDATE Players SET IngoingTimeoutUntil=(NOW() + INTERVAL %s DAY) WHERE DiscordID=%s AND Ladder=%s;", (days, discordID, ladder,))
        self.database.commit()

    def getRanking(self, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT PlayerID, DiscordID, Rank, Tier, Wins, Losses, Titles FROM Players WHERE Ladder=%s ORDER BY Rank LIMIT 100;", (ladder,))
        result = self.cursor.fetchall()

        players = []

        for row in result:
            players += [PlayerInfo(row[0], row[1], row[2], row[3], row[4], row[5], row[6])]
        
        return players

    # Randomly shuffles all ladder participants so that ranks are random
    def shuffleLadder(self, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        # Gets a randomized list of all players
        self.cursor.execute("SELECT PlayerID FROM Players WHERE Ladder=%s ORDER BY RAND();", (ladder,))
        result = self.cursor.fetchall()

        # Assigns new rank to every player
        rank = 1
        tier = 1
        for row in result:
            if row[0] is None:
                break
            
            playerID = row[0]
            tier = self.convertToTier(rank)
            self.cursor.execute("UPDATE Players SET Rank=%s, Tier=%s WHERE PlayerID=%s;", (rank, tier, playerID,))

            rank += 1

        self.database.commit()


##### CHALLENGES #####

    # Creates 'Challenges' table if it doesn't exist yet
    # ChallengeID: Primary Key
    # IssuedByID: Players.PlayerID of Player who challenged the other
    # OpponentID: Players.PlayerID of Player who got challenged
    # Time: Deadline by which the game has to be played
    # State: Whether the game is pending, already played, denied, cancelled or was timed out
    # Won: Whether the game was won by the challenger (False -> Won by Opponent, Null -> Not played)
    def __initChallengesTable(self):
        if not self.__doesTableExist('Challenges'):
            self.cursor.execute("""
            CREATE TABLE Challenges (
                ChallengeID INT AUTO_INCREMENT,
                IssuedByID INT NOT NULL,
                OpponentID INT NOT NULL,
                Time DATETIME DEFAULT NOW(),
                State ENUM('pending', 'played', 'denied', 'cancelled', 'timeout') DEFAULT 'pending',
                Won TINYINT,
                PRIMARY KEY (ChallengeID)
            );""")

            print('Created table "Challenges".')

    def addChallenge(self, issuedByDiscordID, opponentDiscordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        challengeTimeout = self.getConfig('challenge_timeout')

        self.cursor.execute("""INSERT INTO Challenges (IssuedByID, OpponentID, Time) VALUES 
        ((SELECT PlayerID FROM Players WHERE DiscordID=%s AND Ladder=%s),
        (SELECT PlayerID FROM Players WHERE DiscordID=%s AND LADDER=%s),
        (NOW() + INTERVAL %s DAY));""",
        (issuedByDiscordID, ladder, opponentDiscordID, ladder, challengeTimeout,))

        self.database.commit()

    # Returns the Discord ID of the member the player with the given Discord ID played against last
    def getLastPlayedChallenge(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        # Gets the Discord ID of the player who was challenged last
        self.cursor.execute("""SELECT c.ChallengeID, p1.DiscordID, p2.DiscordID, c.Time, c.Won FROM Challenges c 
        JOIN Players p1 ON c.IssuedByID=p1.PlayerID 
        JOIN Players p2 ON c.OpponentID=p2.PlayerID 
        WHERE (p1.DiscordID=%s OR p2.DiscordID=%s) AND p1.Ladder=%s AND p2.Ladder=%s AND c.State='played' 
        ORDER BY c.Time DESC 
        LIMIT 1;""",  (discordID, discordID, ladder, ladder,))
        result = self.cursor.fetchall()

        if len(result) == 0 or result[0][0] is None or result[0][1] is None:
            return None
        else:
            row = result[0]
            return ChallengeInfo(row[0], row[1], row[2], row[3], row[4])

    # Return information about the currently active challenge of the given player
    def getActiveChallenge(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("""SELECT c.ChallengeID, p1.DiscordID, p2.DiscordID, c.Time FROM Challenges c
        JOIN Players p1 ON c.IssuedByID=p1.PlayerID 
        JOIN Players p2 ON c.OpponentID=p2.PlayerID 
        WHERE (p1.DiscordID=%s OR p2.DiscordID=%s) AND p1.Ladder=%s AND p2.Ladder=%s AND c.State='pending'
        ORDER BY c.Time DESC
        LIMIT 1;""", (discordID, discordID, ladder, ladder,))
        result = self.cursor.fetchall()

        if len(result) == 0 or result[0][0] is None:
            return None
        else:
            return ChallengeInfo(
                result[0][0],
                result[0][1],
                result[0][2],
                result[0][3]
            )

    # Cancels the current active challenge of the given player
    def cancelActiveChallenge(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("""SELECT c.ChallengeID, p1.DiscordID, p2.DiscordID FROM Challenges c
        JOIN Players p1 ON c.IssuedByID=p1.PlayerID 
        JOIN Players p2 ON c.OpponentID=p2.PlayerID 
        WHERE (p1.DiscordID=%s OR p2.DiscordID=%s) AND p1.Ladder=%s AND p2.Ladder=%s AND c.State='pending'
        ORDER BY c.Time DESC
        LIMIT 1;""", (discordID, discordID, ladder, ladder,))
        result = self.cursor.fetchall()
        
        if len(result) == 0 or result[0][0] is None:
            return
        else:
            challengeID = result[0][0]
            discordID1 = result[0][1]
            discordID2 = result[0][2]

            if discordID1 == discordID:
                self.cursor.execute("UPDATE Challenges SET State='cancelled' WHERE ChallengeID=%s;", (challengeID,))
            else:
                self.cursor.execute("UPDATE Challenges SET State='denied' WHERE ChallengeID=%s;", (challengeID,))

            self.database.commit()

    # Updates the database record of a challenge with the result and both players' rank, tier, wins and losses
    def reportResult(self, challengeInfo, won, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')
        
        # Updates entry for the challenge in the database
        wonNum = 0
        if won:
            wonNum = 1
        self.cursor.execute("UPDATE Challenges SET State='played', Won=%s WHERE ChallengeID=%s;", (wonNum, challengeInfo.challengeID,))

        challengerInfo = self.getPlayerInfo(challengeInfo.challenger)
        opponentInfo = self.getPlayerInfo(challengeInfo.opponent)

        # Updates Win/Loss/Titles and switches rank&tier if the winner is lower ranked
        if won:
            challengerInfo.wins += 1
            opponentInfo.losses += 1

            if challengerInfo.rank > opponentInfo.rank:
                newRank = opponentInfo.rank
                newTier = opponentInfo.tier

                opponentInfo.rank = challengerInfo.rank
                opponentInfo.tier = challengerInfo.tier

                challengerInfo.rank = newRank
                challengerInfo.tier = newTier

            if challengerInfo.rank == 1:
                challengerInfo.titles += 1
        else:
            challengerInfo.losses += 1
            opponentInfo.wins += 1
                
            if opponentInfo.rank > challengerInfo.rank:
                newRank = opponentInfo.rank
                newTier = opponentInfo.tier

                opponentInfo.rank = challengerInfo.rank
                opponentInfo.tier = challengerInfo.tier

                challengerInfo.rank = newRank
                challengerInfo.tier = newTier

            if opponentInfo.rank == 1:
                opponentInfo.titles += 1

        # Pushes changes to database
        self.cursor.execute("UPDATE Players SET Rank=%s, Tier=%s, Wins=%s, Losses=%s, Titles=%s WHERE PlayerID=%s;", 
        (challengerInfo.rank, challengerInfo.tier, challengerInfo.wins, challengerInfo.losses, challengerInfo.titles, challengerInfo.playerID,))

        self.cursor.execute("UPDATE Players SET Rank=%s, Tier=%s, Wins=%s, Losses=%s, Titles=%s WHERE PlayerID=%s;", 
        (opponentInfo.rank, opponentInfo.tier, opponentInfo.wins, opponentInfo.losses, opponentInfo.titles, opponentInfo.playerID,))

        self.database.commit()


    # Undos the latest result report for the given player
    def reverseReport(self, discordID, challengeInfo, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        # Updates entry for the challenge in the database
        self.cursor.execute("UPDATE Challenges SET State='pending', Won=NULL WHERE ChallengeID=%s;", (challengeInfo.challengeID,))

        challengerInfo = self.getPlayerInfo(challengeInfo.challenger)
        opponentInfo = self.getPlayerInfo(challengeInfo.opponent)

        # Reverses changes to the win/loss/titles and switches the rank/tiers
        if challengeInfo.won is not None:
            if challengeInfo.won == 1:
                challengerInfo.wins -= 1
                opponentInfo.losses -= 1

                if challengerInfo.rank == 1:
                    challengerInfo.titles -= 1
            else:
                challengerInfo.losses -= 1
                opponentInfo.wins -= 1

                if opponentInfo.rank == 1:
                    opponentInfo.titles -= 1

            newRank = opponentInfo.rank
            newTier = opponentInfo.tier

            opponentInfo.rank = challengerInfo.rank
            opponentInfo.tier = challengerInfo.tier

            challengerInfo.rank = newRank
            challengerInfo.tier = newTier
                
            # Pushes changes to database
            self.cursor.execute("UPDATE Players SET Rank=%s, Tier=%s, Wins=%s, Losses=%s, Titles=%s WHERE PlayerID=%s;", 
            (challengerInfo.rank, challengerInfo.tier, challengerInfo.wins, challengerInfo.losses, challengerInfo.titles, challengerInfo.playerID,))

            self.cursor.execute("UPDATE Players SET Rank=%s, Tier=%s, Wins=%s, Losses=%s, Titles=%s WHERE PlayerID=%s;", 
            (opponentInfo.rank, opponentInfo.tier, opponentInfo.wins, opponentInfo.losses, opponentInfo.titles, opponentInfo.playerID,))

        self.database.commit()

    
    # Marks all overdue challenges as timed out
    def cancelAllOverdueChallenges(self, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')
        
        # Gets all overdue challenges
        self.cursor.execute("""SELECT c.ChallengeID, p1.DiscordID, p2.DiscordID FROM Challenges c
        JOIN Players p1 ON c.IssuedByID=p1.PlayerID 
        JOIN Players p2 ON c.OpponentID=p2.PlayerID
        WHERE (c.Time < NOW()) AND c.State='pending';""")
        overdueChallenges = self.cursor.fetchall()

        affectedPlayers = []

        for overdueChallenge in overdueChallenges:
            challengeID = overdueChallenge[0]
            challengerID = overdueChallenge[1]
            opponentID = overdueChallenge[2]

            self.cursor.execute("UPDATE Challenges SET State='timeout' WHERE ChallengeID=%s", (challengeID,))

            challengerCancels = self.updateCancelCounter(challengerID, 1, ladder)
            opponentCancels = self.updateCancelCounter(opponentID, 1, ladder)

            affectedPlayers += [CancelInfo(challengerID, challengerCancels, opponentID, opponentCancels)]
        
        return affectedPlayers


##### CONFIGURATION #####

    # Creates 'Config' table if it doesn't exist yet
    def __initConfigTable(self):
        if not self.__doesTableExist('Config'):
            self.cursor.execute("""
            CREATE TABLE Config (
                ConfigID INT AUTO_INCREMENT,
                Ladder varchar(255),
                Name varchar(255) NOT NULL,
                Value varchar(255) NOT NULL,
                PRIMARY KEY (ConfigID)
            );""")

            self.cursor.execute("""INSERT INTO Config (Name, Value) VALUES 
            ('ranking_channel', 0),
            ('general_channel', 0),
            ('ladder_role', 0),
            ('admin_role', 0),
            ('challenge_timeout', 3),
            ('current_ladder', 'default'),
            ('num_cancels', 3),
            ('outgoing_cooldown', 1),
            ('challenge_protection', 1),
            ('ranking_message', 0),
            ('signup_only', 0)
            ;""")
            self.database.commit()

            print('Created table "Config".')

    # Gets the value of a configuration attribute by name
    def getConfig(self, name, ladder = ''):
        if ladder == '':
            self.cursor.execute("SELECT Value FROM Config WHERE Name=%s LIMIT 1;", (name,))
        else:
            self.cursor.execute("SELECT Value FROM Config WHERE Name=%s AND Ladder=%s LIMIT 1;", (name, ladder,))

        result = self.cursor.fetchall()
        if len(result) == 0:
            raise Exception(f"Invalid configuration name '{name}' for ladder '{ladder}'")
        else:
            return result[0][0]

    # Sets the value of a configuration attribute by name
    def setConfig(self, name, value, ladder = ''):
        if ladder == '':
            self.cursor.execute("UPDATE Config SET Value=%s WHERE Name=%s;", (value, name,))
        else:
            self.cursor.execute("UPDATE Config SET Value=%s WHERE Name=%s AND Ladder=%s;", (value, name, ladder,))

        self.database.commit()

    # Checks if a user is a ladder admin
    def isLadderAdmin(self, member):
        adminRoleID = int(self.getConfig('admin_role'))
        for role in member.roles:
            if role.id == adminRoleID:
                return True
        
        return False

    def isLadderPlayer(self, member):
        playerRoleID = int(self.getConfig('ladder_role'))
        for role in member.roles:
            if role.id == playerRoleID:
                return True

        return False

    def isGeneralChannel(self, channel):
        channelID = int(self.getConfig('general_channel'))
        return channelID == channel.id
    


class ChallengeInfo:
    def __init__(self, challengeID, challengerDiscordID, opponentDiscordID, deadline: datetime.datetime, won = None):
        self.challengeID = challengeID
        self.challenger = challengerDiscordID
        self.opponent = opponentDiscordID
        self.deadline = deadline
        self.won = won

class TimeoutInfo:
    def __init__(self, challengeTimeoutDeadline, protectionDeadline):
        self.outgoingTimeout = challengeTimeoutDeadline
        self.incomingTimeout = protectionDeadline

class PlayerInfo:
    def __init__(self, playerID, discordID, rank, tier, wins, losses, titles):
        self.playerID = playerID
        self.discordID = discordID
        self.rank = rank
        self.tier = tier
        self.wins = wins
        self.losses = losses
        self.titles = titles

class CancelInfo:
    def __init__(self, challenger, challengerCancels, opponent, opponentCancels):
        self.challenger = challenger
        self.challengerCancels = challengerCancels
        self.opponent = opponent
        self.opponentCancels = opponentCancels
