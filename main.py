# coding=utf-8
from dotenv import load_dotenv
load_dotenv()

import random
import websockets
import asyncio
import requests
from time import perf_counter
import html
import json
from datetime import datetime
import traceback
import sys
import os
from get_top_players import Client
from sql import Database


Client().run()

fonts = {
    "bold": '!"$\\\'(),-./𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗:;?@𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙_𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "double-struck": '!"$\\\'(),-./𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡:;?@𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ_𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "bold-fraktur": '!"$\\\'(),-./𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗:;?@𝕬𝕭𝕮𝕯𝕰𝕱𝕲𝕳𝕴𝕵𝕶𝕷𝕸𝕹𝕺𝕻𝕼𝕽𝕾𝕿𝖀𝖁𝖂𝖃𝖄𝖅_𝖆𝖇𝖈𝖉𝖊𝖋𝖌𝖍𝖎𝖏𝖐𝖑𝖒𝖓𝖔𝖕𝖖𝖗𝖘𝖙𝖚𝖛𝖜𝖝𝖞𝖟ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "bold-italic": '!"$\\\'(),-./𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗:;?@𝑨𝑩𝑪𝑫𝑬𝑭𝑮𝑯𝑰𝑱𝑲𝑳𝑴𝑵𝑶𝑷𝑸𝑹𝑺𝑻𝑼𝑽𝑾𝑿𝒀𝒁_𝒂𝒃𝒄𝒅𝒆𝒇𝒈𝒉𝒊𝒋𝒌𝒍𝒎𝒏𝒐𝒑𝒒𝒓𝒔𝒕𝒖𝒗𝒘𝒙𝒚𝒛ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "squared": '!"$\\\'(),-./0123456789:;?@🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉_🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "dark-squares": '!"$\\\'(),-./𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗:;?@🅰🅱🅲🅳🅴🅵🅶🅷🅸🅹🅺🅻🅼🅽🅾🅿🆀🆁🆂🆃🆄🆅🆆🆇🆈🆉_🅰🅱🅲🅳🅴🅵🅶🅷🅸🅹🅺🅻🅼🅽🅾🅿🆀🆁🆂🆃🆄🆅🆆🆇🆈🆉ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "circled": '!"$\\\'(),⊖.⦸0①②③④⑤⑥⑦⑧⑨:;?@ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ_ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ',
    "black-circles": '!"$\\\'(),-./𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗:;?@🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩_🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "emoji-text": '‼"$\\\'()🔽-◾/0123456789:;❓@🅰🅱🌜🐬𝓔🔩🐋♓🕴🎷🎉👢Ⓜ🥄😀🅿🍳🌱💲🍄⛎✌🔱❎🏋💤_🅰🅱🌜🐬𝓔🔩🐋♓🕴🎷🎉👢Ⓜ🥄😀🅿🍳🌱💲🍄⛎✌🔱❎🏋💤ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "upside-down": '¡"$\\\'(),-.\\0⇂ᄅƐގㄣ9ㄥ86:;?@∀ᙠƆᗡƎℲ⅁HIſ⋊˥WNOԀΌᴚS⊥∩ΛMX⅄Z¯ɐqɔpǝɟɓɥıɾʞlɯuodbɹsʇnʌʍxʎz',
    "mirrored": '!"$\\\'(),-./0123456789:;?@AdↃbƎꟻGHIJK⅃MᴎOꟼpᴙꙄTUVWXYZ_AdↄbɘꟻgHijklmᴎoqpᴙꙅTUvwxYz',
    "greek": '!"$\\\'(),-.\\0123456789:;?@ΛBᑕDΣFGΉIJKᒪMПӨPQЯƧƬЦVЩXYZ_ΛBᑕDΣFGΉIJKᒪMПӨPQЯƧƬЦVЩXYZ',
    "rounded": '!"$\\\'(),-.\\0123456789:;?@ᗩᗷᑕᗪEᖴGᕼIᒍKᒪᗰᑎOᑭᑫᖇᔕTᑌᐯᗯ᙭Yᘔ_ᗩᗷᑕᗪEᖴGᕼIᒍKᒪᗰᑎOᑭᑫᖇᔕTᑌᐯᗯ᙭Yᘔ',
    "gothic": '!"$\\\'(),-./0123456789:;?@𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ_𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "math-bold-script": '!"$\\\'(),-./0123456789:;?@𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩_𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "sans-serif-bold": '!"$\\\'(),-./𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵:;?@𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭_𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "bold-italic-sans-serif": '!"$\\\'(),-./𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗:;?@𝘼𝘽𝘾𝘿𝙀𝙁𝙂𝙃𝙄𝙅𝙆𝙇𝙈𝙉𝙊𝙋𝙌𝙍𝙎𝙏𝙐𝙑𝙒𝙓𝙔𝙕_𝙖𝙗𝙘𝙙𝙚𝙛𝙜𝙝𝙞𝙟𝙠𝙡𝙢𝙣𝙤𝙥𝙦𝙧𝙨𝙩𝙪𝙫𝙬𝙭𝙮𝙯ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',
    "sans-italic": '!"$\\\'(),-./0123456789:;?@𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡_𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€',

}
layout = '!"$\\\'(),-./0123456789:;?@ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyzÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝßàáâãäåæçèéêëìíîïñòóôõöøùúûüýÿ€'

# Decorators


def cooldown(user_cd=10, cmd_cd=5):
    def _cooldown(func):
        async def check(self, user, channel, args, *eargs, **kwargs):
            if user is not None and self.is_on_cooldown(func.__name__, user, user_cd, cmd_cd):
                return
            return await func(self, user, channel, args, *eargs, **kwargs)

        return check

    return _cooldown


def requires_gamba_data(func):
    async def check(self, user, channel, args, *eargs, **kwargs):
        if user not in self.gamba_data:
            self.add_new_user(user)
        return await func(self, user, channel, args, *eargs, **kwargs)

    return check


def requires_dev(func):
    async def check(self, user, channel, args, *eargs, **kwargs):
        if user != "sheepposu":
            return await self.send_message(channel, f"@{user} This is a dev only command")
        return await func(self, user, channel, args, *eargs, **kwargs)

    return check

# Util ig


async def do_timed_event(wait, callback, *args, **kwargs):
    await asyncio.sleep(wait)
    await callback(*args, **kwargs)


def print(message):
    sys.stdout.write(f"[{datetime.now().isoformat()}]{message}\n")
    sys.stdout.flush()


