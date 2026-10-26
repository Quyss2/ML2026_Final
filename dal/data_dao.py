from connectors.connector import Connector
from models.data import Data
class DataDAO:
    @staticmethod
    def show_all_data():
        sql = "select * from data"
        conn = Connector()
        conn.connect()
        df = conn.queryDataset(sql)
        if df is None:
            return None
        data_list = []
        for index, row in df.iterrows():
            data = Data(
                id=row["id"],
                event_time=row["event_time"],
                event_type=row["event_type"],
                product_id=row["product_id"],
                category_id=row["category_id"],
                category_code=row["category_code"],
                brand=row["brand"],
                price=row["price"],
                user_id=row["user_id"],
                user_session=row["user_session"]
            )
            data_list.append(data)
        return data_list