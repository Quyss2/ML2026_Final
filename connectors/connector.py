import mysql.connector
import pandas as pd


class Connector:
    def __init__(self,
                 server="localhost",
                 port=3306,
                 database="final_ml_2026",
                 username="root",
                 password="123"):
        self.server=server
        self.port=port
        self.database=database
        self.username=username
        self.password=password
    def connect(self):
        self.conn = mysql.connector.connect(
            host=self.server,
            port=self.port,
            database=self.database,
            user=self.username,
            password=self.password,
            use_pure=True)
    def queryDataset(self,sql,val=None):
        try:
            cursor=self.conn.cursor()
            cursor.execute(sql,val)
            df=pd.DataFrame(cursor.fetchall())
            df.columns=cursor.column_names
            return df
        except Exception as e:
            print(str(e))
            return None

    def execute(self,sql,val=None):
        try:
            cursor=self.conn.cursor()
            cursor.execute(sql,val)
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            self.conn.rollback()
            print(str(e))
            return None
        finally:
            if "cursor" in locals():
                cursor.close()