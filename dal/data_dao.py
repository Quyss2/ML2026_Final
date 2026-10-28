from connectors.connector import Connector
from models.data import Data


class DataDAO:
    COLUMNS = (
        "id",
        "event_time",
        "event_type",
        "product_id",
        "category_id",
        "category_code",
        "brand",
        "price",
        "user_id",
        "user_session",
    )
    EDITABLE_COLUMNS = COLUMNS[1:]
    FILTER_COLUMNS = ("event_type", "brand", "category_code")

    @staticmethod
    def show_all_data():
        sql = "select * from data"
        conn = Connector()
        conn.connect()
        df = conn.queryDataset(sql)
        if df is None:
            return None
        return [
            Data(**{column: row[column] for column in DataDAO.COLUMNS})
            for _, row in df.iterrows()
        ]

    @staticmethod
    def get_distinct_values(column):
        if column not in DataDAO.COLUMNS:
            raise ValueError(f"Unsupported data column: {column}")

        conn = Connector()
        conn.connect()
        df = conn.queryDataset(
            f"SELECT DISTINCT `{column}` FROM data "
            f"WHERE `{column}` IS NOT NULL ORDER BY `{column}`"
        )
        if df is None:
            return None
        return df[column].tolist()

    @staticmethod
    def _build_where(filters, include_price=True, include_time=True):
        conditions = []
        params = []

        for column in DataDAO.FILTER_COLUMNS:
            value = filters.get(column)
            if value is not None:
                conditions.append(f"`{column}` = %s")
                params.append(value)

        if include_time:
            event_time_from = filters.get("event_time_from")
            event_time_to = filters.get("event_time_to")
            if event_time_from is not None:
                conditions.append("`event_time` >= %s")
                params.append(event_time_from)
            if event_time_to is not None:
                conditions.append("`event_time` <= %s")
                params.append(event_time_to)

        if include_price:
            price_from = filters.get("price_from")
            price_to = filters.get("price_to")
            if price_from is not None:
                conditions.append("`price` >= %s")
                params.append(price_from)
            if price_to is not None:
                conditions.append("`price` <= %s")
                params.append(price_to)

        search_text = filters.get("search_text", "").strip()
        search_column = filters.get("search_column")
        if search_text:
            pattern = f"%{search_text}%"
            if search_column in (None, "all"):
                conditions.append(
                    "("
                    + " OR ".join(
                        f"CAST(`{column}` AS CHAR) LIKE %s"
                        for column in DataDAO.COLUMNS
                    )
                    + ")"
                )
                params.extend([pattern] * len(DataDAO.COLUMNS))
            else:
                if search_column not in DataDAO.COLUMNS:
                    raise ValueError(f"Unsupported search column: {search_column}")
                conditions.append(f"CAST(`{search_column}` AS CHAR) LIKE %s")
                params.append(pattern)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        return where_clause, params

    @staticmethod
    def _query_data(sql, params=None):
        conn = Connector()
        conn.connect()
        df = conn.queryDataset(sql, params)
        if df is None:
            return None
        return [
            Data(**{column: row[column] for column in DataDAO.COLUMNS})
            for _, row in df.iterrows()
        ]

    @staticmethod
    def filter_data(filters):
        where_clause, params = DataDAO._build_where(filters)
        return DataDAO._query_data(f"SELECT * FROM data{where_clause}", params)

    @staticmethod
    def insert_data(values):
        unknown_columns = set(values) - set(DataDAO.EDITABLE_COLUMNS)
        if unknown_columns:
            raise ValueError(f"Unsupported data columns: {', '.join(unknown_columns)}")

        columns = [column for column in DataDAO.EDITABLE_COLUMNS if column in values]
        if not columns:
            raise ValueError("At least one data field is required")

        sql_columns = ", ".join(f"`{column}`" for column in columns)
        placeholders = ", ".join("%s" for _ in columns)
        sql = f"INSERT INTO data ({sql_columns}) VALUES ({placeholders})"
        conn = Connector()
        conn.connect()
        return conn.execute(sql, [values[column] for column in columns])

    @staticmethod
    def update_data(record_id, values):
        unknown_columns = set(values) - set(DataDAO.EDITABLE_COLUMNS)
        if unknown_columns:
            raise ValueError(f"Unsupported data columns: {', '.join(unknown_columns)}")

        columns = [column for column in DataDAO.EDITABLE_COLUMNS if column in values]
        if not columns:
            raise ValueError("At least one data field is required")

        assignments = ", ".join(f"`{column}` = %s" for column in columns)
        sql = f"UPDATE data SET {assignments} WHERE `id` = %s"
        params = [values[column] for column in columns]
        params.append(record_id)
        conn = Connector()
        conn.connect()
        return conn.execute(sql, params) is not None

    @staticmethod
    def delete_data(record_ids):
        ids = list(dict.fromkeys(record_ids))
        if not ids:
            raise ValueError("At least one record ID is required")

        placeholders = ", ".join("%s" for _ in ids)
        sql = f"DELETE FROM data WHERE `id` IN ({placeholders})"
        conn = Connector()
        conn.connect()
        return conn.execute(sql, ids) is not None

    @staticmethod
    def get_price_range(filters=None):
        where_clause, params = DataDAO._build_where(filters or {}, include_price=False)
        conn = Connector()
        conn.connect()
        df = conn.queryDataset(
            f"SELECT MIN(`price`) AS min_price, MAX(`price`) AS max_price "
            f"FROM data{where_clause}",
            params,
        )
        if df is None:
            return None
        return df.iloc[0]["min_price"], df.iloc[0]["max_price"]

    @staticmethod
    def get_filter_ranges(filters=None):
        where_clause, params = DataDAO._build_where(
            filters or {},
            include_price=False,
            include_time=False,
        )
        conn = Connector()
        conn.connect()
        df = conn.queryDataset(
            "SELECT MIN(`event_time`) AS min_event_time, "
            "MAX(`event_time`) AS max_event_time, "
            "MIN(`price`) AS min_price, MAX(`price`) AS max_price "
            f"FROM data{where_clause}",
            params,
        )
        if df is None:
            return None
        row = df.iloc[0]
        return {
            "min_event_time": row["min_event_time"],
            "max_event_time": row["max_event_time"],
            "min_price": row["min_price"],
            "max_price": row["max_price"],
        }
