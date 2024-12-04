from .base import CommandBot, CommandArg
from ..context import JoinContext
from ..bot import BotMeta

import os
import logging
from aiohttp import ClientSession


log = logging.getLogger(__name__)


def get_obj(data, key, cls, default=None):
    return default if (value := data.get(key)) is None else cls(value)


class MWSenseCalledAlso:
    __slots__ = ("intro", "cats")

    def __init__(self, data):
        self.intro: str | None = data.get("intro")
        self.cats: list | None = data.get("cats")


class MWSenseBiographicalName:
    __slots__ = ("pname", "sname", "altname", "prs")

    def __init__(self, data):
        self.pname: str | None = data.get("pname")
        self.sname: str | None = data.get("sname")
        self.altname: str | None = data.get("altname")
        self.prs: list | None = data.get("prs")


class MWSenseDefinitionText:
    __slots__ = ("content",)

    def __init__(self, data):
        self.content: str = data


class MWSenseRunIn:
    __slots__ = ("items",)

    def __init__(self, data):
        self.items: list = data


class MWSenseSupplementalInfo:
    __slots__ = ("items",)

    def __init__(self, data):
        self.items: list = data


class MWSenseUsage:
    __slots__ = ("items",)

    def __init__(self, data):
        self.items: list = data


class MWSenseVerbalIllustration:
    __slots__ = ("items",)

    def __init__(self, data):
        self.items: list = data


SENSE_DEF_CONTENTS = (
    MWSenseDefinitionText |
    MWSenseBiographicalName |
    MWSenseCalledAlso |
    MWSenseRunIn |
    MWSenseSupplementalInfo |
    MWSenseUsage |
    MWSenseVerbalIllustration
)


class MWSenseDefinition:
    __slots__ = ("items",)

    def __init__(self, data):
        self.items: list[SENSE_DEF_CONTENTS] = list(map(self.parse_content_item, data))

    @staticmethod
    def parse_content_item(data) -> SENSE_DEF_CONTENTS:
        return {
            "text": MWSenseDefinitionText,
            "bnw": MWSenseBiographicalName,
            "ca": MWSenseCalledAlso,
            "ri": MWSenseRunIn,
            "snote": MWSenseSupplementalInfo,
            "uns": MWSenseUsage,
            "vis": MWSenseVerbalIllustration
        }[data[0]](data[1])


class MWSense:
    __slots__ = (
        "etymology",
        "inflections",
        "labels",
        "pronunciations",
        "divided_sense",
        "grammatical_label",
        "status_labels",
        "sense_number",
        "variants",
        "definition",
        "sense_divider"
    )

    def __init__(self, data):
        self.etymology: list | None = data.get("et")
        self.inflections: list | None = data.get("ins")
        self.labels: list | None = data.get("lbs")
        self.pronunciations: list | None = data.get("prs")
        self.divided_sense: MWSense | None = get_obj(data, "sdsense", MWSense)
        self.grammatical_label: str | None = data.get("sgram")
        self.status_labels: list | None = data.get("sls")
        self.sense_number: str | None = data.get("sn")
        self.variants: list | None = data.get("vrs")
        self.definition: MWSenseDefinition | None = get_obj(data, "dt", MWSenseDefinition)
        self.sense_divider: str | None = data.get("sd")


class MWBindingSense:
    __slots__ = ("sense",)

    def __init__(self, data):
        self.sense: MWSense = MWSense(data["sense"])


class MWSequenceSense:
    __slots__ = ("senses",)

    def __init__(self, data):
        self.senses: list[MWSense | MWBindingSense | list[MWSense | MWBindingSense]] = list(map(self.parse_sense, data))

    @staticmethod
    def parse_sense(data) -> MWSense | MWBindingSense | list[MWSense | MWBindingSense]:

        return {
            "sense": MWSense,
            "sen": MWSense,
            "pseq": lambda data: [MWSense(elm[1]) if elm[0] == "sense" else MWBindingSense(elm[1]) for elm in data],
            "bs": MWBindingSense
        }[data[0]](data[1])


