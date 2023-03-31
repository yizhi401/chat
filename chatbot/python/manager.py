'''Robot manager module.'''

from chatbot import ChatBot
import os
import pathlib
import json
import multiprocessing
import redis
import utils

def run_robot(name, password, photos_root, host):
    os.environ["GRPC_SSL_CIPHER_SUITES"] = "HIGH+ECDSA"
    utils.config_logging()
    print("Starting robot: ", name, password, photos_root, host)
    chatBot = ChatBot(name,password,photos_root)
    chatBot.run(host)

def parse_json_str_to_dict(json_str: str)->dict:
    try:
        return json.loads(json_str)
    except Exception as e:
        return json_str



class RobotManager(object):
    '''Robot manager class.'''

    def __init__(self):
        self.host = "47.103.17.145:16060"
        self.all_robots = []
        self.query_robots()
        print(self.all_robots)
    
    def query_robots(self):
        with redis.Redis(
            host="47.103.17.145", port=8010, db=6, password="godword"
        ) as redis_db:
            for key in redis_db.keys():
                key_str = key.decode('utf-8')
                if key_str == 'INITIAL_ROBOTS':
                    continue
                if key_str != "assistant" and key_str != "wukong":
                    continue
                robot = parse_json_str_to_dict(redis_db.get(key).decode('utf-8'))
                if 'photos_root' not in robot:
                    robot['photos_root'] = ""
                self.all_robots.append({
                    'name': robot['name'],
                    'password': robot['password'],
                    'photos_root': pathlib.Path(robot['photos_root']),
                })

    def start(self):
        self.processors = []
        for robot in self.all_robots:
            processor = multiprocessing.Process(
                target=run_robot,
                args=(
                    robot['name'],
                    robot['password'],
                    robot['photos_root'],
                    self.host,
                ),
            )
            self.processors.append(processor)
            processor.start()
        # Wait for all process to finish
        for processor in self.processors:
            processor.join()


    def stop(self):
        pass


def main():
    manager = RobotManager()
    manager.start()

if __name__ == "__main__":
    main()