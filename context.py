from enum import Enum
from datetime import datetime
import pytz


class ContextType(Enum):
    PRIVMSG = "PRIVMSG"
    JOIN = "JOIN"
    PART = "PART"
    USERSTATE = "USERSTATE"
    ROOMSTATE = "ROOMSTATE"
    CONNECTED = "376"


class Context:
    type = None  # So IDE will shut up about no attribute type

    def __new__(cls, string):
        contexts = []
        for string in string.split("\r\n"):
            data = string.split()
            if len(data) < 3:
                continue
            tags = None
            if data[0].startswith("@"):
                tags = Context.parse_tags_string(data[0])
            offset = 1 if tags is not None else 0
            source = data[0 + offset]
            try:
                message_type = ContextType(data[1 + offset])
            except ValueError:
                contexts.append(UnknownContext(source, data[1 + offset]))
                continue
            channel = data[2 + offset][1:]
            if message_type == ContextType.PRIVMSG:
                message = " ".join(data[3 + offset:])[1:]
                sending_user = source.split("!")[0][1:]
                action = False
                if message.startswith("\x01"):
                    message = message[7:-1]
                    action = True
                contexts.append(MessageContext(sending_user, channel, message, tags, source, action))
            elif message_type == ContextType.JOIN:
                contexts.append(JoinContext(channel, source))
            elif message_type == ContextType.PART:
                contexts.append(PartContext(channel, source))
            elif message_type == ContextType.USERSTATE:
                contexts.append(UserStateContext(source, channel, tags))
            elif message_type == ContextType.ROOMSTATE:
                contexts.append(RoomStateContext(source, channel, tags))
            else:
                contexts.append(UnknownContext(source, message_type))
        return contexts

    @staticmethod
    def parse_tags_string(string):
        return {tag.split("=")[0]: tag.split("=")[1] for tag in string[1:].split(";")}


class JoinContext:
    __slots__ = (
        "channel", "source",
    )
    type = ContextType.JOIN

    def __init__(self, channel, source):
        self.channel = channel
        self.source = source


class PartContext:
    __slots__ = ("channel", "source")
    type = ContextType.PART

    def __init__(self, channel, source):
        self.channel = channel
        self.source = source


class MessageContext:
    __slots__ = (
        "tags", "source", "message_type", "channel", "message", "user", "action", "time_created",
        "emotes", "first_msg", "flags", "id", "returning_chatter", "room_id", "tmi_sent_ts",
        "turbo", "user_id", "user_type", "sending_user"
    )
    type = ContextType.PRIVMSG

    def __init__(self, sending_user="", channel="", message="", tags=None, source=None, action=False):
        self.user = UserStateContext(source, channel, tags) if tags is not None else sending_user
        self.sending_user = sending_user
        self.channel = channel
        self.message = message
        self.source = source
        self.action = action
        self.time_created = datetime.now().replace(tzinfo=pytz.UTC)

        if tags is None:
            return
        self.emotes = tags.get("emotes", [])
        self.first_msg = bool(int(tags.get("first-msg", 0)))
        self.flags = tags.get("flags", [])
        self.id = tags.get("id", None)
        self.returning_chatter = bool(int(tags.get("returning-chatter", 0)))
        self.room_id = tags.get("room-id", None)
        self.tmi_sent_ts = bool(int(tags.get("tmi-sent-ts", 0)))
        self.turbo = bool(int(tags.get("turbo", 0)))
        self.user_id = tags.get("user-id", None)
        self.user_type = tags.get("user-type", None)

    def get_args(self, char_acceptance="unicode"):
        if char_acceptance.lower() == "ascii":
            message = "".join(char for char in self.message if char.isascii())
        elif char_acceptance.lower() == "unicode":
            message = self.message
        else:
            raise ValueError("char_acceptance must be either 'ascii' or 'unicode'")
        return message.split()[1:]

    def split_ats(self):
        msg = [[]]
        for word in self.message.split():
            if word.startswith("@"):
                msg += [[word], []]
                continue
            msg[-1].append(word)
        return list(map(" ".join, msg))


class RoomStateContext:
    __slots__ = (
        "source", "channel", "emote_only", "followers_only", "r9k", "room_id",
        "slow", "subs_only"
    )
    type = ContextType.ROOMSTATE

    def __init__(self, source, channel, tags):
        self.source = source
        self.channel = channel
        if tags is None:
            return
        self.emote_only = bool(int(tags.get("emote-only", 0)))
        self.followers_only = bool(int(tags.get("followers-only", 0)))
        self.r9k = bool(int(tags.get("r9k", 0)))
        self.room_id = tags.get("room-id")
        self.slow = bool(int(tags.get("slow", 0)))
        self.subs_only = bool(int(tags.get("subs-only", 0)))


class UserStateContext:
    __slots__ = (
        "source", "username", "channel", "badge_info", "badges", "color",
        "display_name", "emote_sets", "mod", "subscriber", "user_type",
    )
    type = ContextType.USERSTATE

    def __init__(self, source, channel, tags):
        self.source = source
        self.username = None
        if "!" in source:
            self.username = source.split("!")[0][1:]
        self.channel = channel
        if tags is None:
            return
        self.badge_info = tags.get("badge-info")
        self.badges = tags.get("badges", "").split(",")
        self.badges = list(map(ContextBadge, [] if self.badges[0] == "" else self.badges))
        self.color = tags.get("color", "#FFFFFF")
        self.display_name = tags.get("display-name")
        self.emote_sets = tags.get("emote-sets")
        self.mod = bool(int(tags.get("mod", 0)))
        self.subscriber = bool(int(tags.get("subscriber", 0)))
        self.user_type = tags.get("user-type")


class ContextBadge:
    __slots__ = ("set_id", "extra", "is_sub_badge")

    def __init__(self, data):
        self.set_id, self.extra = data.split("/")
        self.is_sub_badge = self.set_id == "subscriber"


class UnknownContext:
    __slots__ = ("source", "type")

    def __init__(self, source, msg_type):
        self.source = source
        self.type = msg_type
