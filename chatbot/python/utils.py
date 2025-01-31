import json
import logging
import logging.handlers
import pathlib
import os
import datetime
import common
from google.protobuf.json_format import MessageToDict

def encode_to_bytes(src):
    # {"pub":{"id":"81417","topic":"usrLO0Is2K06BQ","noecho":true,"head":{"mime":"text/x-drafty"},"content":{"txt":"你好 你好 hay","fmt":[{"tp":"BR","len":1,"at":2},{"tp":"BR","len":1,"at":5}]}}} 
    # encode_to_bytes converts the 'src' to a byte array.
    # An object/dictionary is first converted to json string then it's converted to bytes.
    # A string is directly converted to bytes.
    if src == None:
        return None
    return json.dumps(src).encode("utf-8")


# Shorten long strings for logging.
def clip_long_string(obj):
    if isinstance(obj, str):
        if len(obj) > common.MAX_LOG_LEN:
            return (
                "<"
                + str(len(obj))
                + " bytes: "
                + obj[:12]
                + "..."
                + obj[-12:]
                + ">"
            )
        return obj
    elif isinstance(obj, (list, tuple)):
        return [clip_long_string(item) for item in obj]
    elif isinstance(obj, dict):
        return dict((key, clip_long_string(val)) for key, val in obj.items())
    else:
        return obj


def to_json(msg):
    return json.dumps(clip_long_string(MessageToDict(msg)))


def read_from_file(file_path) -> str:
    with open(file_path, "r") as f:
        return f.read()


def config_logging(logfile_name: str = ""):
    time_str = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    process_id = os.getpid()
    # Set logfile name with date
    if logfile_name == "":
        logfile_name = f"chatbot[{process_id}]-{time_str}" + ".log"
    logs_dir = pathlib.Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_rotate_handler = logging.handlers.RotatingFileHandler(
        logs_dir / logfile_name,
        mode="a",
        encoding="utf-8",
        maxBytes=1024 * 1024 * 10,
        backupCount=5,
    )
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers={file_rotate_handler},
        # filename=logs_dir / logfile_name,
        # filemode="a",
        # encoding="utf-8",
    )
    logging.getLogger("grpc").setLevel(logging.INFO)
    logging.getLogger("grpc._channel").setLevel(logging.INFO)
    logging.getLogger("grpc._server").setLevel(logging.INFO)
