from .base import CommandBot, CommandArg
from ..context import MessageContext
from ..bot import BotMeta

import requests
import random
import html
import logging


log = logging.getLogger(__name__)


class TriviaHelper:
    trivia_info = {
        "hard": 100,
        "medium": 40,
        "easy": 20,
        "penalty": 0.25,
        "decrease": 0.5,
    }
    difficulty_emotes = {
        "easy": "EZ",
        "medium": "monkaS",
        "hard": "pepeMeltdown"
    }

    def __init__(self):
        self.guessed_answers = []
        self.future = None
        self.difficulty = None
        self.answer = None

    def generate_question(self, category=None):
        self.answer = "temp"

        params = {
            "amount": 1,
            "type": "multiple",
        }
        if category:
            params["category"] = category
        try:
            resp = requests.get("https://opentdb.com/api.php", params=params)
        except Exception as e:
            log.exception(e)
            self.answer = None
            return
        if resp.status_code != 200:
            self.answer = None
            return

        try:
            results = resp.json()['results'][0]
        except IndexError:
            self.answer = None
            return
        answers = [results['correct_answer']] + results['incorrect_answers']
        random.shuffle(answers)
        self.answer = answers.index(results['correct_answer']) + 1
        self.difficulty = results['difficulty']

        answer_string = " ".join([html.unescape(f"[{i + 1}] {answers[i]} ") for i in range(len(answers))])
        return f"Difficulty: {self.difficulty} {self.difficulty_emotes[self.difficulty]} "\
               f"Category: {results['category']} veryPog "\
               f"Question: {html.unescape(results['question'])} monkaHmm "\
               f"Answers: {answer_string}"

    def check_guess(self, ctx, guess):
        if guess in self.guessed_answers:
            return
        self.guessed_answers.append(guess)
        if guess == self.answer:
            gain = self.trivia_info[self.difficulty] * (self.trivia_info['decrease'] ** (len(self.guessed_answers) - 1))
            self.reset()
            return f"@{ctx.user.display_name} ✅ You gained {gain} Becky Bucks 5Head Clap", gain
        else:
            loss = self.trivia_info[self.difficulty] * self.trivia_info['penalty']
            message = f"@{ctx.user.display_name} ❌ You lost {loss} Becky Bucks 3Head Clap"
            if len(self.guessed_answers) == 3:
                self.reset()
                message += " No one guessed correctly."
            return message, -loss

    def reset(self, cancel=True):
        self.answer = None
        self.difficulty = None
        self.guessed_answers = []
        if cancel:
            self.future.cancel()

    @property
    def is_in_progress(self):
        return self.answer is not None


class TriviaBot(CommandBot, metaclass=BotMeta):
    __slots__ = ("trivia_helpers",)

    command_manager = CommandBot.command_manager

    def __init__(self):
        self.trivia_helpers = {}

    async def on_message(self, ctx: MessageContext):
        if not self.trivia_helpers[ctx.channel].is_in_progress:
            return

        ascii_msg = "".join((char for char in ctx.message if char.isascii()))

        try:
            num = int(ascii_msg)
            if num in range(1, 5):
                await self.on_answer(ctx, num)
        except ValueError:
            return

    async def on_join(self, ctx: MessageContext):
        self.trivia_helpers[ctx.channel] = TriviaHelper()

    @command_manager.command(
        "trivia",
        "Play a game of multiple choice trivia",
        [
            CommandArg("category")
        ]
    )
    async def trivia(self, ctx):
        if self.trivia_helpers[ctx.channel].is_in_progress:
            return

        args = ctx.get_args("ascii")
        question = self.trivia_helpers[ctx.channel].generate_question(args[0] if len(args) > 0 else None)
        if question is None:
            return await self.send_message(ctx.channel, "An error occurred when attempting to fetch the question...")
        await self.send_message(ctx.channel, question)

        self.trivia_helpers[ctx.channel].future = self.call_later(20, self.on_trivia_finish, ctx.channel)

    async def on_answer(self, ctx, answer):
        result = self.trivia_helpers[ctx.channel].check_guess(ctx, answer)
        if result is None:
            return
        message, amount = result
        await self.send_message(ctx.channel, message)
        await self.db.add_money(ctx.user_id, ctx.sending_user, amount)

    async def on_trivia_finish(self, channel):
        self.trivia_helpers[channel].reset(cancel=False)
        await self.send_message(channel, "Time has run out for the trivia.")
