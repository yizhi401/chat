"""Python implementation of a Tinode chatbot."""

# For compatibility between python 2 and 3
from __future__ import print_function

import argparse
import traceback
import pathlib
import base64
from concurrent import futures
from datetime import datetime
import json
import logging
import platform
import signal
import sys
import time
import utils
import common

import grpc

# Import generated grpc modules
import model_pb2 as pb
import model_pb2_grpc as pbx
from msg_proc import process_chat
import multiprocessing
import queue


class ChatBot:
    def __init__(self, persona: str, photos_root: pathlib.Path) -> None:
        # User ID of the current user
        self.botUID = None
        # Dictionary wich contains lambdas to be executed when server response is received
        self.onCompletion = {}
        self.persona = persona
        self.photos_root = photos_root

        # List of active subscriptions
        self.subscriptions = {}
        # Keep grpc channel from being collected.
        self.channel = None
        self.client = None

        self.retry_time = 0

        # Message Queue
        self.queue_out = multiprocessing.Queue()

        self.tid = 100
        self.login_basic = ""

    def next_id(self) -> str:
        self.tid += 1
        return str(self.tid)

    def add_future(self, tid, bundle):
        # Add bundle for future execution
        self.onCompletion[tid] = bundle

    # Resolve or reject the future
    def exec_future(self, tid, code, text, params):
        bundle = self.onCompletion.get(tid)
        if bundle != None:
            del self.onCompletion[tid]
            try:
                if code >= 200 and code < 400:
                    arg = bundle.get("arg")
                    bundle.get("onsuccess")(arg, params)
                else:
                    logging.error("Error: {} {} ({})".format(code, text, tid))
                    onerror = bundle.get("onerror")
                    if onerror:
                        onerror(bundle.get("arg"), {
                                "code": code, "text": text})
            except Exception as err:
                logging.error("Error handling server response", err)

    def add_subscription(self, topic):
        self.subscriptions[topic] = True

    def del_subscription(self, topic):
        self.subscriptions.pop(topic, None)

    def subscription_failed(self, topic, errcode):
        if topic == "me":
            # Failed 'me' subscription means the bot is disfunctional.
            if errcode.get("code") == 502:
                # Cluster unreachable. Break the loop and retry in a few seconds.
                self.client_post(None)
            else:
                exit(1)

    def client_generate(self):
        while True:
            try:
                # If we cannot get any message from queue in 10 mins
                # exit the current queue, causing the client to reconnect.
                msg = self.queue_out.get(timeout=60)
                if msg == None:
                    logging.warn("Msg Is None.")
                    if self.client != None:
                        self.client.cancel()
                    return
                logging.debug("out: %s", utils.to_json(msg))
                # Clear retry time.
                self.retry_time = 0
                yield msg
            except queue.Empty as e:
                logging.error(traceback.format_exc())
                logging.error(e)
                state = self.channel._channel.check_connectivity_state(False)
                logging.debug("Channel state:%s", state)
                if state != grpc.ChannelConnectivity.READY.value[0]:
                    logging.error("Grpc Channel is not ready. Exiting...")
                    if self.client != None:
                        logging.info("Canncel grpc client...")
                        self.client.cancel()
                    return
                logging.debug("Retry times: %s", self.retry_time)
                if self.retry_time > 5:
                    logging.warn("Too many retries. Exiting...")
                    if self.client != None:
                        logging.info("Canncel grpc client...")
                        self.client.cancel()
                    return
                else:
                    self.retry_time += 1
            except Exception as e:
                logging.error(traceback.format_exc())
                logging.error(e)
                if self.client != None:
                    logging.info("Canncel grpc client...")
                    self.client.cancel()
                return

    def client_post(self, msg):
        self.queue_out.put(msg)

    def client_reset(self):
        # Drain the queue
        try:
            logging.info("Draining the out queue...")
            while self.queue_out.get(False) != None:
                pass
        except Exception as e:
            logging.error(traceback.format_exc())
            logging.error(e)

        try:
            logging.info("Closing the queue...")
            self.queue_out.close()
            logging.info("Clearing the processors...")
        except Exception as e:
            logging.error(traceback.format_exc())
            logging.error(e)
        # logging.info("Clearing the subscriptions...")
        # self.subscriptions.clear()

    def hello(self):
        tid = self.next_id()
        self.add_future(
            tid,
            {
                "onsuccess": lambda unused, params: server_version(params),
            },
        )
        return pb.ClientMsg(
            hi=pb.ClientHi(
                id=tid,
                user_agent=common.APP_NAME
                + "/"
                + common.APP_VERSION
                + " ("
                + platform.system()
                + "/"
                + platform.release()
                + "); gRPC-python/"
                + common.LIB_VERSION,
                ver=common.LIB_VERSION,
                lang="EN",
            )
        )

    def login(self, cookie_file_name, scheme, secret):
        tid = self.next_id()
        self.add_future(
            tid,
            {
                "arg": cookie_file_name,
                "onsuccess": lambda fname, params: self.on_login(fname, params),
                "onerror": lambda unused, errcode: login_error(unused, errcode),
            },
        )
        return pb.ClientMsg(login=pb.ClientLogin(id=tid, scheme=scheme, secret=secret))

    def subscribe(self, topic, add_to_future=True):
        tid = self.next_id()
        if add_to_future:
            self.add_future(
                tid,
                {
                    "arg": topic,
                    "onsuccess": lambda topicName, unused: self.add_subscription(
                        topicName
                    ),
                    "onerror": lambda topicName, errcode: self.subscription_failed(
                        topicName, errcode
                    ),
                },
            )
        return pb.ClientMsg(sub=pb.ClientSub(id=tid, topic=topic))

    def leave(self, topic):
        tid = self.next_id()
        self.add_future(
            tid,
            {
                "arg": topic,
                "onsuccess": lambda topicName, unused: self.del_subscription(topicName),
            },
        )
        return pb.ClientMsg(leave=pb.ClientLeave(id=tid, topic=topic))

    def publish(self, topic, text):
        tid = self.next_id()
        return pb.ClientMsg(
            pub=pb.ClientPub(
                id=tid,
                topic=topic,
                no_echo=True,
                head={"auto": json.dumps(True).encode("utf-8")},
                content=json.dumps(text).encode("utf-8"),
            )
        )

    def init_client(self, addr, schema, secret, cookie_file_name, secure, ssl_host):
        logging.info(
            "Connecting to %s %s %s %s",
            "secure" if secure else "",
            "server at",
            addr,
            "SNI=" + ssl_host if ssl_host else "",
        )

        self.channel = None
        if secure:
            opts = (("grpc.ssl_target_name_override",
                    ssl_host),) if ssl_host else None
            self.channel = grpc.secure_channel(
                addr, grpc.ssl_channel_credentials(), opts
            )
        else:
            channel_options = [
                ('grpc.keepalive_time_ms', 60000),  # 1 minute
                ('grpc.keepalive_timeout_ms', 10000),  # 10 seconds
                ('grpc.keepalive_permit_without_calls', 1),  # enabled
            ]
            self.channel = grpc.insecure_channel(addr, channel_options)

        self.channel.subscribe(self.channel_callback)

        self.queue_out = multiprocessing.Queue()
        # Call the server
        stream = pbx.NodeStub(self.channel).MessageLoop(self.client_generate())

        # Session initialization sequence: {hi}, {login}, {sub topic='me'}
        self.client_post(self.hello())
        self.client_post(self.login(cookie_file_name, schema, secret))

        return stream

    def process_data_msg(self, msg):
        processor = multiprocessing.Process(
            target=process_chat,
            args=(
                msg,
                self.next_id(),
                self.queue_out,
                self.login_basic,
                self.persona,
                self.photos_root,
            ),
        )
        processor.daemon = True
        processor.start()

    def client_message_loop(self, stream):
        try:
            # Read server responses
            for msg in stream:
                logging.debug("in: %s", utils.to_json(msg))
                if msg.HasField("ctrl"):
                    # Run code on command completion
                    self.exec_future(
                        msg.ctrl.id, msg.ctrl.code, msg.ctrl.text, msg.ctrl.params
                    )

                elif msg.HasField("data"):
                    # Protection against the bot talking to self from another session.
                    if msg.data.from_user_id != self.botUID:
                        self.process_data_msg(msg)
                elif msg.HasField("pres"):
                    # log("presence:", msg.pres.topic, msg.pres.what)
                    # Wait for peers to appear online and subscribe to their topics
                    if msg.pres.topic == "me":
                        if (
                            msg.pres.what == pb.ServerPres.ON
                            or msg.pres.what == pb.ServerPres.MSG
                        ) and self.subscriptions.get(msg.pres.src) == None:
                            self.client_post(self.subscribe(msg.pres.src))
                        elif (
                            msg.pres.what == pb.ServerPres.OFF
                            and self.subscriptions.get(msg.pres.src) != None
                        ):
                            logging.info(
                                "OFF msg received from %s", msg.pres.src)
                            # Chatbot never leave.
                            # self.client_post(self.leave(msg.pres.src))

                else:
                    # Ignore everything else
                    pass
                logging.debug("msg processed: %s", utils.to_json(msg))

        except grpc._channel._Rendezvous as err:
            logging.error("Disconnected: %s", err)

    def on_login(self, cookie_file_name, params):
        self.client_post(self.subscribe("me"))
        # Subscribe post before.
        for topic in self.subscriptions:
            self.client_post(self.subscribe(topic, False))

        """Save authentication token to file"""
        if params == None or cookie_file_name == None:
            return

        if "user" in params:
            self.botUID = params["user"].decode("ascii")

        # Protobuf map 'params' is not a python object or dictionary. Convert it.
        nice = {"schema": "token"}
        for key_in in params:
            if key_in == "token":
                key_out = "secret"
            else:
                key_out = key_in
            nice[key_out] = json.loads(params[key_in].decode("utf-8"))

        try:
            cookie = open(cookie_file_name, "w")
            json.dump(nice, cookie)
            cookie.close()
        except Exception as err:
            logging.error("Failed to save authentication cookie", err)

    def channel_callback(self, channel_connectivity):
        logging.debug("Channel connectivity: %s", channel_connectivity)
        if channel_connectivity == grpc.ChannelConnectivity.READY:
            logging.info("Connected")

    def run(self, args):
        schema = None
        secret = None

        if args.login_token:
            """Use token to login"""
            schema = "token"
            secret = args.login_token.encode("ascii")
            logging.info("Logging in with token: %s", args.login_token)

        elif args.login_basic:
            """Use username:password"""
            schema = "basic"
            secret = args.login_basic.encode("utf-8")
            self.login_basic = args.login_basic.split(":")[0]
            logging.info("Logging in with login:password %s", args.login_basic)

        else:
            """Try reading the cookie file"""
            try:
                schema, secret = self.read_auth_cookie(args.login_cookie)
                logging.info("Logging in with cookie file %s",
                             args.login_cookie)
            except Exception as err:
                logging.info("Failed to read authentication cookie %s", err)

        if schema:
            # Load random quotes from file
            # log("Loaded {} quotes".format(load_quotes(args.quotes)))

            # Start Plugin server
            # server = self.init_server(args.listen)

            # Initialize and launch client
            self.client = self.init_client(
                args.host, schema, secret, args.login_cookie, args.ssl, args.ssl_host
            )

            # Setup closure for graceful termination
            def exit_gracefully(signo, stack_frame):
                logging.info("Terminated with signal %s ", signo)
                # server.stop(0)
                self.client.cancel()
                sys.exit(0)

            # Add signal handlers
            signal.signal(signal.SIGINT, exit_gracefully)
            signal.signal(signal.SIGTERM, exit_gracefully)

            # Run blocking message loop in a cycle to handle
            # server being down.
            while True:
                try:
                    self.client_message_loop(self.client)
                except Exception as err:
                    logging.error(traceback.format_exc())
                    logging.error("Error: %s", err)
                logging.error("Disconnected. Reconnecting in 3 seconds...")
                time.sleep(3)
                # Close connections gracefully before exiting
                # server.stop(None)
                logging.info("Resetting client")
                self.client_reset()
                self.client.cancel()
                logging.info("Reconnecting")
                self.client = self.init_client(
                    args.host,
                    schema,
                    secret,
                    args.login_cookie,
                    args.ssl,
                    args.ssl_host,
                )

        else:
            logging.error("Error: authentication scheme not defined")

    def init_server(self, listen):
        # Launch plugin server: accept connection(s) from the Tinode server.
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
        pbx.add_PluginServicer_to_server(Plugin(), server)
        server.add_insecure_port(listen)
        server.start()

        logging.info("Plugin server running at '" + listen + "'")

        return server

    def read_auth_cookie(self, cookie_file_name):
        """Read authentication token from a file"""
        cookie = open(cookie_file_name, "r")
        params = json.load(cookie)
        cookie.close()
        schema = params.get("schema")
        secret = None
        if schema == None:
            return None, None
        if schema == "token":
            secret = base64.b64decode(params.get("secret").encode("utf-8"))
        else:
            secret = params.get("secret").encode("utf-8")
        return schema, secret


def login_error(unused, errcode):
    # Check for 409 "already authenticated".
    if errcode.get("code") != 409:
        logging.info("Login failed: %s", errcode.get("text"))
        exit(1)
    else:
        logging.info("Already authenticated")


def server_version(params):
    if params == None:
        return
    logging.info(
        "Server: %s, %s", params["build"].decode(
            "ascii"), params["ver"].decode("ascii")
    )


class Plugin(pbx.PluginServicer):
    def Account(self, acc_event, context):
        action = None
        if acc_event.action == pb.CREATE:
            action = "created"
            # TODO: subscribe to the new user.

        elif acc_event.action == pb.UPDATE:
            action = "updated"
        elif acc_event.action == pb.DELETE:
            action = "deleted"
        else:
            action = "unknown"

        logging.info("Account", action, ":",
                     acc_event.user_id, acc_event.public)

        return pb.Unused()
