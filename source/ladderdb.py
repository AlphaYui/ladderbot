import MySQLdb
import sys
import math

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

    # Returns if the user still has to cool down after issuing their last challenge
    def hasChallengeTimeout(self, discordID, ladder = ''):
        if ladder == '':
            ladder = self.getConfig('current_ladder')
        # TODO


##### CHALLENGES #####

    # Creates 'Challenges' table if it doesn't exist yet
    def __initChallengesTable(self):
        if not self.__doesTableExist('Challenges'):
            self.cursor.execute("""
            CREATE TABLE Challenges (
                ChallengeID INT AUTO_INCREMENT,
                Ladder varchar(255) NOT NULL,
                IssuedByID INT NOT NULL,
                OpponentID INT NOT NULL,
                Time DATETIME DEFAULT NOW(),
                State ENUM('pending', 'played', 'denied', 'cancelled', 'timeout') DEFAULT 'pending',
                Won BIT,
                PRIMARY KEY (ChallengeID)
            );""")

            print('Created table "Challenges".')



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
    