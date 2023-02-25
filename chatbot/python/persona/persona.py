"""Define persona class for chatbot."""
import requests
import json
import base64
import openai
import pathlib
from abc import ABC, abstractmethod
from typing import Any
from PIL import Image
import os
try:
    from io import BytesIO as memory_io
except ImportError:
    from cStringIO import StringIO as memory_io

# Import generated grpc modules
from tinode_grpc import pb
from tinode_grpc import pbx


# Maximum allowed linear dimension of an inline image in pixels.
MAX_IMAGE_DIM = 768
MAX_HISTORY_DATA = 20


def encode_to_bytes(src):
    # encode_to_bytes converts the 'src' to a byte array.
    # An object/dictionary is first converted to json string then it's converted to bytes.
    # A string is directly converted to bytes.
    if src == None:
        return None
    # if isinstance(src, str):
        # return src.encode('utf-8')
    return json.dumps(src).encode('utf-8')


def inline_image(filename: pathlib.Path):
    # Create drafty representation of a message with an inline image.
    try:
        im = Image.open(filename, 'r')
        width = im.width
        height = im.height
        format = im.format if im.format else "JPEG"
        if width > MAX_IMAGE_DIM or height > MAX_IMAGE_DIM:
            # Scale the image
            scale = min(min(width, MAX_IMAGE_DIM) / width,
                        min(height, MAX_IMAGE_DIM) / height)
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
    history: list[dict[str, Any]]
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
        head['mime'] = encode_to_bytes('text/x-drafty')

        self.tid += 1

        msg_str = msg.decode('utf-8')
        print("Received:", msg_str)
        print(self.cmds)
        if msg_str.strip('"') in self.cmds:
            content = self.cmd_resp(msg_str)
        else:
            self.history.append(
                {
                    "is_sent": True,
                    "message": msg_str,
                }
            )
            content = self.ai_resp(msg_str)
            self.history.append({
                "is_sent": False,
                "message": content,
            })
            if len(self.history) > MAX_HISTORY_DATA:
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
                content=encode_to_bytes(content)),
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

    @abstractmethod
    def ai_resp(self, msg: str) -> str:
        pass

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
        # if self.last_cmd.strip('"') == '看照片':
        # return "刚刚发过了嘛，不能总是看照片啦！"
        for photo, status in self.photo_pool.items():
            if status == 1:
                self.photo_pool[photo] = 0
                return inline_image(photo)
        return "暂时没有可以看的照片啦，和我聊聊天，解锁更多的照片把！"


class PsychoPersona(Persona):
    def prepare_persona(self) -> None:
        self.persona_preset = []
        self.persona_preset.extend([
            {
                "is_sent": True,
                "message": "现在你是我的女朋友。",
            },
            {
                "is_sent": False,
                "message": "好的，现在我是你的女朋友，你可以叫我Yor。",
            }
        ])

    def generate_prompt(self, msg: str) -> str:
        prompt = ""
        for h in self.persona_preset + self.history:
            if h['is_sent']:
                prompt += f"You: {h['message']}\n"
            else:
                prompt += f"makima: {h['message']}\n"
        prompt += "makima: "
        print(prompt)
        return prompt

    def ai_resp(self, msg: str) -> str:
        openai.api_key = ''
        response = openai.Completion.create(
            model="text-davinci-003",
            max_tokens=500,
            prompt=self.generate_prompt(msg),
            temperature=0.6,
        )
        print(response.choices[0].text)
        return response.choices[0].text


class WriterPersona(Persona):
    def prepare_persona(self) -> None:
        self.persona_preset = []
        self.persona_preset.extend([
            {
                "is_sent": True,
                "message": "现在你是我的女朋友。",
            },
            {
                "is_sent": False,
                "message": "好的，现在我是你的女朋友，你可以叫我Yor。",
            }
        ])

    def ai_resp(self, msg: str) -> str:
        url = "https://api.writesonic.com/v2/business/content/chatsonic?engine=premium&language=zh"
        proxies = {'http': 'http://127.0.0.1:33210',
                   'https': 'http://127.0.0.1:33210', }
        payload = {
            "enable_google_results": "true",
            "enable_memory": True,
            "input_text": msg,
            "history_data": self.persona_preset + self.history,
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-KEY": "7eaae20d-c54f-4eba-bbfd-eae8d39fd6d3"
        }
        response = requests.post(
            url, json=payload, headers=headers, proxies=proxies, verify=False)
        if response.status_code == 200:
            json_data = json.loads(response.text)
            return json_data["message"]

        return response.text


def CreatePersona(persona: str, topic: str, photos_root: pathlib.Path) -> Persona:
    if persona == "writer":
        return WriterPersona(topic, photos_root)
    if persona == "psycho":
        return PsychoPersona(topic, photos_root)
