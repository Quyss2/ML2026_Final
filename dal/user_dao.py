from connectors.connector import Connector
from models.user import User
class UserDAO:
    @staticmethod
    def login(uid, pwd):
        sql = "select * from account where username=%s and password=%s"
        val = (uid, pwd)
        conn = Connector()
        conn.connect()
        df = conn.queryDataset(sql, val)
        if df is None:
            return None  # login failed
        us = User()
        us.id = df["id"]
        us.username = df["username"]
        us.password = df["password"]
        us.is_banned = df["is_banned"]
        us.role = df["role"]
        return us
    @staticmethod
    def register(uid, pwd):
        sql = "insert into account(username,password) values(%s,%s)"
        val = (uid, pwd)
        conn = Connector()
        conn.connect()
        result = conn.execute(sql, val)
        if result is None:
            return None  # register failed
        us = User()
        us.id = result
        us.username = uid
        us.password = pwd
        return us