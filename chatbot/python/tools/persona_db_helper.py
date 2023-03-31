import json
import yaml
import redis

def yaml_file_to_json_str(yaml_file_path: str)->str:
    with open(yaml_file_path, "r",encoding='utf-8') as f:
        yaml_content = yaml.safe_load(f)
    # print(yaml_content)
    for person in yaml_content:
        print(json.dumps(person, ensure_ascii=False))
    return ""

def dump_to_yaml_file(yaml_file_path: str, data: dict):
    with open(yaml_file_path, "w",encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True)


def get_all_keys_in_redis_db(db: int)->list:
    with redis.Redis(
        host="47.103.17.145", port=8010, db=6, password="godword"
    ) as redis_db:
        return redis_db.keys()

def parse_json_str_to_dict(json_str: str)->dict:
    try:
        return json.loads(json_str)
    except Exception as e:
        return json_str


def dump_redis_data():
    try:
        with redis.Redis(
            host="47.103.17.145", port=8010, db=6, password="godword"
        ) as redis_ttl:
            all_data = {}
            for key in redis_ttl.keys():
                all_data[key.decode('utf-8')] = parse_json_str_to_dict(redis_ttl.get(key).decode('utf-8'))
            return all_data
    except Exception as e:
        print(e)
        return None
 

def main():
    dump_to_yaml_file("persona.yaml", dump_redis_data())

if __name__ == "__main__":
    main()