from connectors.connector import Connector
from SaleDatabaseProject.models.user import User
class UserDAO:
    @staticmethod
    def login(uid,pwd):
        sql="select * from users where username=%s and password=%s"
        val=(uid,pwd)
        conn=Connector()
        conn.connect()
        df=conn.queryDataset(sql,val)
        if df is None:
            return None #login failed
        us=User()
        us.id=df["id"]
        us.username=df["username"]
        us.password=df["password"]
        us.is_banned=df["is_banned"]
        us.role=df["role"]
        return us
    