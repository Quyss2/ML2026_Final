import math
import pandas as pd
from collections import Counter
from connectors.connector import Connector

class CustomerDAO:
    @staticmethod
    def getAllCustomers():
        conn=Connector()
        conn.connect()
        sql="select * from customer"
        df=conn.queryDataset(sql)
        return df
    @staticmethod
    def getAllCustomerByAge(min,max):
        conn=Connector()
        conn.connect()
        sql="select * from customer where age>=%s and age<=%s"
        val=(min,max)
        df=conn.queryDataset(sql,val)
        return df
    @staticmethod
    def _vectorize(text, n=2):
        t = f" {str(text).strip().lower()} "
        return Counter(t[i:i + n] for i in range(len(t) - n + 1))

    @staticmethod
    def _cosine(a, b):
        dot = sum(v * b.get(k, 0) for k, v in a.items())
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return 0.0 if na == 0 or nb == 0 else dot / (na * nb)

    @staticmethod
    def searchByNameCosine(keywords, n):
        conn = Connector()
        conn.connect()
        try:
            df = conn.queryDataset("select Id, CustomerID, Name from customer")
        finally:
            conn.disconnect()
        if df is None or df.empty:
            return None

        q = CustomerDAO._vectorize(keywords)
        df["Cosine Similarity"] = [
            round(CustomerDAO._cosine(q, CustomerDAO._vectorize(name)), 4)
            for name in df["Name"]
        ]
        return (df.sort_values("Cosine Similarity", ascending=False)
                  .head(n)
                  .reset_index(drop=True))