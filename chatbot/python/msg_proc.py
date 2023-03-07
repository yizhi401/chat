import time
import logging
import multiprocessing
import model_pb2 as pb
import model_pb2_grpc as pbx
from persona import Persona, CreatePersona
from db import Database
import utils
import traceback
import common

friends = {}


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


def process_chat(
    queue_in,
    queue_out,
    bot_name,
    persona,
    photos_root,
):
    tid = 100
    utils.config_logging()
    db_instance = Database()
    while True:
        msg = queue_in.get()
        if msg == None:
            return
        tid += 1
        # Respond to message.
        # Mark received message as read.
        queue_out.put(note_read(msg.data.topic, msg.data.seq_id))
        # Notify user that we are responding.
        queue_out.put(typing_reply(msg.data.topic))
        # # Insert a small delay to prevent accidental DoS self-attack.
        time.sleep(0.1)

        ttl_valid, tokens_left = db_instance.get_user_validity(
            bot_name, msg.data.from_user_id)
        if not ttl_valid:
            # Respond with with chat persona for this topic.
            queue_out.put(
                publish_msg(
                    common.COMMON_MSG["USER_TTL_INVALID"], tid, msg.data.topic)
            )
            continue

        if tokens_left <= 0:
            queue_out.put(
                publish_msg(
                    common.COMMON_MSG["USER_TOKEN_INVALID"], tid, msg.data.topic)
            )
            continue

        msg_str = msg.data.content.decode('utf-8').strip('"')
        if msg_str not in common.CTRL_KEYS:
            tokens_left -= 1
            db_instance.save_tokens_left(
                bot_name, msg.data.from_user_id, tokens_left)

        logging.info("%s: User %s is valid", bot_name, msg.data.from_user_id)

        if msg.data.from_user_id in friends:
            chat_persona = friends[msg.data.from_user_id]
        else:
            chat_persona = CreatePersona(
                persona=persona,
                bot_name=bot_name,
                from_user_id=msg.data.from_user_id,
                topic=msg.data.topic,
                photos=photos_root,
                db_instance=db_instance
            )
            friends[msg.data.from_user_id] = chat_persona

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
                publish_msg(
                    common.COMMON_MSG["INTERNAL_ERROR"], tid, msg.data.topic)
            )
