class Data:
    def __init__(
        self,
        id=None,
        event_time=None,
        event_type=None,
        product_id=None,
        category_id=None,
        category_code=None,
        brand=None,
        price=None,
        user_id=None,
        user_session=None
    ):
        self.id = id
        self.event_time = event_time
        self.event_type = event_type
        self.product_id = product_id
        self.category_id = category_id
        self.category_code = category_code
        self.brand = brand
        self.price = price
        self.user_id = user_id
        self.user_session = user_session