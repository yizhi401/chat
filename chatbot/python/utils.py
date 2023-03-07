import json
import logging
import pathlib
import os
import datetime
import common
from google.protobuf.json_format import MessageToDict


def encode_to_bytes(src):
    # encode_to_bytes converts the 'src' to a byte array.
    # An object/dictionary is first converted to json string then it's converted to bytes.
    # A string is directly converted to bytes.
    if src == None:
        return None
    return json.dumps(src).encode("utf-8")


# Shorten long strings for logging.
def clip_long_string(obj, clip_to_history=False):
    if isinstance(obj, str):
        if len(obj) > common.MAX_LOG_LEN:
            if clip_to_history:
                return obj[: common.MAX_LOG_LEN]
            else:
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


def config_logging():
    time_str = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    process_id = os.getpid()
    # Set logfile name with date
    logfile_name = f"chatbot[{process_id}]-{time_str}" + ".log"
    logs_dir = pathlib.Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        filename=logs_dir / logfile_name,
        filemode="w",
        # encoding="utf-8",
    )
    logging.getLogger("grpc").setLevel(logging.INFO)
    logging.getLogger("grpc._channel").setLevel(logging.INFO)
    logging.getLogger("grpc._server").setLevel(logging.INFO)
