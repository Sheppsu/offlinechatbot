from enum import Enum, IntEnum


class NSFW(Enum):
    WHITE = "white"
    GRAY = "gray"
    BLACK = "black"


class MediaType(IntEnum):
    UNKNOWN = 0
    TV = 1
    OVA = 2
    MOVIE = 3
    SPECIAL = 4
    ONA = 5
    MUSIC = 6


class Status(IntEnum):
    FINISHED_AIRING = 0
    CURRENTLY_AIRING = 1
    NOT_YET_AIRED = 2


class Source(IntEnum):
    OTHER = 0
    ORIGINAL = 1
    MANGA = 2
    FOUR_KOMA_MANGA = 3
    WEB_MANGA = 4
    DIGITAL_MANGA = 5
    NOVEL = 6
    LIGHT_NOVEL = 7
    VISUAL_NOVEL = 8
    GAME = 9
    CARD_GAME = 10
    BOOK = 11
    PICTURE_BOOK = 12
    RADIO = 13
    MUSIC = 14


class Rating(Enum):
    G = "g"
    PG = "pg"
    PG_13 = "pg_13"
    R = "r"
    R_PLUS = "r+"
    RX = "rx"
