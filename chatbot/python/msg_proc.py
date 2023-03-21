import time
import logging
import multiprocessing
import model_pb2 as pb
import model_pb2_grpc as pbx
from persona import Persona, CreatePersona
import utils
import json
import db
import traceback
import common


def note_read(topic, seq):
    return pb.ClientMsg(note=pb.ClientNote(topic=topic, what=pb.READ, seq_id=seq))


def typing_reply(topic):
    return pb.ClientMsg(note=pb.ClientNote(topic=topic, what=pb.KP))


def publish_msg(content, tid, topic):
    head = {}
    head["mime"] = utils.encode_to_bytes("text/x-drafty")

    return pb.ClientMsg(
        pub=pb.ClientPub(
            id=str(tid),
            topic=topic,
            no_echo=True,
            head=head,
            content=utils.encode_to_bytes(content),
        ),
    )

def _recover_multiple_lines(json_msg):
    # json_str: "content":{"txt":"你好 你好 hay","fmt":[{"tp":"BR","len":1,"at":2},{"tp":"BR","len":1,"at":5}]}}} 
    try:
        if "txt" in json_msg:
            if "fmt" not in json_msg:
                return json_msg['txt']
            for fmt in json_msg['fmt']:
                if fmt['tp'] == 'BR':
                    json_msg['txt'] = json_msg['txt'][:fmt['at']] + '\n' + json_msg['txt'][fmt['at']+1:]
            return json_msg['txt']
    except Exception as e:
        logging.error("Failed to recover multiple lines string: %s with exception %s", json_msg,e)
        return json_msg

def _parse_msg(msg:str):
    # Check if msg is json string or complain string
    try:
        d = json.loads(msg)
        return _recover_multiple_lines(d)
    except ValueError:
        # This is not json string, just return the string
        return msg

def process_chat(
    msg,
    tid,
    queue_out,
    bot_name,
    persona,
    photos_root,
):
    utils.config_logging(
        logfile_name=f"{bot_name}_{msg.data.from_user_id}_{msg.data.topic}.log"
    )
    if msg == None:
        return
    # Respond to message.
    # Mark received message as read.
    queue_out.put(note_read(msg.data.topic, msg.data.seq_id))
    # Notify user that we are responding.
    queue_out.put(typing_reply(msg.data.topic))
    # # Insert a small delay to prevent accidental DoS self-attack.
    time.sleep(0.1)

    ttl_valid, tokens_left = db.get_user_validity(bot_name, msg.data.from_user_id)
    if not ttl_valid:
        # Respond with with chat persona for this topic.
        queue_out.put(
            publish_msg(common.COMMON_MSG["USER_TTL_INVALID"], tid, msg.data.topic)
        )
        return

    if tokens_left <= 0:
        queue_out.put(
            publish_msg(common.COMMON_MSG["USER_TOKEN_INVALID"], tid, msg.data.topic)
        )
        return

    msg_str =_parse_msg(msg.data.content.decode("utf-8").strip('"'))
    if msg_str not in common.CTRL_KEYS:
        tokens_left -= 1
        db.save_tokens_left(bot_name, msg.data.from_user_id, tokens_left)

    logging.info("%s: User %s is valid", bot_name, msg.data.from_user_id)

    chat_persona = CreatePersona(
        persona=persona,
        bot_name=bot_name,
        from_user_id=msg.data.from_user_id,
        topic=msg.data.topic,
        photos=photos_root,
    )

    # Update current tokens left
    chat_persona.set_tokens_left(tokens_left)
    try:
        # Respond with with chat persona for this topic.
        msg = chat_persona.publish_msg(msg_str)
        queue_out.put(msg)
    except Exception as e:
        logging.error("Error in publish_msg %s", e)
        logging.error(traceback.format_exc())
        queue_out.put(
            publish_msg(common.COMMON_MSG["INTERNAL_ERROR"], tid, msg.data.topic)
        )
