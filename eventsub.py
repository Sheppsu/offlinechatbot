import websockets
import asyncio
from datetime import datetime
from enum import Enum


class EventSubMessageType(Enum):
    WELCOME = "session_welcome"
    KEEPALIVE = "session_keepalive"
    NOTIFICATION = "notification"
    RECONNECT = "session_reconnect"
    REVOCATION = "revocation"


class EventSubSubscriptionType(Enum):
    AUTOMOD_MESSAGE_HOLD = "automod.message.hold"
    AUTOMOD_MESSAGE_UPDATE = "automod.message.update"
    AUTOMOD_SETTINGS_UPDATE = "automod.settings.update"
    AUTOMOD_TERMS_UPDATE = "automod.terms.update"
    CHANNEL_BITS_USE = "channel.bits.use"
    CHANNEL_UPDATE = "channel.update"
    CHANNEL_FOLLOW = "channel.follow"
    CHANNEL_AD_BREAK_BEGIN = "channel.ad_break.begin"
    CHANNEL_CHAT_CLEAR = "channel.chat.clear"
    CHANNEL_CHAT_CLEAR_USER_MESSAGES = "channel.chat.clear_user_messages"
    CHANNEL_CHAT_MESSAGE = "channel.chat.message"
    CHANNEL_CHAT_MESSAGE_DELETE = "channel.chat.message_delete"
    CHANNEL_CHAT_NOTIFICATION = "channel.chat.notification"
    CHANNEL_CHAT_SETTINGS_UPDATE = "channel.chat_settings.update"
    CHANNEL_CHAT_USER_MESSAGE_HOLD = "channel.chat.user_message_hold"
    CHANNEL_CHAT_USER_MESSAGE_UPDATE = "channel.chat.user_message_update"
    CHANNEL_SHARED_CHAT_SESSION_BEGIN = "channel.shared_chat.begin"
    CHANNEL_SHARED_CHAT_SESSION_UPDATE = "channel.shared_chat.update"
    CHANNEL_SHARED_CHAT_SESSION_END = "channel.shared_chat.end"
    CHANNEL_SUBSCRIBE = "channel.subscribe"
    CHANNEL_SUBSCRIPTION_END = "channel.subscription.end"
    CHANNEL_SUBSCRIPTION_GIFT = "channel.subscription.gift"
    CHANNEL_SUBSCRIPTION_MESSAGE = "channel.subscription.message"
    CHANNEL_CHEER = "channel.cheer"
    CHANNEL_RAID = "channel.raid"
    CHANNEL_BAN = "channel.ban"
    CHANNEL_UNBAN = "channel.unban"
    CHANNEL_UNBAN_REQUEST_CREATE = "channel.unban_request.create"
    CHANNEL_UNBAN_REQUEST_RESOLVE = "channel.unban_request.resolve"
    CHANNEL_MODERATE = "channel.moderate"
    CHANNEL_MODERATOR_ADD = "channel.moderator.add"
    CHANNEL_MODERATOR_REMOVE = "channel.moderator.remove"
    CHANNEL_GUEST_STAR_SESSION_BEGIN = "channel.guest_star_session.begin"
    CHANNEL_GUEST_STAR_SESSION_END = "channel.guest_star_session.end"
    CHANNEL_GUEST_STAR_SESSION_UPDATE = "channel.guest_star_session.update"
    CHANNEL_GUEST_STAR_SETTINGS_UPDATE = "channel.guest_star_settings.update"
    CHANNEL_POINTS_AUTO_REWARD_REDEMPTION_ADD = "channel.channel_points_automatic_reward_redemption.add"
    CHANNEL_POINTS_CUSTOM_REWARD_ADD = "channel.channel_points_custom_reward.add"
    CHANNEL_POINTS_CUSTOM_REWARD_UPDATE = "channel.channel_points_custom_reward.update"
    CHANNEL_POINTS_CUSTOM_REWARD_REMOVE = "channel.channel_points_custom_reward.remove"
    CHANNEL_POINTS_CUSTOM_REWARD_REDEMPTION_ADD = "channel.channel_points_custom_reward_redemption.add"
    CHANNEL_POINTS_CUSTOM_REWARD_REDEMPTION_UPDATE = "channel.channel_points_custom_reward_redemption.update"
    CHANNEL_POLL_BEGIN = "channel.poll.begin"
    CHANNEL_POLL_PROGRESS = "channel.poll.progress"
    CHANNEL_POLL_END = "channel.poll.end"
    CHANNEL_PREDICTION_BEGIN = "channel.prediction.begin"
    CHANNEL_PREDICTION_PROGRESS = "channel.prediction.progress"
    CHANNEL_PREDICTION_LOCK = "channel.prediction.lock"
    CHANNEL_PREDICTION_END = "channel.prediction.end"
    CHANNEL_SUSPICIOUS_USER_MESSAGE = "channel.suspicious_user.message"
    CHANNEL_SUSPICIOUS_USER_UPDATE = "channel.suspicious_user.update"
    CHANNEL_VIP_ADD = "channel.vip.add"
    CHANNEL_VIP_REMOVE = "channel.vip.remove"
    CHANNEL_WARNING_ACK = "channel.warning.acknowledge"
    CHANNEL_WARNING_SEND = "channel.warning.send"
    CHARITY_DONATION = "channel.charity_campaign.donate"
    CHARITY_CAMPAIGN_START = "channel.charity_campaign.start"
    CHARITY_CAMPAIGN_PROGRESS = "channel.charity_campaign.progress"
    CHARITY_CAMPAIGN_STOP = "channel.charity_campaign.stop"
    CONDUIT_SHARD_DISABLED = "conduit.shard.disabled"
    DROP_ENTITLEMENT_GRANT = "drop.entitlement.grant"
    EXTENSION_BITS_TRANSACTION_CREATE = "extension.bits_transaction.create"
    GOAL_BEGIN = "channel.goal.begin"
    GOAL_PROGRESS = "channel.goal.progress"
    GOAL_END = "channel.goal.end"
    HYPE_TRAIN_BEGIN = "channel.hype_train.begin"
    HYPE_TRAIN_PROGRESS = "channel.hype_train.progress"
    HYPE_TRAIN_END = "channel.hype_train.end"
    SHIELD_MODE_BEGIN = "channel.shield_mode.begin"
    SHIELD_MODE_END = "channel.shield_mode.end"
    SHOUTOUT_CREATE = "channel.shoutout.create"
    SHOUTOUT_RECEIVED = "channel.shoutout.received"
    STREAM_ONLINE = "stream.online"
    STREAM_OFFLINE = "stream.offline"
    USER_AUTH_GRANT = "user.authorization.grant"
    USER_AUTH_REVOKE = "user.authorization.revoke"
    USER_UPDATE = "user.update"
    WHISPER_RECEIVED = "user.whisper.message"


