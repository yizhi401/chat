
import requests
import json
import base64
import pathlib
from abc import ABC, abstractmethod
from PIL import Image
try:
    from io import BytesIO as memory_io
except ImportError:
    from cStringIO import StringIO as memory_io

# Maximum allowed linear dimension of an inline image in pixels.
MAX_IMAGE_DIM = 768


def encode_to_bytes(src):
    # encode_to_bytes converts the 'src' to a byte array.
    # An object/dictionary is first converted to json string then it's converted to bytes.
    # A string is directly converted to bytes.
    if src == None:
        return None
    # if isinstance(src, str):
        # return src.encode('utf-8')
    return json.dumps(src).encode('utf-8')


def inline_image(filename):
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
                      'name': os.path.basename(filename)}}]
        }
        im.close()
        return result
    except IOError as err:
        print("Failed processing image '" + filename + "':", err)
        return None


class Persona(ABC):

    history: list[str] = []
    feeling: int
    photos_root: pathlib.Path
    photo_pool: dict[pathlib.Path:int]
    cmds: list[str] = [
        "命令",
        "看照片",
        "查状态",
    ]

    def __init__(self, photos: pathlib.Path) -> None:
        self.photos_root = photos

    def respond(self, msg: bytes) -> None:
        msg_str = msg.decode('utf-8')
        if msg_str in self.cmds:
            return self.cmd_resp(msg_str)
        pass

    @abstractmethod
    def ai_resp(self, msg: str) -> str:
        pass

    def cmd_resp(self, cmd: str) -> str:
        if (cmd == '命令'):
            return """
            命令：查看命令列表
            查状态：查看当前状态
            看照片：随机展示一张照片
            """
        elif (cmd == '查状态'):
            _unread_photos = sum(self.photo_pool.values())
            return f"""当前状态
            好感度：{self.feeling}
            已解锁照片：{_unread_photos}/{len(self.photo_pool)}
            """
        elif (cmd == '看照片'):
        return cmd


class PsychoPersona(Persona):
    def ai_resp(self, msg: str) -> None:
        pass


class WriterPersona(Persona):
    def ai_resp(self, msg: str) -> None:
        url = "https://api.writesonic.com/v2/business/content/chatsonic?engine=premium&language=zh"
        proxies = {'http': 'http://127.0.0.1:33210',
                   'https': 'http://127.0.0.1:33210', }

        payload = {
            "enable_google_results": "true",
            "enable_memory": True,
            "input_text": msg,
            "history_data": self.history,
        }
        print(payload)
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-KEY": "7eaae20d-c54f-4eba-bbfd-eae8d39fd6d3"
        }
        self.history.append(
            {
                "is_sent": True,
                "message": msg,
            }
        )

        response = requests.post(
            url, json=payload, headers=headers, proxies=proxies, verify=False)
        if response.status_code == 200:
            print(response.text)
            json_data = json.loads(response.text)
            self.history.append({
                "is_sent": False,
                "message": json_data["message"]
            })
            return json_data["message"]

        return response.text


def CreatePersona(persona: str) -> Persona:
    if persona == "writer":
        return WriterPersona()
