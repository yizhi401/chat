import logging
import redis


class Database:
    def __init__(self):
        pass
        # logging.info("Connecting to redis...")
        # self.redis = redis.Redis(host="47.103.17.145",
        #                          port=8010, db=8, password="godword")
        # self.redis_ttl = redis.Redis(
        #     host="47.103.17.145", port=8010, db=7, password="godword"
        # )

    def get_user_validity(self, chatbot: str, from_user_id: str):
        logging.debug("Checking user validity: %s", from_user_id)
        ttl_key = f"TTL:{chatbot}:{from_user_id}"
        try:
            redis_ttl = redis.Redis(
                host="47.103.17.145", port=8010, db=7, password="godword"
            )
            token_left = redis_ttl.get(ttl_key)
            if token_left == None:
                return [False, 0]
            tokens = int(token_left.decode("utf-8"))
            logging.debug("User %s has %s tokens left", from_user_id, tokens)
            return [True, tokens]
        except Exception as e:
            logging.error("Error in get_user_validity %s", e)
            return [False, 0]

    def save_tokens_left(self, chatbot: str, from_user_id: str, tokens_left: int):
        logging.debug("Decreasing tokens for user %s : %s", from_user_id, tokens_left)
        ttl_key = f"TTL:{chatbot}:{from_user_id}"
        try:
            redis_ttl = redis.Redis(
                host="47.103.17.145", port=8010, db=7, password="godword"
            )
            redis_ttl.set(ttl_key, str(tokens_left))
        except Exception as e:
            logging.error("Error in save_tokens_left %s", e)

    def get_user_data(self, from_user_id: str) -> str:
        try:
            redis_con = redis.Redis(
                host="47.103.17.145", port=8010, db=8, password="godword"
            )
            json_data = redis_con.get(from_user_id)
            if json_data == None:
                return ""
            return json_data.decode("utf-8")
        except Exception as e:
            logging.error("Error in get_user_data %s", e)
            return ""

    def save_user_data(self, from_user_id: str, json_data: str):
        logging.debug("Saving user data for %s: %s", from_user_id, json_data)
        try:
            redis_con = redis.Redis(
                host="47.103.17.145", port=8010, db=8, password="godword"
            )
            redis_con.set(from_user_id, json_data)
        except Exception as e:
            logging.error("Error in save_user_data %s", e)
