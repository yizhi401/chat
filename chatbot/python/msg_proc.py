import time
import os
import random
from multiprocessing import Process, Queue, Lock
import model_pb2 as pb
import model_pb2_grpc as pbx
from persona.persona import Persona, CreatePersona

friends: dict[str, Persona] = {}


def note_read(topic, seq):
    return pb.ClientMsg(note=pb.ClientNote(topic=topic, what=pb.READ, seq_id=seq))


def typing_reply(topic):
    return pb.ClientMsg(note=pb.ClientNote(topic=topic, what=pb.KP))


def process_chat(queue_in,
                 queue_out,
                 persona,
                 photos_root,
                 ):
    while True:
        msg = queue_in.get()
        if msg == None:
            return

        # Respond to message.
        # Mark received message as read.
        queue_out.put(note_read(msg.data.topic, msg.data.seq_id))
        # Notify user that we are responding.
        queue_out.put(typing_reply(msg.data.topic))
        # # Insert a small delay to prevent accidental DoS self-attack.
        time.sleep(0.1)

        if msg.data.from_user_id in friends:
            chat_persona = friends[msg.data.from_user_id]
        else:
            chat_persona = CreatePersona(
                persona, msg.data.topic, photos_root)
            friends[msg.data.from_user_id] = chat_persona

        # Respond with with chat persona for this topic.
        queue_out.put(chat_persona.publish_msg(msg.data.content))
