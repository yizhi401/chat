import logging
import redis
import json


def get_user_validity(from_user_id: str):
    logging.debug("Checking user validity: %s", from_user_id)
    ttl_key = f"TTL:{from_user_id}"
    try:
        with redis.Redis(
            host="47.103.17.145", port=8010, db=7, password="godword"
        ) as redis_ttl:
            token_left = redis_ttl.get(ttl_key)
            if token_left == None:
                return [False, 0]
            time_left = redis_ttl.ttl(ttl_key)
            if time_left is None or time_left < 0:
                return [False, 0]
            tokens = json.loads(token_left.decode("utf-8"))
            # token string is like:
            # {"times": 10, "tokens": 20}
            if tokens["times"] <= 0 and tokens["tokens"] <= 0:
                return [False, 0]
            logging.debug("User %s has %s tokens left", from_user_id, tokens)
            return [True, tokens]
    except Exception as e:
        logging.error("Error in get_user_validity %s", e)
        return [False, 0]


def save_tokens_left(from_user_id: str, tokens_left):
    logging.debug("Decreasing tokens for user %s : %s",
                  from_user_id, tokens_left)
    ttl_key = f"TTL:{from_user_id}"
    try:
        with redis.Redis(
            host="47.103.17.145", port=8010, db=7, password="godword"
        ) as redis_ttl:
            json_str = json.dumps(tokens_left)
            ttl = redis_ttl.ttl(ttl_key)
            if ttl is None or ttl < 0:
                return
            redis_ttl.set(ttl_key, json_str)
            redis_ttl.expire(ttl_key, ttl)
    except Exception as e:
        logging.error("Error in save_tokens_left %s", e)


def get_user_data(from_user_id: str) -> str:
    try:
        with redis.Redis(
            host="47.103.17.145", port=8010, db=8, password="godword"
        ) as redis_con:
            json_data = redis_con.get(from_user_id)
            if json_data == None:
                return ""
            return json_data.decode("utf-8")
    except Exception as e:
        logging.error("Error in get_user_data %s", e)
        return ""


def save_user_data(from_user_id: str, json_data: str):
    logging.debug("Saving user data for %s: %s", from_user_id, json_data)
    try:
        with redis.Redis(
            host="47.103.17.145", port=8010, db=8, password="godword"
        ) as redis_con:
            redis_con.set(from_user_id, json_data)
    except Exception as e:
        logging.error("Error in save_user_data %s", e)
