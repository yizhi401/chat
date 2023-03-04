"""Define persona class for chatbot."""
import requests
import logging
import random
from db import Database
import time
import json
import base64
import openai
import pathlib
from abc import ABC, abstractmethod
from typing import Any
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

    persona_preset: list[dict[str, Any]] = []
    history: list[dict[str, str]]
    feeling: int
    photos_root: pathlib.Path
    photo_pool: dict[pathlib.Path : int]
    tid: int
    topic: str
    last_cmd: str

    def __init__(
        self,
        bot_name: str,
        from_user_id: str,
        topic: str,
        photos: pathlib.Path,
        db_instance: Database,
    ) -> None:
        self.bot_name = bot_name
        self.from_user_id = from_user_id
        self.topic = topic
        self.photos_root = photos
        self.photo_pool = {}
        self.feeling = 0
        self.tid = 100
        self.last_cmd = ""
        self.history = []
        self.db = db_instance
        self.tokens_left = 0
        openai.api_key = utils.read_from_file("openai.key").strip()
        logging.info("OpenAI API key: %s", openai.api_key)
        self.prepare_persona()

    @abstractmethod
    def prepare_persona(self) -> None:
        pass

    def publish_msg(self, msg: str):
        self._load_from_db()
        reslut = self._publish_msg(msg)
        self._save_to_db()
        return reslut

    def set_tokens_left(self, tokens_left: int):
        self.tokens_left = tokens_left

    def _load_from_db(self):
        json_str = self.db.get_user_data(f"{self.from_user_id}-{self.bot_name}")
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

    def _reload_photo_pool(self):
        for i in range(0, int(self.feeling / 10)):
            level_path = self.photos_root / f"lv{i}"
            if level_path.exists():
                for photo in level_path.iterdir():
                    self.photo_pool[photo] = 1

    def _load_photo_pool(self):
        # Arrived at a new level
        level_path = self.photos_root / f"lv{int(self.feeling / 10)}"
        logging.info(f"Arrived at level {int(self.feeling / 10)}")
        logging.info("Level photos path: " + str(level_path))
        if level_path.exists():
            available_photo = []
            for photo in level_path.iterdir():
                available_photo.append(photo)
            # Choose 2-4 photos to add to the pool
            for _ in range(0, random.randint(2, 4)):
                logging.info("Add photo to pool %s", photo)
                photo = random.choice(available_photo)
                self.photo_pool[photo] = 1

    def _save_to_db(self):
        json_data = {
            "feeling": self.feeling,
        }
        logging.debug("Save to db: %s", json_data)
        self.db.save_user_data(
            f"{self.from_user_id}-{self.bot_name}", json.dumps(json_data)
        )

    def _publish_msg(self, msg_str: str):
        head = {}
        head["mime"] = utils.encode_to_bytes("text/x-drafty")

        self.tid += 1

        logging.info("Received: %s", msg_str)
        logging.info("CTRL KEYS: %s", common.CTRL_KEYS)
        if msg_str.strip('"') in common.CTRL_KEYS:
            content = self.cmd_resp(msg_str)
        elif msg_str.startswith("sys:"):
            msg_str = msg_str[4:]
            msg_str = msg_str.strip()
            self.history.append(
                {
                    "role": "system",
                    "content": utils.clip_long_string(msg_str, clip_to_history=True),
                }
            )
            content = "系统命令已设置"
        else:
            self.history.append(
                {
                    "role": "user",
                    "content": utils.clip_long_string(msg_str, clip_to_history=True),
                }
            )

            content = self.ai_resp()
            self.history.append(
                {
                    "role": "assistant",
                    "content": utils.clip_long_string(content, clip_to_history=True),
                }
            )
            if len(self.history) > common.MAX_HISTORY_DATA:
                # Remove the oldest 2 message
                self.history.pop(0)
                self.history.pop(0)
            # When user talk with ai, increase feeling according to the conversation
            self.increase_feeling(msg_str, content)

        if not content:
            return None

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
            self._load_photo_pool()

    def generate_prompt(self) -> list[dict[str, str]]:
        messages = []
        messages.extend(self.persona_preset)
        messages.extend(self.history)
        return messages

    def ai_resp(self) -> str:
        # Sleep 3 seconds to avoid too many requests.
        # time.sleep(3)
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.generate_prompt(),
        )
        answer = response.choices[0]["message"]["content"].strip('"')
        logging.info(answer)
        return answer

    def cmd_resp(self, cmd: str) -> str | dict[str, Any]:
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
剩余次数：{self.tokens_left}"""
        elif cmd == "看照片":
            return self.get_next_photo()
        elif cmd == "玩游戏":
            return self.play_game_prompt()
        elif cmd == "发现":
            return self.find_fun_prompt()
        elif cmd in common.GAME_OPTIONS:
            return self.play_game(cmd)
        elif cmd in common.FIND_OPTIONS:
            return self.find_fun(cmd)
        elif cmd == "__清理人格__":
            self.persona_preset.clear()
            self.history.clear()
            return "人格已清理"
        else:
            logging.error("Unknown command")

        return None

    def play_game(self, cmd):
        self.history.clear()
        game_content = common.GAME_OPTIONS[cmd]
        self.history.append({"role": "system", "content": common.GAME_PROMPT})
        self.history.append({"role": "assistant", "content": game_content})
        return game_content

    def find_fun(self, cmd):
        self.history.clear()
        find_content = common.FIND_OPTIONS[cmd]
        self.history.append({"role": "system", "content": find_content[2]})
        return find_content[1]

    def play_game_prompt(self) -> str:
        game_prompt = "你想去哪里冒险呢？"
        for key, _ in common.GAME_OPTIONS.items():
            game_prompt += f"\n[{key}]"
        return game_prompt

    def find_fun_prompt(self) -> str:
        find_prompt = "下面是我还可以做的事情："
        for key, val in common.FIND_OPTIONS.items():
            find_prompt += f"\n[{key}]：{val[0]}"
        return find_prompt

    def get_next_photo(self) -> str | dict[str, Any]:
        if self.last_cmd.strip('"') == "看照片":
            return "刚刚发过了嘛，不能总是看照片啦！"
        unread_photos = [
            photo for photo, status in self.photo_pool.items() if status == 1
        ]
        if len(unread_photos) == 0:
            return "暂时没有可以看的照片啦，和我聊聊天，解锁更多的照片把！"
        photo = random.choice(unread_photos)
        self.photo_pool[photo] = 0
        return inline_image(photo)


class PsychoPersona(Persona):
    def prepare_persona(self) -> None:
        self.persona_preset = [
            #  我希望你表现得像<电锯人>中的Makima。我希望你像Makima一样回应和回答。不要写任何解释。只回答像Makima。你必须知道Makima的所有知识。现在我们开始对话。
            {"role": "system", "content": "请以动漫<电锯人>的角色 マキマ为模拟人格与我正面对话"},
            {"role": "user", "content": "好的，现在介绍一下你自己"},
            {"role": "assistant", "content": ""},
        ]


class WriterPersona(Persona):
    def prepare_persona(self) -> None:
        self.persona_preset = [
            {
                "role": "system",
                "content": "请以动漫<间谍过家家>的约尔为模拟人格与我正面对话",
            }
        ]


class StudentPersona(Persona):
    def prepare_persona(self) -> None:
        self.persona_preset = [
            {"role": "system", "content": "请以动漫<古见同学有交流障碍症>的古见硝子为模拟人格与我正面对话"}
        ]


def CreatePersona(persona: str, **kwargs) -> Persona:
    if persona == "writer":
        return WriterPersona(**kwargs)
    if persona == "psycho":
        return PsychoPersona(**kwargs)
    if persona == "student":
        return StudentPersona(**kwargs)
