"""Define persona class for chatbot."""
import requests
import logging
import redis
import random
import db
import time
import json
import base64
import openai
import pathlib
from abc import ABC, abstractmethod
from typing import Any
import cmd_proc
from PIL import Image
import os
from io import BytesIO as memory_io
from enum import Enum

# Import generated grpc modules
from tinode_grpc import pb
from tinode_grpc import pbx
import utils
import common


def inline_image(filename: pathlib.Path):
    # Create drafty representation of a message with an inline image.
    try:
        im = Image.open(filename, "r")
        width = im.width
        height = im.height
        format = im.format if im.format else "JPEG"
        if width > common.MAX_IMAGE_DIM or height > common.MAX_IMAGE_DIM:
            # Scale the image
            scale = min(
                min(width, common.MAX_IMAGE_DIM) / width,
                min(height, common.MAX_IMAGE_DIM) / height,
            )
            width = int(width * scale)
            height = int(height * scale)
            resized = im.resize((width, height))
            im.close()
            im = resized

        mimetype = "image/" + format.lower()
        bitbuffer = memory_io()
        im.save(bitbuffer, format=format)
        data = base64.b64encode(bitbuffer.getvalue())

        # python3 fix.
        if type(data) is not str:
            data = data.decode()

        result = {
            "txt": " ",
            "fmt": [{"len": 1}],
            "ent": [
                {
                    "tp": "IM",
                    "data": {
                        "val": data,
                        "mime": mimetype,
                        "width": width,
                        "height": height,
                        "name": filename.name,
                    },
                }
            ],
        }
        im.close()
        return result
    except IOError as err:
        logging.error("Failed processing image '" + filename + "':", err)
        return None


