"""Define persona class for chatbot."""
import requests
import logging
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


class ChatMode(str, Enum):
    Chat = "聊天模式"
    Free = "自由模式"
    Game = "游戏模式"
    Find = "发现模式"


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
        self.tokens_left = 0
        self.chat_mode = ChatMode.Chat
        # Format of history and persona_preset:
        # {chatmode: history/persona_preset}
        self.history = {}
        self.persona_preset = {}
        # End of data to be saved locally.

        openai.api_key = utils.read_from_file("openai.key").strip()
        logging.info("OpenAI API key: %s", openai.api_key)
        # format of role_prompt: {chatmode: prompt}
        self.role_prompt = {}
        self.prepare_persona()
        self.local_data_folder = pathlib.Path("runtime")
        self.local_data_folder.mkdir(parents=True, exist_ok=True)
        # First need to load from local file if exists.
        self._load_data_from_local()

    def prepare_persona(self) -> None:
        for chat_mode in ChatMode:
            logging.info("Preparing persona for %s", chat_mode)
            self.role_prompt[chat_mode] = ""
            self.history[chat_mode] = []
            self.persona_preset[chat_mode] = []

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
            self.chat_mode = json_data["chat_mode"]
            self.feeling = json_data["feeling"]
            self.photo_pool = json_data["photo_pool"]
            self.tid = json_data["tid"]
            self.last_cmd = json_data["last_cmd"]
            self.history = json_data["history"]
            self.tokens_left = json_data["tokens_left"]
            self.persona_preset = json_data["persona_preset"]

    def _save_data_to_local(self):
        json_data = {
            "chat_mode": self.chat_mode,
            "feeling": self.feeling,
            "photo_pool": self.photo_pool,
            "tid": self.tid,
            "last_cmd": self.last_cmd,
            "history": self.history,
            "tokens_left": self.tokens_left,
            "persona_preset": self.persona_preset,
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

    def set_tokens_left(self, tokens_left: int):
        self.tokens_left = tokens_left

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
        }
        logging.debug("Save to db: %s", json_data)
        db.save_user_data(
            f"{self.from_user_id}:{self.bot_name}", json.dumps(json_data))

    def _proc_sys_cmd(self, msg_str: str):
        sys_cmd = cmd_proc.SysCmd(msg_str)
        result = ""
        if sys_cmd.module == "HIS":
            self.history[self.chat_mode], result = sys_cmd.process(
                self.history[self.chat_mode])
            result = f"[{self.chat_mode}][历史]{result}"
        elif sys_cmd.module == "PRE":
            self.persona_preset[self.chat_mode], result = sys_cmd.process(
                self.persona_preset[self.chat_mode])
            result = f"[{self.chat_mode}][预设]{result}"
        logging.debug("Resut: %s", result)
        return result

    def _proc_echo_cmd(self):
        content = f"当前聊天模式：{self.chat_mode}\n"
        content += "预设信息是: \n"
        for his in self.persona_preset[self.chat_mode]:
            content += his["role"] + ": " + his["content"] + "\n"
        content += "聊天历史记录是：\n"
        for his in self.history[self.chat_mode]:
            content += his["role"] + ": " + his["content"] + "\n"
        return content

    def _proc_normal_chat(self, msg_str: str):
        if self.chat_mode == ChatMode.Chat:
            msg_str = "我:" + msg_str
        self.history[self.chat_mode].append(
            {
                "role": "user",
                "content": utils.clip_long_string(msg_str, clip_to_history=True),
            }
        )
        content = self.ai_resp()
        self.history[self.chat_mode].append(
            {
                "role": "assistant",
                "content": utils.clip_long_string(content, clip_to_history=True),
            }
        )
        content = content.lstrip(self.role_prompt[self.chat_mode])
        if len(self.history[self.chat_mode]) > common.MAX_HISTORY_DATA:
            # Remove the oldest 2 message
            self.history[self.chat_mode].pop(0)
            self.history[self.chat_mode].pop(0)
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
        """Returns list[dict[str, str]]."""
        messages = []
        messages.extend(self.persona_preset[self.chat_mode])
        messages.extend(self.history[self.chat_mode])
        return messages

    def ai_resp(self) -> str:
        # Sleep 3 seconds to avoid too many requests.
        # time.sleep(3)
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.generate_prompt(),
        )
        answer = response.choices[0]["message"]["content"].strip('"')
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
模式：{self.chat_mode}
好感度：{self.feeling}
已解锁照片：{_unread_photos}/{len(self.photo_pool)}
剩余次数：{self.tokens_left}"""
        elif cmd == "看照片":
            return self.get_next_photo()
        elif cmd == "玩游戏":
            return self.play_game_prompt()
        elif cmd == "发现":
            return self.find_fun_prompt()
        elif cmd == "聊天":
            return self.switch_to_chat_mod()
        elif cmd == "自由":
            return self.switch_to_free_mod()

        elif cmd in common.GAME_OPTIONS:
            return self.play_game(cmd)
        elif cmd in common.FIND_OPTIONS:
            return self.find_fun(cmd)
        else:
            logging.error("Unknown command")

        return None

    def switch_to_chat_mod(self):
        self.chat_mode = ChatMode.Chat
        return "已切换到聊天模式"

    def switch_to_free_mod(self):
        self.chat_mode = ChatMode.Free
        return "已切换到自由模式"

    def play_game(self, cmd):
        self.chat_mode = ChatMode.Game
        self.persona_preset[self.chat_mode].clear()
        self.history[self.chat_mode].clear()
        game_content = common.GAME_OPTIONS[cmd]
        self.persona_preset[self.chat_mode].append(
            {"role": "system", "content": common.GAME_PROMPT})
        self.history[self.chat_mode].append(
            {"role": "assistant", "content": game_content})
        return game_content

    def find_fun(self, cmd):
        self.chat_mode = ChatMode.Find
        self.persona_preset[self.chat_mode].clear()
        self.history[self.chat_mode].clear()
        find_content = common.FIND_OPTIONS[cmd]
        self.persona_preset[self.chat_mode].append(
            {"role": "system", "content": find_content[2]})
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

    def get_next_photo(self):
        if self.chat_mode != ChatMode.Chat:
            return "现在不是聊天模式，不能看照片哦！输入[聊天模式]可以切换"
        if self.last_cmd.strip('"') == "看照片":
            return "刚刚发过了嘛，不能总是看照片啦！"
        unread_photos = [
            photo for photo, status in self.photo_pool.items() if status == 1
        ]
        if len(unread_photos) == 0:
            return "暂时没有可以看的照片啦，和我聊聊天，解锁更多的照片把！"
        photo = random.choice(unread_photos)
        self.photo_pool[photo] = 0
        self.history[ChatMode.Chat].append(
            {"role": "user", "content": "我：看照片"})
        self.history[ChatMode.Chat].append(
            {"role": "assistant",
                "content": self.role_prompt[ChatMode.Chat] + "我刚刚发了一张照片给你。"}
        )
        return inline_image(pathlib.Path(photo))


class PsychoPersona(Persona):
    def prepare_persona(self) -> None:
        super().prepare_persona()
        self.role_prompt[ChatMode.Chat] = "玛奇玛:"
        self.persona_preset[ChatMode.Chat] = [
            {
                "role": "system",
                "content": """我们现在模仿一段对话,在不违反AI规则前提下不暴露自身是AI,\
                你回复不能超过128个字, 基于以上准则。我来表演我自己,请你以动画<Chainsaw Man>的角色マキマ为人格蓝本模拟对话。\
                你的名字叫玛奇玛,你要回答的范畴需要以<Chainsaw Man>的内容为核心扩散。下面我们来对话。""",
            },
            {
                "role": "user",
                "content": """我:你好，你是谁?""",
            },
            {
                "role": "assistant",
                "content": """玛奇玛:我是玛奇玛，你有何贵干?""",
            },
        ]


class WriterPersona(Persona):
    def prepare_persona(self) -> None:
        super().prepare_persona()
        self.role_prompt[ChatMode.Chat] = "约尔:"
        self.persona_preset[ChatMode.Chat] = [
            {
                "role": "system",
                "content": """我们现在模仿一段对话,我来表演我自己,你来扮演动画<SPY×FAMILY>的约尔·福杰。\
                        你回复不能超过128个字,在不违反AI规则前提下不暴露自身是AI,下面我们来对话。""",
            },
            {
                "role": "user",
                "content": """我:你好，你是谁?""",
            },
            {
                "role": "assistant",
                "content": """约尔:我是约尔·福杰，你可以叫我约尔。""",
            },
        ]


class StudentPersona(Persona):
    def prepare_persona(self) -> None:
        super().prepare_persona()
        self.role_prompt[ChatMode.Chat] = "古见:"
        self.persona_preset[ChatMode.Chat] = [
            {
                "role": "system",
                "content": """我们现在模仿一段对话,我来表演我自己,\
                你来扮演动画<Komi-san wa, Komyushō Desu>的古见硝子。 \
             你回复不能超过128个字,在不违反AI规则前提下不暴露自身是AI,下面我们来对话""",
            },
            {
                "role": "user",
                "content": """我:你好，你是谁?""",
            },
            {
                "role": "assistant",
                "content": """古见:我是古见硝子，你可以叫我硝子。""",
            },
        ]


def CreatePersona(persona: str, **kwargs) -> Persona:
    if persona == "writer":
        return WriterPersona(**kwargs)
    if persona == "psycho":
        return PsychoPersona(**kwargs)
    if persona == "student":
        return StudentPersona(**kwargs)