class MWDefinition:
    __slots__ = ("verb_divider", "sense_sequences")

    def __init__(self, data):
        self.verb_divider: str | None = data.get("vd")
        self.sense_sequences: list[MWSequenceSense] = list(map(MWSequenceSense, data.get("sseq", [])))


class MWBot(CommandBot, metaclass=BotMeta):
    __slots__ = ("mw_cache",)

    MWD_API_KEY = os.getenv("MWD_API_KEY")
    MWT_API_KEY = os.getenv("MWT_API_KEY")

    command_manager = CommandBot.command_manager

    def __init__(self):
        self.mw_cache = {"dictionary": {}, "thesaurus": {}, "args": {}}

    async def make_mw_req(self, endpoint, dictionary=True):
        cache = self.mw_cache["dictionary" if dictionary else "thesaurus"]
        if (value := cache.get(endpoint.lower(), None)) is not None:
            return value

        base, key = ("collegiate", self.MWD_API_KEY) if dictionary else ("thesaurus", self.MWT_API_KEY)
        async with ClientSession() as session:
            async with session.get(f"https://www.dictionaryapi.com/api/v3/references/{base}/json/{endpoint}?key={key}") as resp:
                if resp.status == 200:
                    cache[endpoint.lower()] = (data := await resp.json())
                    return data

                log.error(f"mw returned {resp.status}: {await resp.text()}")

    async def on_join(self, ctx: JoinContext):
        self.mw_cache["args"][ctx.channel] = {"word": "", "index": 1}

    @staticmethod
    def parse_mw_text(text):
        def parse_mark(mark):
            for m in ("a_link", "d_link", "i_link", "et_link", "mat", "sx", "dxt"):
                if mark.startswith(m):
                    return mark.split("|")[1]
            return {
                "bc": ":"
            }.get(mark, "")

        while "{" in text:
            start = text.index("{")
            end = text.index("}")
            text = text[:start] + parse_mark(text[start + 1:end]) + text[end + 1:]
        return text

    async def parse_mw_args(self, ctx, dictionary=True):
        args = ctx.get_args()
        last_args = self.mw_cache["args"][ctx.channel] or {}

        index = self.process_value_arg("-i", args, last_args["index"])
        if type(index) == str and not index.isdigit():
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Index must be an integer")

        if len(args) == 0 and len(last_args["word"]) == 0:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} Specify a word to lookup")
        elif len(args) != 0 and type(index) == int:
            # default to index 1 when word is specified but not index
            index = 1

        word = " ".join(args) or last_args["word"]
        index = int(index)
        data = await self.make_mw_req(word, dictionary=dictionary)

        if data is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Something went wrong when communicating with the Merriam-Webster api"
            )

        if len(data) == 0:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} that word does not exist in the Merriam-Webster collegiate dictionary"
            )

        if type(data[0]) == str:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Could not find that word. Did you mean one of these words: {', '.join(data)}"
            )

        if index not in range(1, len(data) + 1):
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} Index must be between 1 and {len(data)}"
            )

        self.mw_cache["args"][ctx.channel]["word"] = word
        self.mw_cache["args"][ctx.channel]["index"] = index

        return data[index - 1], index, len(data)

    @staticmethod
    def parse_definition(data) -> str | None:
        if (definition := data.get("def", None)) is None:
            return

        definition = MWDefinition(definition[0])

        def get_text(definition):
            return next(filter(lambda item: isinstance(item, MWSenseDefinitionText), definition.items)).content

        seq = definition.sense_sequences[0]
        sense = seq.senses[0]
        if isinstance(sense, MWBindingSense):
            sense = sense.sense
        if isinstance(sense, MWSense):
            return get_text(sense.definition)

        text = ""
        for i, sense in enumerate(sense):
            if isinstance(sense, MWBindingSense):
                sense = sense.sense
            if i != 0 and sense.sense_number is not None:
                text += f"{sense.sense_number} "
            text += get_text(sense.definition)

        return text

    @staticmethod
    def parse_example(data):
        if (definition := data.get("def", None)) is None:
            return

        definition = MWDefinition(definition[0])

        def find_example(sense):
            if isinstance(sense, MWBindingSense):
                sense = sense.sense

            if sense.definition is not None:
                for item in sense.definition.items:
                    if isinstance(item, MWSenseVerbalIllustration):
                        return item.items[0]["t"]

            if sense.divided_sense is not None:
                return find_example(sense.divided_sense)

        # I love MW response format!!!!!
        for seq in definition.sense_sequences:
            for sense in seq.senses:
                if isinstance(sense, MWSense):
                    sense = [sense]
                for sense in sense:
                    example = find_example(sense)
                    if example is not None:
                        return example

    @command_manager.command(
        "define",
        "Get the definition of a word from Merriam Webster dictionary",
        [
            CommandArg("word", is_optional=True)
        ],
        aliases=["def"]
    )
    async def define_word(self, ctx):
        ret = await self.parse_mw_args(ctx)
        if not isinstance(ret, tuple):
            return
        data, index, length = ret

        word = data["meta"]["id"].split(":")[0]
        definition = self.parse_definition(data)
        if definition is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} ({index}/{length}) {word} :No definition available for this index"
            )

        fl = data["fl"]
        date = data.get("date")
        date = f" | from {self.parse_mw_text(date)}" if date is not None else ""

        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} ({index}/{length}) {word} [{fl}] {self.parse_mw_text(definition)}{date}"
        )

    @command_manager.command(
        "example",
        "Get an example sentence for a word from Merriam Webster dictionary.",
        [
            CommandArg("word", is_optional=True)
        ]
    )
    async def example_word(self, ctx):
        ret = await self.parse_mw_args(ctx)
        if type(ret) != tuple:
            return
        data, index, length = ret

        word = data["meta"]["id"].split(":")[0]
        example = self.parse_example(data)
        if example is None:
            return await self.send_message(
                ctx.channel,
                f"@{ctx.user.display_name} ({index}/{length}) {word} :No example available for this index"
            )

        fl = data["fl"]
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} ({index}/{length}) {word} [{fl}] {self.parse_mw_text(example)}"
        )

    @command_manager.command(
        "synonyms",
        "Get the synonyms for a word from Merriam Webster dictionary",
        [
            CommandArg("word", is_optional=True)
        ]
    )
    async def synonyms_word(self, ctx):
        ret = await self.parse_mw_args(ctx, dictionary=False)
        if type(ret) != tuple:
            return
        data, index, length = ret

        word = data["meta"]["id"].split(":")[0]
        fl = data["fl"]
        syns = sum(data["meta"]["syns"], [])[:20]
        if len(syns) == 0:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} this word has no synonym entries")
        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} ({index}/{length}) {word} [{fl}]: {', '.join(syns)}"
        )

    @command_manager.command(
        "antonyms",
        "Get the antonyms for a word from Merriam Webster dictionary",
        [
            CommandArg("word", is_optional=True)
        ]
    )
    async def antonyms_word(self, ctx):
        ret = await self.parse_mw_args(ctx, dictionary=False)
        if not isinstance(ret, tuple):
            return
        data, index, length = ret

        if isinstance(data, str):
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} this word has no antonym entries")

        word = data["meta"]["id"].split(":")[0]
        fl = data["fl"]
        ants = sum(data["meta"]["ants"], [])[:20]
        if len(ants) == 0:
            return await self.send_message(ctx.channel, f"@{ctx.user.display_name} this word has no antonym entries")

        await self.send_message(
            ctx.channel,
            f"@{ctx.user.display_name} ({index}/{length}) {word} [{fl}]: {', '.join(ants)}"
        )
