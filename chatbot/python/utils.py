import json
import common
from google.protobuf.json_format import MessageToDict


def encode_to_bytes(src):
    # encode_to_bytes converts the 'src' to a byte array.
    # An object/dictionary is first converted to json string then it's converted to bytes.
    # A string is directly converted to bytes.
    if src == None:
        return None
    return json.dumps(src).encode('utf-8')


# Shorten long strings for logging.
def clip_long_string(obj):
    if isinstance(obj, str):
        if len(obj) > common.MAX_LOG_LEN:
            return '<' + str(len(obj)) + ' bytes: ' + obj[:12] + '...' + obj[-12:] + '>'
        return obj
    elif isinstance(obj, (list, tuple)):
        return [clip_long_string(item) for item in obj]
    elif isinstance(obj, dict):
        return dict((key, clip_long_string(val)) for key, val in obj.items())
    else:
        return obj


def to_json(msg):
    return json.dumps(clip_long_string(MessageToDict(msg)))