class SessionStatus(Enum):
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class SubscriptionStatus(Enum):
    ENABLED = "enabled"
    AUTH_REVOKED = "authorization_revoked"
    USER_REMOVED = "user_removed"
    VERSION_REMOVED = "version_removed"


class EventSubMetadata:
    __slots__ = ("id", "type", "timestamp")

    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.type: str = data["type"]
        self.timestamp: datetime = datetime.fromisoformat(data["timestamp"])


class EventSubMetadataExt(EventSubMetadata):
    __slots__ = ("subscription_type", "subscription_version")

    def __init__(self, data: dict):
        super().__init__(data)

        self.subscription_type: EventSubSubscriptionType = EventSubSubscriptionType(data["subscription_type"])
        self.subscription_version: str = data["subscription_version"]


class EventSubSession:
    __slots__ = ("id", "status", "connected_at", "keepalive_timeout_seconds", "reconnect_url")

    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.status: SessionStatus = SessionStatus(data["status"])
        self.connected_at: datetime = datetime.fromisoformat(data["connected_at"])
        self.keepalive_timeout_seconds: int = data["keepalive_timeout_seconds"]
        self.reconnect_url: str = data["reconnect_url"]


class EventSubSubscription:
    __slots__ = ("id", "status", "type", "version", "cost", "condition", "transport", "created_at", "event")

    def __init__(self, data: dict):
        self.id: str = data["id"]
        self.status: SubscriptionStatus = SubscriptionStatus(data["status"])
        self.type: EventSubSubscriptionType = EventSubSubscriptionType(data["type"])
        self.version: str = data["version"]
        self.cost: int = data["cost"]
        self.condition: dict = data["condition"]
        self.transport: dict = data["transport"]
        self.created_at: datetime = datetime.fromisoformat(data["created_at"])


# Websocket messages

class EventSubWelcomeMessage:
    __slots__ = ("metadata", "session")

    def __init__(self, data: dict):
        self.metadata: EventSubMetadata = EventSubMetadata(data)
        self.session: EventSubSession = EventSubSession(data["payload"]["session"])


class EventSubKeepaliveMessage:
    __slots__ = ("metadata",)

    def __init__(self, data: dict):
        self.metadata: EventSubMetadata = EventSubMetadata(data)


class EventSubNotificationMessage:
    __slots__ = ("metadata", "subscription", "event")

    def __init__(self, data: dict):
        self.metadata: EventSubMetadataExt = EventSubMetadataExt(data)
        payload = data["payload"]
        self.subscription: EventSubSubscription = EventSubSubscription(payload["subscription"])
        self.event: dict = payload["event"]


class EventSubReconnectMessage:
    __slots__ = ("metadata", "session")

    def __init__(self, data: dict):
        self.metadata: EventSubMetadata = EventSubMetadata(data)
        self.session: EventSubSession = EventSubSession(data["payload"]["session"])


class EventSubRevocationMessage:
    __slots__ = ("metadata", "subscription")

    def __init__(self, data: dict):
        self.metadata: EventSubMetadataExt = EventSubMetadataExt(data)
        self.subscription: EventSubSubscription = EventSubSubscription(data["payload"]["subscription"])


def parse_eventsub_msg(data):
    return {
        EventSubMessageType.WELCOME: EventSubWelcomeMessage,
        EventSubMessageType.KEEPALIVE: EventSubKeepaliveMessage,
        EventSubMessageType.RECONNECT: EventSubReconnectMessage,
        EventSubMessageType.NOTIFICATION: EventSubNotificationMessage,
        EventSubMessageType.REVOCATION: EventSubRevocationMessage
    }[EventSubMessageType(data["metadata"]["message_type"])](data)


class EventSubCommunicator:
    def __init__(self):
        self.ws = None

    async def connect(self):
        async with websockets.connect('wss://eventsub.wss.twitch.tv/ws') as ws:
            self.ws = ws


if __name__ == "__main__":
    comm = EventSubCommunicator()
    asyncio.run(comm.connect())
