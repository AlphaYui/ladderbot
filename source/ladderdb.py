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

        self.cursor.execute("INSERT INTO Players (DiscordID, Ladder, Tier, Rank) VALUES (%s, %s, %s, %s);", (discordID, ladder, newPlayerTier, newPlayerRank))
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

    # Return true if player 1 is allowed to challenge player 2 with their current ranking
    # This is the case if player 1 is either:
    # a) one tier below player 2
    # b) in the same tier as player 2, but has a lower rank
    def canChallenge(self, discordID1, discordID2, ladder = ''):
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



##### CHALLENGES #####

    # Creates 'Challenges' table if it doesn't exist yet
    def __initChallengesTable(self):
        if not self.__doesTableExist('Challenges'):
            self.cursor.execute("""
            CREATE TABLE Challenges (
                ChallengeID INT AUTO_INCREMENT,
                IssuedByID INT NOT NULL,
                OpponentID INT NOT NULL,
                Time DATETIME DEFAULT NOW(),
                State ENUM('pending', 'played', 'denied', 'cancelled', 'timeout') DEFAULT 'pending',
                Won BIT,
                PRIMARY KEY (ChallengeID)
            );""")

            print('Created table "Challenges".')

    # Returns true if the player is currently challenging at least one other player
    def isCurrentlyChallenging(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT COUNT(*) FROM Challenges LEFT JOIN Players ON Challenges.IssuedByID=Players.PlayerID WHERE DiscordID=%s AND Ladder=%s AND State='pending';", (discordID, ladder,))
        result = self.cursor.fetchall()

        outgoingChallengeCount = result[0][0]

        if outgoingChallengeCount is None or outgoingChallengeCount == 0:
            return False
        else:
            return True

    # Returns true if the player is currently being challenged by at least one other player
    def isCurrentlyBeingChallenged(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')

        self.cursor.execute("SELECT COUNT(*) FROM Challenges LEFT JOIN Players ON Challenges.OpponentID=Players.PlayerID WHERE DiscordID=%s AND Ladder=%s AND State='pending';", (discordID, ladder,))
        result = self.cursor.fetchall()

        incomingChallengeCount = result[0][0]

        if incomingChallengeCount is None or incomingChallengeCount == 0:
            return False
        else:
            return True

    

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
            ('num_cancels', 3)
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
    