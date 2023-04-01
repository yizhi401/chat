import logging
import redis
import json
import datetime


def get_time_left_of_today() -> int:
    # 返回今天剩余的秒数
    now = datetime.datetime.now()
    tomorrow = now + datetime.timedelta(days=1)
    tomorrow = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    return (tomorrow - now).seconds


def get_user_validity(from_user_id: str):
    # 当前用户的有效性原则：
    # 1. 付费用户
    #    -- 在redis中存在key，且type为vip
    #    -- 付费用户的不计TOKEN和TIMES
    # 2. 免费用户
    #    -- 每天30次聊天+300000 TOKEN余量，未用完清零
    logging.debug("Checking user validity: %s", from_user_id)
    ttl_key = f"TTL:{from_user_id}"
    try:
        with redis.Redis(
            host="47.103.17.145", port=8010, db=7, password="godword"
        ) as redis_ttl:
            token_left = redis_ttl.get(ttl_key)
            if token_left == None:
                # 免费用户，KEY不存在，初始化30次
                free_tokens = {
                    "times": 30,
                    "tokens": 30000,
                    "type": "free",
                }
                redis_ttl.set(ttl_key, json.dumps(free_tokens))
                redis_ttl.expire(ttl_key, get_time_left_of_today())
                return [True, free_tokens]

            tokens = json.loads(token_left.decode("utf-8"))
            # token string is like:
            # {"times": 10, "tokens": 20, "type": "free"}
            tokens["ttl"] = redis_ttl.ttl(ttl_key)
            if tokens["times"] <= 0 and tokens["tokens"] <= 0:
                return [False, 0]
            logging.debug("User %s has %s tokens left", from_user_id, tokens)
            return [True, tokens]
    except Exception as e:
        logging.error("Error in get_user_validity %s", e)
        return [False, 0]


def save_tokens_left(from_user_id: str, tokens_left):
    logging.debug("Decreasing tokens for user %s : %s", from_user_id, tokens_left)
    ttl_key = f"TTL:{from_user_id}"
    try:
        with redis.Redis(
            host="47.103.17.145", port=8010, db=7, password="godword"
        ) as redis_ttl:
            # VIP用户不计算TOKEN和TIMES，也不会过期
            if tokens_left["type"] == "vip":
                tokens_left["times"] = 999999999
                tokens_left["tokens"] = 999999999
            # delete ttl key
            tokens_left.pop("ttl")
            json_str = json.dumps(tokens_left)
            ttl = redis_ttl.ttl(ttl_key)
            redis_ttl.set(ttl_key, json_str)
            if ttl > 0:
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