class Bot:
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    username = "sheepposubot"
    oauth = os.getenv("OAUTH")
    uri = "ws://irc-ws.chat.twitch.tv:80"
    channel_to_run_in = "btmc"

    # I should probably put this stuff in a file lol
    pull_options = {3: ['Slingshot', "Sharpshooter's Oath", 'Raven Bow', 'Emerald Orb', 'Thrilling Tales of Dragon Slayers', 'Magic Guide', 'Black Tassel', 'Debate Club', 'Bloodtainted Greatsword', 'Ferrous Shadow', 'Skyrider Sword ', 'Harbinger of Dawn', 'Cool Steel'], 4: ['Amber', 'Kaeya', 'Lisa', 'Barbara', 'Razor', 'Xiangling', 'Beidou', 'Xingqiu', 'Ningguang', 'Fischl', 'Bennett', 'Noelle', 'Chongyun', 'Sucrose', 'Diona', 'Xinyan', 'Rosaria', 'Yanfei', 'Sayu', 'Kujou Sara', 'Thoma', 'Gorou', 'Yun Jin', 'Favonius Sword', 'The Flute', 'Sacrificial Sword', "Lion's Roar", 'The Alley Flash', 'Favonius Greatsword', 'The Bell', 'Sacrificial Greatsword', 'Rainslasher', 'Lithic Blade', 'Akuoumaru', "Dragon's Bane", 'Favonius Lance', 'Lithic Spear', "Wavebreaker's Fin", 'Favonius Codex', 'The Widsith', 'Sacrificial Fragments', 'Eye of Perception', 'Favonius Warbow', 'The Stringless', 'Sacrificial Bow', 'Rust', 'Alley Hunter', 'Mitternachts Waltz', "Mouun's Moon", 'Wine and Song'], 5: ['Kamisato Ayato', 'Yae Miko', 'Shenhe', 'Arataki Itto', 'Sangonomiya Kokomi', 'Raiden Shogun', 'Yoimiya', 'Kamisato Ayaka', 'Kaedehara Kazuha', 'Eula', 'Hu Tao', 'Xiao', 'Ganyu', 'Albedo', 'Zhongli', 'Tartaglia', 'Klee', 'Venti', 'Keqing', 'Mona', 'Qiqi', 'Diluc', 'Jean', 'Aquila Favonia', 'Skyward Blade', 'Summit Shaper', 'Primordial Jade Cutter', 'Freedom-Sworn', 'Mistsplitter Reforged', 'Skyward Pride', "Wolf's Gravestone", 'The Unforged', 'Song of Broken Pines', 'Redhorn Stonethresher', 'Primordial Jade Winged-Spear', 'Skyward Spine', 'Vortex Vanquisher', 'Staff of Homa', 'Engulfing Lightning', 'Calamity Queller', 'Skyward Atlas', 'Lost Prayer to the Sacred Winds', 'Memory of Dust', 'Everlasting Moonglow', "Kagura's Verity", 'Skyward Harp', "Amos' Bow", 'Elegy for the End', 'Thundering Pulse', 'Polar Star']}
    banned_words = [  # Was originally used to stop this word from being posted for scramble, but since there's a new list with non-tos words it doesn't really do anything
        "kike"
    ]
    emotes = ['ALBERTSCOOKING', 'ANIKICHAD', 'AYAKA', 'billyOkay', 'bruh', 'Champ', 'Clueless', 'Drake', 'enyoters',
              'FRICK', 'Groucho', 'GunL', 'hackingCD', 'KoroneFukireta', 'LETSGO', 'MetalTime', 'monkaSpeed', 'nekoNc',
              'NOOO', 'NotAllowed', 'Offline', 'peepoBye', 'peepoHey', 'pepeW', 'PogTasty', 'PointYou', 'ppParty',
              'SEASONING', 'SmartPhone', 'SteerL', 'SUSSY', 'ThinkL', 'ThinkR', 'TrollDespair', 'Baby', 'bambooPls',
              'billyReady', 'BLANKIES', 'BlobWobble', 'BoatW', 'Boolin', 'BoolinJAM', 'BoolinS', 'BoolLaugh', 'btmcAcc',
              'btmcDitch', 'btmcFly', 'btmcGa', 'btmcPls', 'btmcRainbowPls', 'btmcSMD', 'CartW', 'CATBEDOINGTHELAUNDRY',
              'catJAM', 'catKISS', 'Chatting', 'COGGERS', 'COGW', 'CoolChamp', 'CrabPls', 'DIANO', 'DinkDonk',
              'DOGGERS', 'DonoWall', 'DrumTime', 'FeelsLagMan', 'FeelsRainMan', 'FOGGERS', 'funnyChamp', 'gachiBOP',
              'gachiHYPER', 'GachiPls', 'gachiW', 'GIGACHAD', 'Goose', 'HACKERMANS', 'HYPERCLAP', 'iLOVEyou',
              'IMDONEMAN', 'LATE', 'miyanoHype', 'modCheck', 'monkaDMCA', 'monkaEXTREME', 'monkaSoap', 'monkaSTEER',
              'monkaTOS', 'NODDERS', 'noelDab', 'NOPERS', 'NOTED', 'nouCHEER', 'OkayChamp', 'OMEGALULiguess',
              'OMEGAROLL', 'osuWHO', 'OuttaPocket', 'PagChomp', 'PainsChamp', 'PauseChamp', 'PauseU', 'peepoArrive',
              'peepoClap', 'peepoLeave', 'PeepoSHAKE', 'peepoShy', 'pepeDS', 'pepeFASTJAM', 'PepegaAim', 'PepegaCredit',
              'PepegaPls', 'pepeJAM', 'pepeJAMJAM', 'pepeLaughing', 'pepeMeltdown', 'PepoCheer', 'peppyPls',
              'PETTHEPEEPO', 'PogChomp', 'PoggersFish', 'PogMe', 'PogO', 'Pogpega', 'PogU', 'PogYou', 'PorkChop',
              'ppCircle', 'ppCrazy', 'ppHop', 'ppHopper', 'ppOverheat', 'ppPoof', 'RainbowPls', 'RainbowPlsFAST',
              'rareBeast', 'ratJAM', 'reeferSad', 'SadChamp', 'SEEYOUNEXTTIME', 'SillyChamp', 'SOLVED', 'Stab',
              'StareChamp', 'sumSmash', 'THISSHOULDNOTBEPOSSIBLE', 'TriDance', 'TriFi', 'Tssk', 'veryPog', 'ViolinTime',
              'WeirdChamp', 'widepeepoHappyRightHeart', 'WorthIt', 'WYSI', 'YEPJAM', '3Head', '4HEader', '4Real',
              '5Head', 'AYAYAWeird', 'Bedge', 'BOGGED', 'colonD', 'COPIUM', 'forsenCD', 'HandsUp', 'HYPERAYAYA',
              'HYPERDANSGAMEW', 'Kapp', 'KEKW', 'KEKWait', 'KKomrade', 'KKonaW', 'LULW', 'Madge', 'MaN', 'MEGALUL',
              'monkaHmm', 'monkaLaugh', 'monkaW', 'OMEGALUL', 'osuHOW', 'PagMan', 'Pepega', 'PepegaHands', 'PepeHands',
              'PepeLaugh', 'PepePoint', 'PepoG', 'Pog', 'POGGERS', 'Prayge', 'REEEE', 'Sadge', 'SmileW', 'VaN',
              'WaitWhat', 'WICKED', 'Widega', 'WideHard', 'widepeepoHappy', 'widepeepoSad', 'Wokege', 'YEP', 'ZULUL',
              '7tvM', 'AlienDance', 'AYAYA', 'BasedGod', 'BillyApprove', 'Clap', 'Clap2', 'CrayonTime', 'EZ',
              'FeelsDankMan', 'FeelsOkayMan', 'FeelsStrongMan', 'FeelsWeirdMan', 'forsenPls', 'gachiBASS', 'gachiGASM',
              'GuitarTime', 'knaDyppaHopeep', 'nymnCorn', 'PartyParrot', 'peepoHappy', 'peepoSad', 'PepePls', 'PETPET',
              'PianoTime', 'ppL', 'RainTime', 'RareParrot', 'RebeccaBlack', 'reckH', 'Stare', 'SteerR', 'TeaTime',
              'WAYTOODANK', 'WineTime', 'YEAHBUT7TV', ':tf:', 'AngelThump', 'ariW', 'BroBalt', 'bttvNice', 'bUrself',
              'CandianRage', 'CiGrip', 'ConcernDoge', 'CruW', 'cvHazmat', 'cvL', 'cvMask', 'cvR', 'D:', 'DatSauce',
              'DogChamp', 'DuckerZ', 'FeelsAmazingMan', 'FeelsBadMan', 'FeelsBirthdayMan', 'FeelsGoodMan',
              'FireSpeed', 'FishMoley', 'ForeverAlone', 'GabeN', 'haHAA', 'HailHelix', 'Hhhehehe',
              'KappaCool', 'KaRappa', 'KKona', 'LuL', 'M&Mjc', 'monkaS', 'NaM', 'notsquishY', 'PoleDoge', 'RarePepe',
              'RonSmug', 'SaltyCorn', 'ShoopDaWhoop', 'sosGame', 'SourPls', 'SqShy', 'TaxiBro', 'tehPoleCat', 'TwaT',
              'VapeNation', 'VisLaud', 'WatChuSay', 'Wowee', 'WubTF', 'AndKnuckles', 'BeanieHipster', 'BORT', 'CatBag',
              'LaterSooner', 'LilZ', 'ManChicken', 'OBOY', 'OiMinna', 'YooHoo', 'ZliL', 'ZrehplaR', 'ZreknarF'
    ]
    bomb_time = 30

    def __init__(self):
        self.ws = None
        self.running = False
        self.loop = asyncio.get_event_loop()
        self.future_objects = []

        # Is ed offline or not
        self.offline = True

        # Twitch api stuff
        self.access_token, self.expire_time = self.get_access_token()
        self.expire_time += perf_counter()

        # Message related variables
        self.message_send_cd = 1.5
        self.last_message = 0
        self.message_lock = asyncio.Lock()

        # Command related variables
        self.commands = {
            "pull": self.pull,
            "genshinpull": self.pull,
            "guess": self.guess,
            "font": self.font,
            "fonts": self.fonts,
            # "trivia": self.trivia,
            'slap': self.slap,
            "pity": self.pity,
            "scramble": lambda channel, user, args: self.scramble(channel, user, args, "word"),
            "hint": lambda channel, user, args: self.hint(channel, user, args, "word"),
            "scramble_osu": lambda channel, user, args: self.scramble(channel, user, args, "osu"),
            "hint_osu": lambda channel, user, args: self.hint(channel, user, args, "osu"),
            "scramble_map": lambda channel, user, args: self.scramble(channel, user, args, "map"),
            "hint_map": lambda channel, user, args: self.hint(channel, user, args, "map"),
            "scramble_genshin": lambda channel, user, args: self.scramble(channel, user, args, "genshin"),
            "hint_genshin": lambda channel, user, args: self.hint(channel, user, args, "genshin"),
            "scramble_emote": lambda channel, user, args: self.scramble(channel, user, args, "emote"),
            "hint_emote": lambda channel, user, args: self.hint(channel, user, args, "emote"),
            "bal": self.balance,
            "leaderboard": self.leaderboard,
            "sheepp_filter": self.filter,
            "give": self.give,
            "toggle": self.toggle,
            "balance_market": self.market_balance,
            "sheepp_commands": self.say_commands,
            "ranking": self.get_ranking,
            "rps": self.rps,
            "new_name": self.new_name,
            "scramble_multiplier": self.scramble_difficulties,
            "scramble_calc": self.scramble_calc,
            "afk": self.afk,
            "help": self.help_command,
            "trivia_category": self.trivia_category,
            "sourcecode": self.sourcecode,
            "bombparty": self.bomb_party,
            "start": self.start_bomb_party,
            "join": self.join_bomb_party,
            "leave": self.leave_bomb_party,
            "settings": self.change_bomb_settings,
            "players": self.player_list,
            "funfact": self.random_fact,
        }  # Update pastebins when adding new commands
        self.cooldown = {}
        self.overall_cooldown = {}

        # Guess the number
        self.number = random.randint(1, 1000)

        # Trivia
        self.answer = None
        self.guessed_answers = []
        self.trivia_future = None
        self.trivia_diff = None
        self.trivia_info = {
            "hard": 100,
            "medium": 40,
            "easy": 20,
            "penalty": 0.25,
            "decrease": 0.5,
        }

        default_scramble_info = {
            "answer": None,
            "hint": "",
            "future": None,
        }
        self.scramble_info = {
            "word": {
                **default_scramble_info,
                "get_answer": lambda: random.choice(self.word_list),
                "name": "word",
                "hint_type": "default",
                "case_sensitive": False,
                "difficulty_multiplier": 1,
            },
            "osu": {
                **default_scramble_info,
                "get_answer": lambda: random.choice(self.top_players),
                "name": "player name",
                "hint_type": "default",
                "case_sensitive": False,
                "difficulty_multiplier": 0.8,
            },
            "map": {
                **default_scramble_info,
                "get_answer": lambda: random.choice(self.top_maps),
                "name": "map name",
                "hint_type": "default",
                "case_sensitive": False,
                "difficulty_multiplier": 1.3,
            },
            "genshin": {
                **default_scramble_info,
                "get_answer": lambda: random.choice(self.genshin),
                "name": "genshin weap/char",
                "hint_type": "default",
                "case_sensitive": False,
                "difficulty_multiplier": 0.7,
            },
            "emote": {
                **default_scramble_info,
                "get_answer": lambda: random.choice(self.emotes),
                "name": "emote",
                "hint_type": "every_other",
                "case_sensitive": True,
                "difficulty_multiplier": 0.6,
            }
        }

        # Bomb party
        self.used_words = []
        self.party = {}
        self.bomb_party_future = None
        self.current_player = 0
        self.current_letters = None
        self.bomb_start_time = 0
        self.turn_order = []
        self.timer = 30
        self.bomb_settings = {
            "difficulty": "medium",
            "timer": 30,
            "minimum_time": 5,
            "lives": 3,
        }
        self.valid_bomb_settings = {
            "difficulty": ("easy", "medium", "hard", "nightmare", "impossible"),
            "timer": range(5, 60+1),
            "minimum_time": range(0, 10+1),
            "lives": range(1, 5+1),
        }

        # Data
        self.database = Database()

        genshin = list(self.pull_options.values())
        self.genshin = genshin[0] + genshin[1] + genshin[2]

        # File saved data
        self.pity = self.database.get_pity()
        self.gamba_data = self.database.get_userdata()
        self.top_players = []
        self.top_maps = []
        self.word_list = []
        self.facts = []
        self.afk = self.database.get_afk()
        self.all_words = []
        self.bomb_party_letters = {}
        self.load_data()

    # Util

    def is_on_cooldown(self, command, user, user_cd=10, cmd_cd=5):
        if command not in self.overall_cooldown:
            self.overall_cooldown.update({command: perf_counter()})
            return False
        if perf_counter() - self.overall_cooldown[command] < cmd_cd:
            return True
        if command not in self.cooldown:
            self.cooldown.update({command: {user: perf_counter()}})
            return False
        if user not in self.cooldown[command]:
            self.cooldown[command].update({user: perf_counter()})
            self.overall_cooldown[command] = perf_counter()
            return False
        if perf_counter() - self.cooldown[command][user] < user_cd:
            return True
        self.cooldown[command][user] = perf_counter()
        self.overall_cooldown[command] = perf_counter()
        return False

    def set_timed_event(self, wait, callback, *args, **kwargs):
        return asyncio.run_coroutine_threadsafe(do_timed_event(wait, callback, *args, **kwargs), self.loop)

    @staticmethod
    def format_date(date):
        minutes = (datetime.now() - date).total_seconds() // 60
        hours = 0
        days = 0
        if minutes >= 60:
            hours = minutes // 60
            minutes = minutes % 60
            if hours >= 24:
                days = hours // 24
                hours = hours % 24
        elif minutes == 0:
            return f"{(datetime.now() - date).seconds} seconds"
        return ((f"{int(days)} day(s) " if days != 0 else "") + (f" {int(hours)} hour(s) " if hours != 0 else "") + (
            f" {int(minutes)} minute(s)" if minutes != 0 else "")).strip()

    # File save/load

    def construct_bomb_party_letters(self):
        with open("data/2strings.json", "r") as f:
            letters = json.load(f)
            with open("data/3strings.json", "r") as f3:
                letters.update(json.load(f3))

            self.bomb_party_letters = {
                "easy": [let for let, amount in letters.items() if amount >= 10000 and '-' not in let],
                "medium": [let for let, amount in letters.items() if 10000 > amount >= 5000 and '-' not in let],
                "hard": [let for let, amount in letters.items() if 5000 > amount >= 1000 or (amount >= 5000 and '-' in let)],
                "nightmare": [let for let, amount in letters.items() if 1000 > amount >= 500],
                "impossible": [let for let, amount in letters.items() if 500 > amount],
            }

    def load_top_players(self):
        with open("data/top players (200).json", "r") as f:
            self.top_players = json.load(f)

    def load_top_maps(self):
        with open("data/top_maps.json", "r") as f:
            self.top_maps = json.load(f)

    def load_words(self):
        with open("data/words.json", "r") as f:
            self.word_list = json.load(f)

    def load_facts(self):
        with open("data/facts.json", "r") as f:
            self.facts = json.load(f)

    def load_all_words(self):
        with open("data/all_words.json", "r") as f:
            self.all_words = [word.lower() for word in json.load(f)]

    def load_data(self):
        self.load_top_players()
        self.load_top_maps()
        self.load_words()
        self.load_facts()
        self.load_all_words()
        self.construct_bomb_party_letters()

    def save_money(self, user):
        self.database.update_userdata(user, 'money', round(self.gamba_data[user]['money']))

    # Api request stuff

    def load_top_plays(self):  # To be used in the future maybe
        resp = requests.get('https://osutrack-api.ameo.dev/bestplay?mode=0')
        resp.raise_for_status()
        top_plays = resp.json()

    def get_access_token(self):
        resp = requests.post("https://id.twitch.tv/oauth2/token", params={"client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "client_credentials"})
        resp.raise_for_status()
        resp = resp.json()
        return resp['access_token'], resp['expires_in']

    def get_stream_status(self):
        try:
            resp = requests.get("https://api.twitch.tv/helix/search/channels", params={"query": self.channel_to_run_in, "first": 1}, headers={"Authorization": f"Bearer {self.access_token}", "Client-Id": self.client_id})
            resp.raise_for_status()
            resp = resp.json()
            self.offline = not resp['data'][0]['is_live']
        except:
            print(traceback.format_exc())
            self.offline = False

    # Fundamental

    async def start(self):
        async with websockets.connect(self.uri) as ws:
            self.ws = ws
            self.running = True

            try:
                await self.connect()  # Connect to the irc server
                poll = asyncio.run_coroutine_threadsafe(self.poll(), self.loop)  # Begin polling for events sent by the server
                await asyncio.sleep(5)  # Leave time for reply from server before beginning to join channels and stuff
                await self.run()  # Join channels + whatever else is in the function

                last_check = perf_counter() - 20
                while self.running:
                    await asyncio.sleep(1)  # Leave time for other threads to run

                    # Check is ed is live
                    if perf_counter() - last_check >= 20:
                        self.get_stream_status()
                        last_check = perf_counter()

                    # Check if access token needs to be renewed
                    if perf_counter() >= self.expire_time:
                        self.access_token, self.expire_time = self.get_access_token()
                        self.expire_time += perf_counter()

                    # Check all future objects and if they're done: print the result and remove them from the list
                    for future in self.future_objects:
                        if future.done():
                            try:
                                result = future.result()
                                if result is not None:
                                    print(future.result())
                            except:
                                print(traceback.format_exc())
                            finally:
                                self.future_objects.remove(future)

                    # Check if poll is no longer running, in which case, the bot is no longer running.
                    if poll.done():
                        print(poll.result())
                        self.running = False

            except KeyboardInterrupt:
                pass
            except websockets.exceptions.ConnectionClosedError as e:
                # Restart the bot
                print(e)
            except:
                print(traceback.format_exc())
            finally:
                self.running = False

    async def run(self):
        # await self.register_cap("tags")
        await self.join(self.username)
        await self.join(self.channel_to_run_in)

    async def connect(self):
        await self.ws.send(f"PASS {self.oauth}")
        print(f"> PASS {self.oauth}")
        await self.ws.send(f"NICK {self.username}")
        print(f"> NICK {self.username}")

    async def poll(self):
        while self.running:
            data = await self.ws.recv()
            print(f"< {data}")

            if data.startswith("PING"):
                await self.ws.send("PONG :tmi.twitch.tv")
                continue

            # Account for tags
            data = data.split()
            offset = 0
            tags = None
            if data[0].startswith("@"):
                tags = {tag.split("=")[0]: tag.split("=")[1] for tag in data[0].split(";")}
                offset = 1
            source = data[0 + offset]
            command = data[1 + offset]
            channel = data[2 + offset][1:]
            content = " ".join(data[3:])[1:]

            if command == "PRIVMSG":
                user = source.split("!")[0][1:]
                # Run in its own thread to avoid holding up the polling thread
                future = asyncio.run_coroutine_threadsafe(self.on_message(user, channel, content, tags), self.loop)
                self.future_objects.append(future)

    async def join(self, channel):
        await self.ws.send(f"JOIN #{channel}")
        print(f"> JOIN #{channel}")

    async def part(self, channel):
        await self.ws.send(f"PART #{channel}\r\n")
        print(f"< PART #{channel}\r\n")

    async def register_cap(self, *caps):
        caps = ' '.join([f'twitch.tv/{cap}' for cap in caps])
        await self.ws.send(f"CAP REQ :{caps}\r\n")
        print(f"< CAP REQ :{caps}\r\n")

    async def send_message(self, channel, message):
        if not self.offline and channel == self.channel_to_run_in:
            return
        await self.message_lock.acquire()
        await self.ws.send(f"PRIVMSG #{channel} :/me {message}")
        print(f"> PRIVMSG #{channel} :{message}")
        await asyncio.sleep(1.5)  # Wait 1.5 seconds before releasing lock to avoid going over rate limits
        self.message_lock.release()

    # Events

    async def on_message(self, user, channel, message, tags):
        if (not self.offline and channel == self.channel_to_run_in) or user == self.username:
            return

        if message.lower().startswith("pogpega") and message.lower() != "pogpega":
            message = message[8:]

        if message.startswith("Use code"):
            await asyncio.sleep(1)
            await self.send_message(channel, "PogU 👆 Use code \"BTMC\" !!!")
        elif message.strip() in [str(num) for num in range(1, 5)] and self.trivia_diff is not None:
            message = int(message)
            if message in self.guessed_answers:
                return
            await self.on_answer(user, channel, message)
            return

        for scramble_type, info in self.scramble_info.items():
            if info['answer'] is not None:
                await self.on_scramble(user, channel, message, scramble_type)
            if info['future'] is not None and info['future'].done() and info['future'].result():
                print(info['future'].result())

        if self.bomb_start_time != 0 and self.turn_order[self.current_player] == user:
            await self.on_bomb_party(channel, message)

        await self.on_afk(user, channel, message)

        if message.startswith("!"):
            command = message.split()[0].lower().replace("!", "")
            args = message.split()[1:]
            if command in self.commands:
                if user == self.username:
                    await asyncio.sleep(1)
                await self.commands[command](user, channel, args)

    # Commands

    @cooldown(cmd_cd=1, user_cd=2)
    async def pull(self, user, channel, args):
        if user not in self.pity:
            self.pity.update({user: {4: 0, 5: 0}})
            self.database.new_pity(user, 0, 0)

        pity = False
        self.pity[user][4] += 1
        self.pity[user][5] += 1
        if self.pity[user][4] == 10 and self.pity[user][5] != 90:
            pull = 4
            pity = True
        elif self.pity[user][5] == 90:
            pull = 5
            pity = True
        else:
            num = random.randint(1, 1000)
            pull = 3
            if num <= 6:
                pull = 5
            elif num <= 57:
                pull = 4
        await self.send_message(channel,
                                f"@{user} You pulled {random.choice(self.pull_options[pull])} " +
                                ("\u2B50\u2B50\u2B50" if pull == 3 else '🌟' * pull) +
                                {3: ". 😔", 4: "! Pog", 5: "! PogYou"}[pull] +
                                ((" Rolls in: " + str(
                                    self.pity[user][pull] if not pity else {4: 10, 5: 90}[pull])) if pull != 3 else "")
                                )
        if pull == 5:
            self.pity[user][5] = 0
            self.pity[user][4] = 0
        elif pull == 4:
            self.pity[user][4] = 0
        self.database.save_pity(user, self.pity[user][4], self.pity[user][5])

    @cooldown()
    async def font(self, user, channel, args):
        if len(args) < 2:
            return await self.send_message(channel, "Must provide a font name and characters to convert. Do !fonts to see a list of valid fonts.")

        font_name = args[0].lower()
        if font_name not in fonts:
            return await self.send_message(channel, f"{font_name} is not a valid font name.")

        await self.send_message(channel, "".join([fonts[font_name][layout.index(char)] if char in layout else char for char in " ".join(args[1:])]))

    @cooldown()
    async def fonts(self, user, channel, args):
        await self.send_message(channel, f'Valid fonts: {", ".join(list(fonts.keys()))}.')

    @cooldown(user_cd=5, cmd_cd=3)
    async def guess(self, user, channel, args):
        if len(args) < 1:
            return await self.send_message(channel, f"@{user} You must provide a number 1-1000 to guess with")

        try:
            guess = int(args[0])
        except ValueError:
            return await self.send_message(channel, f"@{user} That's not a valid number OuttaPocket Tssk")

        if self.number == guess:
            await self.send_message(channel, f"@{user} You got it PogYou")
            self.number = random.randint(1, 1000)
        else:
            await self.send_message(channel, f"@{user} It's not {guess}. Try guessing " + (
                "higher" if guess < self.number else "lower") + ". veryPog")

    @cooldown()
    async def trivia(self, user, channel, args):
        if self.answer is not None:
            return
        self.answer = "temp"
        difficulty = {
            "easy": "EZ",
            "medium": "monkaS",
            "hard": "pepeMeltdown"
        }
        resp = requests.get(f"https://opentdb.com/api.php?amount=1&type=multiple{f'&category={args[0]}' if len(args) > 0 else ''}").json()['results'][0]

        answers = [resp['correct_answer']] + resp['incorrect_answers']
        random.shuffle(answers)
        self.answer = answers.index(resp['correct_answer']) + 1
        answer_string = " ".join([html.unescape(f"[{i + 1}] {answers[i]} ") for i in range(len(answers))])
        self.trivia_diff = resp['difficulty']

        await self.send_message(channel,
                                f"Difficulty: {resp['difficulty']} {difficulty[resp['difficulty']]} Category: {resp['category']} veryPog Question: {html.unescape(resp['question'])} monkaHmm Answers: {answer_string}")
        self.trivia_future = self.set_timed_event(20, self.on_trivia_finish, channel)

    @requires_gamba_data
    async def on_answer(self, user, channel, answer):
        self.guessed_answers.append(answer)
        worth = self.trivia_info[self.trivia_diff]
        if answer == self.answer:
            await self.send_message(channel, f"@{user} {answer} is the correct answer ✅. You gained {worth * (self.trivia_info['decrease'] ** (len(self.guessed_answers) - 1))} Becky Bucks 5Head Clap")
            self.gamba_data[user]['money'] += worth * (self.trivia_info['decrease'] ** (len(self.guessed_answers) - 1))
            self.save_money(user)
            await self.on_trivia_finish(channel, timeout=False)
        else:
            await self.send_message(channel, f"@{user} {answer} is wrong ❌. You lost {worth*self.trivia_info['penalty']} Becky Bucks 3Head Clap")
            self.gamba_data[user]['money'] -= worth*self.trivia_info['penalty']
            self.save_money(user)
            if self.answer not in self.guessed_answers and len(self.guessed_answers) == 3:
                self.trivia_diff = None  # make sure someone doesn't answer before it can say no one got it right
                await self.send_message(channel, f"No one answered correctly! The answer was {self.answer}.")
                await self.on_trivia_finish(channel, timeout=False)

    async def on_trivia_finish(self, channel, timeout=True):
        if timeout:
            await self.send_message(channel, f"Time has run out for the trivia! The answer was {self.answer}.")
        else:
            self.trivia_future.cancel()
        self.answer = None
        self.guessed_answers = []
        self.trivia_diff = None
        self.trivia_future = None


    @cooldown()
    async def slap(self, user, channel, args):
        if not args:
            return await self.send_message(channel, "You must provide a user to slap.")

        hit = random.choice((True, False))
        await self.send_message(channel,
                                f"{user} slapped {args[0]}! D:" if hit else f"{user} tried to slap {args[0]}, but they caught it! pepePoint")

    @cooldown(cmd_cd=3)
    async def pity(self, user, channel, args):
        if user not in self.pity:
            return await self.send_message(channel, "You haven't rolled yet (from the time the bot started up).")
        await self.send_message(channel,
                                f"@{user} 4* pity in {10 - self.pity[user][4]} rolls; 5* pity in {90 - self.pity[user][5]} rolls.")

    @cooldown()
    async def scramble(self, user, channel, args, scramble_type):
        if self.scramble_info[scramble_type]['answer'] is not None:
            return

        self.scramble_info[scramble_type]['answer'] = self.scramble_info[scramble_type]['get_answer']()
        while self.scramble_info[scramble_type]['answer'].lower() in self.banned_words:
            self.scramble_info[scramble_type]['answer'] = self.scramble_info[scramble_type]['get_answer']()
        self.scramble_info[scramble_type]['hint'] = "?" * len(self.scramble_info[scramble_type]['answer'])
        scrambled_word = [char for char in self.scramble_info[scramble_type]['answer']]
        random.shuffle(scrambled_word)
        scrambled_word = "".join(scrambled_word)
        await self.send_message(channel,
                                f"Unscramble this {self.scramble_info[scramble_type]['name']}: {scrambled_word.lower()}")
        self.scramble_info[scramble_type]['future'] = self.set_timed_event(120, self.on_scramble_finish, channel,
                                                                           scramble_type)

    async def on_scramble(self, user, channel, guess, scramble_type):
        word = self.scramble_info[scramble_type]['answer']
        hint = self.scramble_info[scramble_type]['hint']
        if not word:
            return
        if (guess.lower() == word.lower() and not self.scramble_info[scramble_type]["case_sensitive"]) or guess == word:
            self.scramble_info[scramble_type]['answer'] = None
            self.scramble_info[scramble_type]['hint'] = ""
            self.scramble_info[scramble_type]['future'].cancel()
            self.scramble_info[scramble_type]['future'] = None
            money = round(random.randint(5, 10) * len(word.replace(" ", "")) * hint.count("?")/len(word) * self.scramble_info[scramble_type]['difficulty_multiplier'])
            await self.send_message(channel,
                                    f"@{user} You got it right! {word} was the {self.scramble_info[scramble_type]['name']}. Drake You've won {money} Becky Bucks!")
            if user not in self.gamba_data:
                self.add_new_user(user)
            self.gamba_data[user]["money"] += money
            self.save_money(user)

    @cooldown(cmd_cd=5)
    async def hint(self, user, channel, args, scramble_type):
        word = self.scramble_info[scramble_type]['answer']
        hint = self.scramble_info[scramble_type]['hint']
        if word is None or "?" not in hint:
            return
        {
            "default": self.default_hint,
            "every_other": self.every_other_hint,
        }[self.scramble_info[scramble_type]['hint_type']](scramble_type)

        await self.send_message(channel, f"Here's a hint ({self.scramble_info[scramble_type]['name']}): " +
                                self.scramble_info[scramble_type]['hint'].lower())

    def default_hint(self, scramble_type):
        word = self.scramble_info[scramble_type]['answer']
        hint = self.scramble_info[scramble_type]['hint']
        i = hint.index("?")
        self.scramble_info[scramble_type]['hint'] = hint[:i] + word[i] + (len(word) - i - 1) * "?"

    def every_other_hint(self, scramble_type):
        word = self.scramble_info[scramble_type]['answer']
        hint = self.scramble_info[scramble_type]['hint']
        try:
            i = hint.index("??") + 1
            self.scramble_info[scramble_type]['hint'] = hint[:i] + word[i] + (len(word) - i - 1) * "?"
        except ValueError:
            self.default_hint(scramble_type)

    async def on_scramble_finish(self, channel, scramble_type):
        await self.send_message(channel,
                                f"Time is up! The {self.scramble_info[scramble_type]['name']} was {self.scramble_info[scramble_type]['answer']}")
        self.scramble_info[scramble_type]['answer'] = None
        self.scramble_info[scramble_type]['hint'] = ""
        self.scramble_info[scramble_type]['future'] = None

    def add_new_user(self, user):
        self.gamba_data.update({user: {
            'money': 0,
            'settings': {
                'receive': True
            }
        }})
        self.database.new_user(user)

    @cooldown(user_cd=60)
    @requires_gamba_data
    async def collect(self, user, channel, args):
        money = random.randint(10, 100)
        self.gamba_data[user]["money"] += money
        await self.send_message(channel, f"@{user} You collected {money} Becky Bucks!")
        self.save_money(user)

    @cooldown(cmd_cd=2, user_cd=3)
    @requires_gamba_data
    async def gamba(self, user, channel, args):
        if not args:
            return await self.send_message(channel,
                                           f"@{user} You must provide an amount to bet and a risk factor. Do !riskfactor to learn more")
        if len(args) < 2:
            return await self.send_message(channel,
                                           f"@{user} You must also provide a risk factor. Do !riskfactor to learn more.")
        amount = 0
        risk_factor = 0
        if args[0].lower() == "all":
            args[0] = self.gamba_data[user]['money']
        try:
            amount = float(args[0])
            risk_factor = int(args[1])
        except ValueError:
            return await self.send_message(channel,
                                           f"@{user} You must provide a valid number (integer for risk factor) value.")
        if risk_factor not in range(1, 100):
            return await self.send_message(channel, f"@{user} The risk factor you provided is outside the range 1-99!")
        if amount > self.gamba_data[user]["money"]:
            return await self.send_message(channel, f"@{user} You don't have enough Becky Bucks to bet that much!")
        if amount == 0:
            return await self.send_message(channel, f"@{user} You can't bet nothing bruh")
        if amount < 0:
            return await self.send_message(channel, f"@{user} Please specify a positive integer bruh")

        loss = random.randint(1, 100) in range(risk_factor)
        if loss:
            await self.send_message(channel, f"@{user} YIKES! You lost {amount} Becky Bucks ❌ [LOSE]")
            self.gamba_data[user]["money"] -= amount
        else:
            payout = round((1 + risk_factor * 0.01) * amount - amount, 2)
            await self.send_message(channel, f"@{user} You gained {payout} Becky Bucks! ✅ [WIN]")
            self.gamba_data[user]["money"] += payout
        self.gamba_data[user]["money"] = round(self.gamba_data[user]["money"], 2)
        self.save_money(user)

    @cooldown()
    async def risk_factor(self, user, channel, args):
        await self.send_message(channel,
                                f"@{user} The risk factor determines your chances of losing the bet and your payout. The chance of you winning the bet is 100 minus the risk factor. Your payout is (1 + riskfactor*0.01)) * amount bet (basically says more risk = better payout)")

    @cooldown(user_cd=10)
    @requires_gamba_data
    async def balance(self, user, channel, args):
        await self.send_message(channel,
                                f"@{user} You currently have {round(self.gamba_data[user]['money'], 2)} Becky Bucks.")

    @cooldown()
    async def leaderboard(self, user, channel, args):
        lead = {k: v for k, v in sorted(self.gamba_data.items(), key=lambda item: item[1]['money'])}
        top_users = list(lead.keys())[-5:]
        top_money = list(lead.values())[-5:]
        output = "Top 5 richest users: "
        for i in range(5):
            output += f'{i + 1}. {top_users[4 - i]}_${round(top_money[4 - i]["money"], 2)} '
        await self.send_message(channel, output)

    @cooldown()
    @requires_gamba_data
    async def get_ranking(self, user, channel, args):
        lead = {k: v for k, v in sorted(self.gamba_data.items(), key=lambda item: item[1]['money'])}
        users = list(lead.keys())
        users.reverse()
        rank = users.index(user) + 1
        await self.send_message(channel, f"@{user} You are currently rank {rank} in terms of Becky Bucks!")

    @cooldown()
    async def filter(self, user, channel, args):
        await self.send_message(channel,
                                "Here's a filter that applies to me and any user that uses my commands: https://pastebin.com/nyBX5jbb")

    @cooldown()
    @requires_gamba_data
    async def give(self, user, channel, args):
        user_to_give = args[0].lower()
        if user_to_give not in self.gamba_data:
            return await self.send_message(channel, f"@{user} That's not a valid user to give money to.")
        if not self.gamba_data[user_to_give]['settings']['receive']:
            return await self.send_message(channel,
                                           f"@{user} This user has their receive setting turned off and therefore cannot accept money.")
        amount = args[1]
        try:
            amount = round(float(amount), 2)
        except ValueError:
            return await self.send_message(channel, f"@{user} That's not a valid number.")
        if self.gamba_data[user]['money'] < amount:
            return await self.send_message(channel, f"@{user} You don't have that much money to give.")

        if amount < 0:
            return await self.send_message(channel, "You can't give someone a negative amount OuttaPocket Tssk")

        self.gamba_data[user]['money'] -= amount
        self.gamba_data[user_to_give]['money'] += amount
        await self.send_message(channel, f"@{user} You have given {user_to_give} {amount} Becky Bucks!")

    @cooldown()
    @requires_gamba_data
    async def toggle(self, user, channel, args):
        if len(args) < 2:
            return await self.send_message(channel, f"@{user} You must provide a setting name and either on or off")
        setting = args[0].lower()
        if setting not in self.gamba_data[user]['settings']:
            return await self.send_message(channel,
                                           f"@{user} That's not a valid setting name. The settings consist of the following: " + ", ".join(
                                               list(self.gamba_data[user]['settings'].keys())))
        try:
            value = {"on": True, "off": False}[args[1].lower()]
        except KeyError:
            return await self.send_message(channel, "You must specify on or off.")

        self.gamba_data[user]['settings'][setting] = value
        self.database.update_userdata(user, setting, value)
        await self.send_message(channel, f"@{user} The {setting} setting has been turned {args[1]}.")

    @cooldown()
    @requires_dev
    async def market_balance(self, user, channel, args):
        lead = {k: v for k, v in sorted(self.gamba_data.items(), key=lambda item: item[1]['money'])}
        top_user = list(lead.keys())[-1]
        pool = self.gamba_data[top_user]['money']
        giveaway = round(pool / len(self.gamba_data), 2)
        self.gamba_data[top_user]['money'] = 0
        for user in self.gamba_data:
            self.gamba_data[user]['money'] += giveaway

        await self.send_message(channel,
                                f"I have given away {giveaway} Becky Bucks to each player provided by {top_user} without their consent PogU")

    @cooldown(cmd_cd=10)
    async def say_commands(self, user, channel, args):
        await self.send_message(channel, f"@{user} Here is a list of my commands: https://pastebin.com/tK9f0EWK")

    @cooldown(user_cd=5, cmd_cd=3)
    @requires_gamba_data
    async def rps(self, user, channel, args):
        if not args:
            return await self.send_message(channel, f"@{user} You must say either rock, paper, or scissors. (You can also use the first letter for short)")
        choice = args[0][0].lower()
        if choice not in ('r', 'p', 's'):
            return await self.send_message(channel, f"@{user} That's not a valid move. You must say either rock, paper, or scissors. (You can also use the first letter for short)")

        com_choice = random.choice(('r', 'p', 's'))
        win = {"r": "s", "s": "p", "p": "r"}
        abbr = {"r": "rock", "s": "scissors", "p": "paper"}
        if com_choice == choice:
            return await self.send_message(channel, f"@{user} I also chose {abbr[com_choice]}! bruh")
        if win[com_choice] == choice:
            await self.send_message(channel, f"@{user} LETSGO I won, {abbr[com_choice]} beats {abbr[choice]}. You lose 10 Becky Bucks!")
            self.gamba_data[user]['money'] -= 10
            return self.save_money(user)
        await self.send_message(channel, f"@{user} IMDONEMAN I lost, {abbr[choice]} beats {abbr[com_choice]}. You win 10 Becky Bucks!")
        self.gamba_data[user]['money'] += 10
        self.save_money(user)
        
    @requires_dev
    async def new_name(self, user, channel, args):
        old_name = args[0]
        new_name = args[1]
        if old_name not in self.gamba_data or new_name not in self.gamba_data:
            return await self.send_message(channel, "One of the provided names is not valid.")
        self.gamba_data[old_name]['money'] += self.gamba_data[new_name]['money']
        self.gamba_data[new_name] = dict(self.gamba_data[old_name])
        del self.gamba_data[old_name]
        await self.send_message(channel, "The data has been updated for the new name!")

    @cooldown()
    async def scramble_difficulties(self, user, channel, args):
        await self.send_message(channel, f"@{user} Difficulty multiplier for each scramble: {', '.join(['%s-%s' %(scramble, info['difficulty_multiplier']) for scramble, info in self.scramble_info.items()])}")

    @cooldown()
    async def scramble_calc(self, user, channel, args):
        await self.send_message(channel, f"@{user} Scramble payout is calculated by picking a random number 5-10, "
                                         f"multiplying that by the length of the word (excluding spaces), multiplying "
                                         f"that by hint reduction, and multiplying that by the scramble difficulty "
                                         f"multiplier for that specific scramble. To see the difficulty multipliers, "
                                         f"do !scramble_multiplier. Hint reduction is the length of the word minus the "
                                         f"amount of hints used divided by the length of the word.")

    @cooldown()
    async def fact(self, user, channel, args):
        await self.send_message(channel, f"@{user} {random.choice(self.facts)}")

    @cooldown()
    async def afk(self, user, channel, args):
        await self.send_message(channel, f"@{user} Your afk has been set.")
        message = " ".join(args)
        self.afk[user] = {"message": message, "time": datetime.now().isoformat()}
        self.database.save_afk(user, message)

    @cooldown()
    async def help_command(self, user, channel, args):
        await self.send_message(channel, f"@{user} sheepposubot help (do !commands for StreamElements): https://sheep.sussy.io/index.html (domain kindly supplied by pancakes man)")

    async def on_afk(self, user, channel, message):
        pings = [word.replace("@", "").replace(",", "").replace(".", "").replace("-", "") for word in message.lower().split() if word.startswith("@")]
        for ping in pings:
            if ping in self.afk:
                await self.send_message(channel,  f"@{user} {ping} is afk ({self.format_date(datetime.fromisoformat(self.afk[ping]['time']))} ago): {self.afk[ping]['message']}")

        if user not in self.afk:
            return
        elif (datetime.now() - datetime.fromisoformat(self.afk[user]['time'])).seconds > 60:
            await self.send_message(channel, f"@{user} Your afk has been removed.")
            del self.afk[user]
            self.database.delete_afk(user)

    @cooldown()
    async def trivia_category(self, user, channel, args):
        await self.send_message(channel, f"@{user} I'll make something more intuitive later but for now, if you want to know which number correlates to which category, go here https://opentdb.com/api_config.php, click a category, click generate url and then check the category specified in the url.")

    @cooldown()
    async def sourcecode(self, user, channel, args):
        await self.send_message(channel, f"@{user} https://github.com/Sheepposu/offlinechatbot")

    # Bomb party functions
    @cooldown()
    async def bomb_party(self, user, channel, args):
        if len(self.party) > 0:
            return
        self.party.update({user: self.bomb_settings['lives']})

        await self.send_message(channel, f"{user} has started a Bomb Party game! Anyone else who wants to play should type !join. When enough players have joined, the host should type !start to start the game, otherwise the game will automatically start or close after 2 minutes.")
        self.bomb_party_future = self.set_timed_event(120, self.close_or_start_game, channel)

    async def close_or_start_game(self, channel):
        if len(self.party) < 2:
            self.close_bomb_party()
            return await self.send_message(channel, "The bomb party game has closed since there is only one player in the party.")
        await self.start_bomb_party(None, channel, None, False)

    @cooldown()
    async def start_bomb_party(self, user, channel, args, cancel=True):
        if len(self.party) == 0 or self.turn_order or list(self.party.keys())[0] != user:
            return
        if len(self.party) < 2:
            return await self.send_message(channel, f"@{user} You need at least 2 players to start the bomb party game.")
        if cancel:
            self.bomb_party_future.cancel()

        for player in self.party:
            self.party[player] = self.bomb_settings['lives']

        self.turn_order = list(self.party.keys())
        random.shuffle(self.turn_order)
        player = self.turn_order[self.current_player]
        self.current_letters = random.choice(self.bomb_party_letters[self.bomb_settings['difficulty']])

        await self.send_message(channel, f"@{player} ({'♥'*self.party[player]}) You're up first! Your string of letters is {self.current_letters}")
        self.timer = self.bomb_settings['timer']
        self.bomb_party_future = self.set_timed_event(self.timer+5, self.bomb_party_timer, channel)
        self.bomb_start_time = perf_counter()

    @cooldown(user_cd=10, cmd_cd=0)
    async def join_bomb_party(self, user, channel, args):
        if len(self.party) == 0 or self.turn_order:
            return
        if user in self.party:
            return await self.send_message(channel, f"@{user} You have already joined the game")

        self.party.update({user: 0})
        await self.send_message(channel, f"@{user} You have joined the game of bomb party!")

    @cooldown(cmd_cd=0)
    async def leave_bomb_party(self, user, channel, args):
        if len(self.party) == 0 or user not in self.party:
            return
        self.party[user] = 0
        await self.send_message(channel, f"@{user} You have left the game of bomb party.")
        if self.turn_order and await self.check_win(channel):
            self.bomb_party_future.cancel()
        elif self.turn_order and self.turn_order[self.current_player] == user:
            self.bomb_party_future.cancel()
            await self.next_player(channel)
        elif not self.turn_order:
            del self.party[user]
            if len(self.party) == 0:
                self.close_bomb_party()
                await self.send_message(channel, "The game of bomb party has closed.")

    @cooldown(user_cd=0, cmd_cd=0)
    async def change_bomb_settings(self, user, channel, args):
        if len(self.party) == 0 or self.turn_order or list(self.party.keys())[0] != user:
            return
        if len(args) < 2:
            return await self.send_message(channel, f"@{user} You must provide a setting name and the value: !settings <setting> <value>. Valid settings: {', '.join(list(self.bomb_settings.keys()))}")
        setting = args[0].lower()
        value = args[1].lower()
        if setting not in self.bomb_settings:
            return await self.send_message(channel, f"@{user} That's not a valid setting. Valid settings: {', '.join(list(self.bomb_settings.keys()))}")
        try:
            value = type(self.bomb_settings[setting])(value)
            if value not in self.valid_bomb_settings[setting]:
                return await self.send_message(channel, "That's not a valid value for this setting.")
            self.bomb_settings[setting] = value
            await self.send_message(channel, f"@{user} The {setting} setting has been changed to {value}")
        except ValueError:
            return await self.send_message(channel, "There was a problem processing the value you gave for the specific setting.")

    @cooldown()
    async def player_list(self, user, channel, args):
        if len(self.party) == 0:
            return
        await self.send_message(channel, f"@{user} Current players playing bomb party: {', '.join(['%s (%s)' %(player, '♥'*lives) for player, lives in self.party.items()])}")

    async def bomb_party_timer(self, channel):
        self.timer = self.bomb_settings['timer']
        self.bomb_start_time = 0
        player = self.turn_order[self.current_player]
        self.party[player] -= 1
        message = f"You ran out of time and now have {self.party[player]} {'♥'*self.party[player]} heart(s) left" if self.party[player] != 0 else "You ran out of time and lost all your lives! YouDied"
        await self.send_message(channel, f"@{player} {message}")
        if await self.check_win(channel):
            return
        await self.next_player(channel)

    async def next_player(self, channel):
        player = self.turn_order[self.current_player]
        while self.party[self.turn_order[self.current_player]] == 0 or self.turn_order[self.current_player] == player:
            self.current_player = 1 + self.current_player if self.current_player != len(self.turn_order)-1 else 0
        self.current_letters = random.choice(self.bomb_party_letters[self.bomb_settings['difficulty']])
        player = self.turn_order[self.current_player]
        await self.send_message(channel, f"@{player} ({'♥'*self.party[player]}) Your string of letters is {self.current_letters} - You have {round(self.timer+self.bomb_settings['minimum_time'])} seconds.")
        self.bomb_start_time = perf_counter()
        self.bomb_party_future = self.set_timed_event(self.timer+self.bomb_settings['minimum_time'], self.bomb_party_timer, channel)

    async def on_bomb_party(self, channel, message):
        player = self.turn_order[self.current_player]
        message = message.lower()
        if message not in self.all_words:
            return
        if message in self.used_words:
            return await self.send_message(channel, f"@{player} ({'♥'*self.party[player]}) That word has already been used this game.")
        if self.current_letters not in message:
            return await self.send_message(channel, f"@{player} ({'♥'*self.party[player]}) That word does not contain your string of letters: {self.current_letters}")
        if len(message) == len(self.current_letters):
            return await self.send_message(channel, f"@{player} ({'♥'*self.party[player]}) You cannot answer with the string of letters itself.")
        self.bomb_party_future.cancel()
        self.timer -= max((0, perf_counter() - self.bomb_start_time - self.bomb_settings['minimum_time']))
        self.used_words.append(message)
        await self.next_player(channel)

    async def check_win(self, channel):
        players_left = [player for player, lives in self.party.items() if lives != 0]
        if len(players_left) != 1:
            return False
        winner = players_left[0]
        money = len(self.party)*100
        self.gamba_data[winner]['money'] += money
        self.database.update_userdata(winner, 'money', self.gamba_data[winner]['money'])
        self.close_bomb_party()
        await self.send_message(channel, f"@{winner} Congratulations on winning the bomb party game! You've won {money} Becky Bucks!")
        return True

    def close_bomb_party(self):
        self.used_words = []
        self.party = {}
        self.bomb_party_future = None
        self.current_player = 0
        self.current_letters = None
        self.bomb_start_time = 0
        self.turn_order = []
        self.timer = self.bomb_time
        self.bomb_settings = {
            "difficulty": "medium",
            "timer": 30,
            "minimum_time": 5,
            "lives": 3,
        }

    @cooldown(cmd_cd=2, user_cd=0)
    async def random_fact(self, user, channel, args):
        fact = requests.get("https://uselessfacts.jsph.pl/random.json?language=en")
        fact.raise_for_status()
        self.send_message(channel, f"Fun fact: {fact.json()['text']}")


bot = Bot()
bot.running = True
while bot.running:
    bot.loop.run_until_complete(bot.start())