class Persona(ABC):
    """Abstract class for a persona. Persona is used for each topic.
    Cannot share data between topics.
    """

    def __init__(
        self,
        bot_name: str,
        from_user_id: str,
        topic: str,
        photos: pathlib.Path,
        initial_data,
        tokens_left,
    ) -> None:
        self.bot_name = bot_name
        self.from_user_id = from_user_id
        self.topic = topic
        self.photos_root = photos
        # The following data needs to be save locally.
        self.photo_pool = {}
        self.feeling = 0
        self.tid = 100
        self.last_cmd = ""
        self.tokens_used = {
            "timeCount":0,
            "tokenCount":0,
        }
        self.initial_data = initial_data
        self.tokens_left = tokens_left
        # Format of history and persona_preset:
        # {chatmode: history/persona_preset}
        self.history = []
        self.persona_preset = []
        # End of data to be saved locally.

        openai.api_key = utils.read_from_file("openai.key").strip()
        logging.info("OpenAI API key: %s", openai.api_key)
        self.prepare_persona()
        self.local_data_folder = pathlib.Path("runtime")
        self.local_data_folder.mkdir(parents=True, exist_ok=True)
        # First need to load from local file if exists.
        self._load_data_from_local()

    def prepare_persona(self) -> None:
        self.persona_preset = self.initial_data['preset']
        self.story = self.initial_data['story']
        self.user_prefix = self.initial_data['user_prefix']
        self.robot_prefix = self.initial_data['robot_prefix']
        self.memory = self.initial_data['memory']
        self.history.clear()

    def _get_local_file_name(self):
        return f"{self.from_user_id}_{self.bot_name}_{self.topic}.json"

    def _load_data_from_local(self):
        if not (self.local_data_folder / self._get_local_file_name()).exists():
            # No local data file, a new user.
            return
        with open(
            self.local_data_folder / self._get_local_file_name(), "r", encoding="utf-8"
        ) as f:
            json_data = json.load(f)
            self.feeling = json_data["feeling"]
            self.photo_pool = json_data["photo_pool"]
            self.tid = json_data["tid"]
            self.last_cmd = json_data["last_cmd"]
            self.history = json_data["history"]
            self.tokens_used = json_data["tokens_used"]
            self.persona_preset = json_data["persona_preset"]
            self.memory = json_data["memory"]

    def _save_data_to_local(self):
        json_data = {
            "feeling": self.feeling,
            "photo_pool": self.photo_pool,
            "tid": self.tid,
            "last_cmd": self.last_cmd,
            "history": self.history,
            "tokens_used": self.tokens_used,
            "persona_preset": self.persona_preset,
            "memory": self.memory,
        }
        with open(
            self.local_data_folder / self._get_local_file_name(), "w", encoding="utf-8"
        ) as f:
            json.dump(json_data, f)

    def publish_msg(self, msg: str):
        self._load_from_db()
        reslut = self._publish_msg(msg)
        self._save_to_db()
        self._save_data_to_local()
        logging.info("Publish msg done")
        return reslut

    def _load_from_db(self):
        json_str = db.get_user_data(f"{self.from_user_id}:{self.bot_name}")
        logging.info("Load from db: %s", json_str)
        if json_str == "":
            logging.info("Find no user data for %s in db", self.from_user_id)
            return
        json_data = json.loads(json_str)
        logging.info("Load from db: %s", json_data)
        self.feeling = json_data["feeling"]
        if self.feeling > 10 and len(self.photo_pool) == 0:
            # Reload photo_pools. Because we do not save what photos
            # are seen before by the user, we make all the
            # photos unread as a bonus.
            self._reload_photo_pool()
        self.tokens_used['timeCount'] = json_data["timeCount"]
        self.tokens_used['tokenCount'] = json_data["tokenCount"]

    def _reload_photo_pool(self):
        for i in range(0, int(self.feeling / 10)):
            self._load_photo_pool((i + 1) * 10)

    def _load_photo_pool(self, feeling):
        # Arrived at a new level
        level_path = self.photos_root / f"lv{int(feeling / 10)}"
        logging.info(f"Arrived at level {int(feeling / 10)}")
        logging.info("Level photos path: " + str(level_path))
        if level_path.exists():
            available_photo = []
            for photo in level_path.iterdir():
                available_photo.append(photo)
            # Choose 2-4 photos to add to the pool
            for _ in range(0, random.randint(2, 4)):
                logging.info("Add photo to pool %s", photo)
                photo = random.choice(available_photo)
                self.photo_pool[str(photo)] = 1

    def _save_to_db(self):
        json_data = {
            "feeling": self.feeling,
            "timeCount": self.tokens_used['timeCount'],
            "tokenCount": self.tokens_used['tokenCount']
        }
        logging.debug("Save to db: %s", json_data)
        db.save_user_data(
            f"{self.from_user_id}:{self.bot_name}", json.dumps(json_data))

    def _proc_sys_cmd(self, msg_str: str):
        sys_cmd = cmd_proc.SysCmd(msg_str)
        self.history, result = sys_cmd.process(
            self.history)
        logging.debug("Resut: %s", result)
        return result

    def _proc_echo_cmd(self):
        content = "预设信息是: \n"
        for his in self.persona_preset:
            content += his["role"] + ": " + his["content"] + "\n"
        content += "聊天历史记录是：\n"
        for his in self.history:
            content += his["role"] + ": " + his["content"] + "\n"
        return content

    def _proc_normal_chat(self, msg_str: str):
        msg_str = self.user_prefix + msg_str
        self.history.append(
            {
                "role": "user",
                "content": msg_str,
            }
        )
        content = self.ai_resp()
        self.history.append(
            {
                "role": "assistant",
                "content": content,
            }
        )
        content = content.lstrip(
            self.robot_prefix).strip(",.!?;:。，！？；：")
        if len(self.history) > common.MAX_HISTORY_DATA:
            # Remove the oldest 2 message
            self.history.pop(0)
            self.history.pop(0)
        # When user talk with ai, increase feeling according to the conversation
        self.increase_feeling(msg_str, content)
        return content

    def _proc_reset_cmd(self):
        self.prepare_persona()
        return "人格已经重置"

    def _publish_msg(self, msg_str: str):
        head = {}
        head["mime"] = utils.encode_to_bytes("text/x-drafty")

        self.tid += 1

        logging.info("Received: %s", msg_str)
        if cmd_proc.check_if_command_valid(msg_str):
            content = self._proc_sys_cmd(msg_str)
        elif msg_str.strip('"') in common.CTRL_KEYS:
            content = self.cmd_resp(msg_str)
        elif msg_str.lower() == "echo":
            content = self._proc_echo_cmd()
        elif msg_str.lower() == "reset":
            content = self._proc_reset_cmd()
        else:
            content = self._proc_normal_chat(msg_str)

        if not content:
            raise Exception("No reply")

        logging.info("Reply: %s", content)

        self.last_cmd = msg_str

        return pb.ClientMsg(
            pub=pb.ClientPub(
                id=str(self.tid),
                topic=self.topic,
                no_echo=True,
                head=head,
                content=utils.encode_to_bytes(content),
            ),
        )

    def increase_feeling(self, msg: str, resp: str) -> None:
        self.feeling += 1
        logging.info("Feeling: %d", self.feeling)
        if self.feeling % 10 == 0:
            self._load_photo_pool(self.feeling)

    def generate_prompt(self):
        """Returns list[dict[str, str]]. During this process, the 
        history and persona_preset will be trimed to max prompt length."""
        total_len = 0
        for msg in self.persona_preset:
            total_len += len(msg["content"])
        for msg in self.history:
            total_len += len(msg["content"])
        while total_len > common.MAX_PROMPT_LEN:
            # Pop the oldest message from history first.
            if len(self.history) > 0:
                content = self.history.pop(0)
                total_len -= len(content["content"])
                continue
            # Pop the oldest message from persona_preset because it's too long.
            if len(self.persona_preset) > 0:
                content = self.persona_preset.pop(0)
                total_len -= len(content["content"])
                continue
        messages = []
        messages.extend(self.persona_preset)
        if self.memory:
            messages.extend(self.history)
        else:
            messages.append(self.history[-1])
        return messages

    def ai_resp(self) -> str:
        # Sleep 3 seconds to avoid too many requests.
        # time.sleep(3)
        prompt_data = self.generate_prompt()
        words = 0
        # Don't calculate prompt as default.
        if self.memory:
            words = len(self.history[-1]["content"])
        else:
            for msg in self.history:
                words += len(msg["content"])
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=prompt_data,
        )
        answer = response.choices[0]["message"]["content"].strip('"')
        words += len(answer)
        if self.tokens_left["tokenCount"] > 0:
            self.tokens_left["tokenCount"] -= words
            self.tokens_used['tokenCount'] += words
            if self.tokens_left["tokenCount"] < 0:
                self.tokens_left["tokenCount"] = 0
        else:
            self.tokens_left["timeCount"] -= 1
            self.tokens_used['timeCount'] += 1
            if self.tokens_left["timeCount"] < 0:
                self.tokens_left["timeCount"] = 0
        db.save_tokens_left(self.from_user_id,self.tokens_left)
        # logging.info(answer)
        return answer

    def cmd_resp(self, cmd: str):
        """Returns str | dict[str, Any]"""
        cmd = cmd.strip('"')
        logging.debug("Received command: %s", cmd)
        if cmd == "命令":
            available_cmd = "可以使用的命令："
            for key, val in common.CTRL_CMDS.items():
                available_cmd += f"\n[{key}]：{val}"
            return available_cmd
        elif cmd == "查状态":
            _unread_photos = sum(self.photo_pool.values())
            return f"""当前状态:
好感度：{self.feeling}
已解锁照片：{_unread_photos}/{len(self.photo_pool)}
剩余次数：{self.tokens_left['timeCount']}
剩余tokens: {self.tokens_left['tokenCOunt']}
记忆：{'开' if self.memory else '关'}"""
        elif cmd == "看照片":
            return self.get_next_photo()
        elif cmd == "记忆开":
            self.memory = True
            return "记忆已开启"
        elif cmd == "记忆关":
            self.memory = False
            return "记忆已关闭"
        else:
            logging.error("Unknown command")

        return None

    def get_next_photo(self):
        if self.last_cmd.strip('"') == "看照片":
            return "刚刚发过了嘛，不能总是看照片啦！"
        unread_photos = [
            photo for photo, status in self.photo_pool.items() if status == 1
        ]
        if len(unread_photos) == 0:
            return "暂时没有可以看的照片啦，和我聊聊天，解锁更多的照片把！"
        photo = random.choice(unread_photos)
        self.photo_pool[photo] = 0
        self.history.append(
            {"role": "user", "content": "我：看照片"})
        self.history.append(
            {"role": "assistant",
                "content": self.robot_prefix + "我刚刚发了一张照片给你。"}
        )
        return inline_image(pathlib.Path(photo))


def CreatePersona(bot_name: str,
                  from_user_id: str,
                  topic: str,
                  photos: pathlib.Path,
                  tokens_left,
                  ) -> Persona:
    logging.debug("Get robot data %s", bot_name)
    try:
        with redis.Redis(
            host="47.103.17.145", port=8010, db=6, password="godword"
        ) as redis_ttl:
            bot_data = redis_ttl.get(bot_name)
            if bot_data == None:
                logging.error(
                    "Bot %s not found. Are you runnig a existing robot?", bot_name)
                return None
            json_data = json.loads(bot_data)
    except Exception as e:
        logging.error("Error in get robot data %s", e)
        return None
    
    if "memory" not in json_data:
        # 默认记忆开启
        json_data["memory"] = True

    return Persona(
        bot_name=bot_name,
        from_user_id=from_user_id,
        topic=topic,
        photos=photos,
        initial_data=json_data,
        tokens_left=tokens_left,
    )
