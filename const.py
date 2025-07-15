import logging


class ConstMeta(type):

    def __setattr__(self, name, value):
        if name in self.__dict__:
            raise TypeError(f"Can't rebind const ({name})")
        else:
            self.__setattr__(name, value)


class Const(metaclass=ConstMeta):
    # Slack App OAuth Tokens
    USER_TOKEN = "xoxp-xxxxxx"  # Your User Token
    BOT_TOKEN = "xoxb-xxxxxx"  # Your Bot Token

    # Wait time (sec) for an API call or a file download.
    # If change this value, check the rate limits of Slack APIs.
    # Default wait time for most API calls
    ACCESS_WAIT = 2.0
    # Wait time for conversations.history and conversations.replies
    # Non-Marketplace apps: 1 request/minute (60 seconds)
    CONVERSATIONS_ACCESS_WAIT = 60.0
    # Whether this is a Marketplace app (affects rate limits)
    IS_MARKETPLACE_APP = False
    # Export Directory path.
    EXPORT_BASE_PATH = "./export"
    # Logging level for the logging module.
    LOG_LEVEL = logging.INFO
    # Connect and read timeouts (sec) for the requests module.
    REQUESTS_CONNECT_TIMEOUT = 3.05
    REQUESTS_READ_TIMEOUT = 60
    # Whether or not to use the User Token.
    USE_USER_TOKEN = True
    # Whether or not.to split message files by day.
    # If split, message files are saved in a format similar to official
    # functions.
    SPLIT_MESSAGE_FILES = True
    # Maximum number of retries for rate limit errors.
    # Set to 0 for infinite retries (recommended for complete data export).
    MAX_RATE_LIMIT_RETRIES = 0
