"""Define persona class for chatbot."""
import requests
import random
import json
import base64
import openai
import pathlib
from abc import ABC, abstractmethod
from typing import Any
from PIL import Image
import os
from io import BytesIO as memory_io

# Import generated grpc modules
from tinode_grpc import pb
from tinode_grpc import pbx
import utils
import common


def inline_image(filename: pathlib.Path):
    # Create drafty representation of a message with an inline image.
    try:
        im = Image.open(filename, 'r')
        width = im.width
        height = im.height
        format = im.format if im.format else "JPEG"
        if width > common.MAX_IMAGE_DIM or height > common.MAX_IMAGE_DIM:
            # Scale the image
            scale = min(min(width, common.MAX_IMAGE_DIM) / width,
                        min(height, common.MAX_IMAGE_DIM) / height)
            width = int(width * scale)
            height = int(height * scale)
            resized = im.resize((width, height))
            im.close()
            im = resized

        mimetype = 'image/' + format.lower()
        bitbuffer = memory_io()
        im.save(bitbuffer, format=format)
        data = base64.b64encode(bitbuffer.getvalue())

        # python3 fix.
        if type(data) is not str:
            data = data.decode()

        result = {
            'txt': ' ',
            'fmt': [{'len': 1}],
            'ent': [{'tp': 'IM', 'data':
                     {'val': data, 'mime': mimetype, 'width': width, 'height': height,
                      'name': filename.name}}]
        }
        im.close()
        return result
    except IOError as err:
        print("Failed processing image '" + filename + "':", err)
        return None


class Persona(ABC):
    """Abstract class for a persona. Persona is used for each topic.
    Cannot share data between topics.
    """
    persona_preset: list[dict[str, Any]] = []
    history: list[dict[str, str]]
    feeling:  int
    photos_root: pathlib.Path
    photo_pool: dict[pathlib.Path:int]
    cmds: list[str] = [
        "命令",
        "看照片",
        "查状态",
    ]
    tid: int
    topic: str
    last_cmd: str

    def __init__(self, topic: str, photos: pathlib.Path) -> None:
        self.topic = topic
        self.photos_root = photos
        self.photo_pool = {}
        self.feeling = 0
        self.tid = 100
        self.last_cmd = ''
        self.history = []
        self.prepare_persona()

    @abstractmethod
    def prepare_persona(self) -> None:
        pass

    def publish_msg(self, msg: str):
        head = {}
        head['mime'] = utils.encode_to_bytes('text/x-drafty')

        self.tid += 1

        msg_str = msg.decode('utf-8')
        print("Received:", msg_str)
        print(self.cmds)
        if msg_str.strip('"') in self.cmds:
            content = self.cmd_resp(msg_str)
        else:
            self.history.append(
                {
                    "role": "user",
                    "content": msg_str,
                }
            )
            content = self.ai_resp()
            self.history.append({
                "role": "assistant",
                "content": content,
            })
            if len(self.history) > common.MAX_HISTORY_DATA:
                # Remove the oldest 2 message
                self.history.pop(0)
                self.history.pop(0)
            # When user talk with ai, increase feeling according to the conversation
            self.increase_feeling(msg_str, content)

        if not content:
            return None

        self.last_cmd = msg_str

        return pb.ClientMsg(
            pub=pb.ClientPub(
                id=str(self.tid),
                topic=self.topic,
                no_echo=True,
                head=head,
                content=utils.encode_to_bytes(content)),
        )

    def increase_feeling(self, msg: str, resp: str) -> None:
        self.feeling += 5
        if self.feeling % 10 == 0:
            # Arrived at a new level
            level_path = self.photos_root / \
                f'level{int(self.feeling / 10) - 1}'
            if level_path.exists():
                for photo in level_path.iterdir():
                    self.photo_pool[photo] = 1

    def generate_prompt(self) -> list[dict[str, str]]:
        messages = []
        messages.extend(self.persona_preset)
        messages.extend(self.history)
        return messages

    def ai_resp(self) -> str:
        openai.api_key = ''
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.generate_prompt(),
        )
        print(response.choices[0]['message']['content'])
        return response.choices[0]['message']['content'].strip('"')

    def cmd_resp(self, cmd: str) -> str | dict[str, Any]:
        cmd = cmd.strip('"')
        if (cmd == '命令'):
            return """可以使用的命令：\n
            [命令]：查看命令列表\n
            [查状态]：查看当前状态\n
            [看照片]：随机展示一张照片\n
            """
        elif (cmd == '查状态'):
            _unread_photos = sum(self.photo_pool.values())
            return f"""当前状态:
            好感度：{self.feeling}
            已解锁照片：{_unread_photos}/{len(self.photo_pool)}
            """
        elif (cmd == '看照片'):
            return self.get_next_photo()
        else:
            print("Unknown command")

        return None

    def get_next_photo(self) -> str | dict[str, Any]:
        if self.last_cmd.strip('"') == '看照片':
            return "刚刚发过了嘛，不能总是看照片啦！"
        unread_photos = [photo for photo,
                         status in self.photo_pool.items() if status == 1]
        if len(unread_photos) == 0:
            return "暂时没有可以看的照片啦，和我聊聊天，解锁更多的照片把！"
        photo = random.choice(unread_photos)
        self.photo_pool[photo] = 0
        return inline_image(photo)


class PsychoPersona(Persona):
    def prepare_persona(self) -> None:
        self.persona_preset = [
            {"role": "system", "content": "请模拟动漫 <电锯人> Makima的人格来和我对话"}
        ]


class WriterPersona(Persona):
    def prepare_persona(self) -> None:
        self.persona_preset = [
            {"role": "system", "content": "请模拟动漫 <间谍过家家> Yor的人格来和我对话"}
        ]


def CreatePersona(persona: str, topic: str, photos_root: pathlib.Path) -> Persona:
    if persona == "writer":
        return WriterPersona(topic, photos_root)
    if persona == "psycho":
        return PsychoPersona(topic, photos_root)
