from typing import Any
# TODO DB module cannot use logging module.
# import logging
import redis


class Database:
    def __init__(self):
        print("Connecting to redis...")
        self.redis = redis.Redis(host='47.103.17.145',
                                 port=8010, db=8, password='godword')
        self.redis_ttl = redis.Redis(host='47.103.17.145',
                                     port=8010, db=7, password='godword')

    def check_user_validity(self, chatbot: str, from_user_id: str) -> bool:
        ttl_key = f"TTL:{chatbot}:{from_user_id}"
        print(ttl_key)
        return self.redis_ttl.get(ttl_key) != None

    def get_user_data(self, from_user_id: str) -> bool:
        pass

    def save_user_data(self, from_user_id: str, data: Any):
        pass


db = Database()
