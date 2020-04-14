import MySQLdb
import sys

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
    
    # Executes the given query and returns all results.
    def query(self, sqlCommand):
        self.cursor.execute(sqlCommand)
        return self.cursor.fetchall()
        