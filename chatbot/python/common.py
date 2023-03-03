import pkg_resources

# Maximum allowed linear dimension of an inline image in pixels.
MAX_IMAGE_DIM = 768
MAX_HISTORY_DATA = 20

COMMON_MSG = {
    "USER_INVALID": "您的费用已耗尽，请充值！",
    "INTERNAL_ERROR": "现在我的脑袋有点乱，让我再好好想想...",
}

APP_NAME = "Tino-chatbot"
APP_VERSION = "1.2.2"
LIB_VERSION = pkg_resources.get_distribution("tinode_grpc").version

# Maximum length of string to log. Shorten longer strings.
MAX_LOG_LEN = 64
