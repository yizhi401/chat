import argparse
import pathlib
import os
import utils
import logging
import datetime
from chatbot import ChatBot


def run(args):
    chatBot = ChatBot(args.persona, args.photos_root)
    chatBot.run(args)


def init():
    # This is needed for gRPC ssl to work correctly.
    os.environ["GRPC_SSL_CIPHER_SUITES"] = "HIGH+ECDSA"
    utils.config_logging()


def main():
    """Parse command-line arguments. Extract server host name, listen address, authentication scheme"""

    init()

    purpose = "Tino, Tinode's chatbot."
    logging.info(purpose)
    parser = argparse.ArgumentParser(description=purpose)
    parser.add_argument(
        "--host",
        default="localhost:16060",
        help="address of Tinode server gRPC endpoint",
    )
    parser.add_argument(
        "--ssl", action="store_true", help="use SSL to connect to the server"
    )
    parser.add_argument(
        "--ssl-host",
        help="SSL host name to use instead of default (useful for connecting to localhost)",
    )
    parser.add_argument(
        "--listen",
        default="0.0.0.0:40051",
        help="address to listen on for incoming Plugin API calls",
    )
    parser.add_argument(
        "--login-basic", help="login using basic authentication username:password"
    )
    parser.add_argument("--login-token", help="login using token authentication")
    parser.add_argument(
        "--login-cookie",
        default=".tn-cookie",
        help="read credentials from the provided cookie file",
    )
    parser.add_argument(
        "--persona", default="writer", help="Persona type for this chatbot."
    )
    parser.add_argument(
        "--photos_root",
        default="photos",
        type=pathlib.Path,
        help="root directory for storing aigirls' photos",
    )
    args = parser.parse_args()

    run(args)


if __name__ == "__main__":
    main()
