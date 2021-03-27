import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, cast, Dict, List, NewType, Optional, Union

from telegram import Update
from telegram.ext import Updater, Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

TimerID = NewType('TimerID', str)
ChatID = NewType('ChatID', int)
JobName = NewType('JobName', str)


@dataclass
class UserSettings:
    work_interval: float = 3600
    relax_interval: float = 1200
    reminder_interval: float = 3
    work_end_text: str = 'Work time has ended!'
    relax_end_text: str = 'Relax time has ended!'
    reminder_text: str = 'Did you hear me?! Interval has passed!'
    confirm_on_no_jobs_text: str = 'Nothing to confirm, all intervals are ended.'


class MyBot:
    __updater: Updater
    __dispatcher: Dispatcher

    chat_id_to_job_name: Dict[ChatID, JobName] = dict()
    chat_id_to_user_settings: Dict[ChatID, UserSettings] = dict()

    @property
    def job_name_to_chat_id(self) -> Dict[JobName, ChatID]:
        return {v: k for k, v in self.chat_id_to_job_name.items()}

    def __init__(self, token):
        self.__updater = Updater(token)
        self.__dispatcher = self.__updater.dispatcher
        self.__register_handlers()

    def __register_handlers(self):
        self.__dispatcher.add_handler(CommandHandler('start', self.__start_command))
        self.__dispatcher.add_handler(CommandHandler('set', self.__start_timer))
        self.__dispatcher.add_handler(CommandHandler('confirm', self.__confirm_command))
        self.__dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, self.__echo_message))

    def __start_command(self, update: Update, ctx: CallbackContext):
        update.message.reply_text('Hello and welcome!')
        self.chat_id_to_user_settings.setdefault(ChatID(update.message.chat_id), UserSettings())

    @staticmethod
    def __echo_message(update: Update, ctx: CallbackContext):
        update.message.reply_text(update.message.text)

    def __start_timer(self, update: Update, ctx: CallbackContext):
        def get_interval(args: List[str]):
            if len(args) != 1:
                raise ValueError
            if not (arg := args[0]).isnumeric():
                raise ValueError
            return int(arg)

        chat_id = ChatID(update.message.chat_id)
        try:
            interval = get_interval(ctx.args)
            settings = self.chat_id_to_user_settings[chat_id]
            settings.work_interval = interval
        except ValueError:
            cmd = update.message.text.split(maxsplit=1)
            update.message.reply_text(f'"{cmd}" takes only one numeric argument.')
            return
        self.chat_id_to_job_name[chat_id] = str(chat_id)
        update.message.reply_text(f'Timer started!\n'
                                  f'Work interval: {settings.work_interval}\n'
                                  f'Relax interval: {settings.relax_interval}\n'
                                  f'Reminder interval: {settings.reminder_interval}')
        ctx.job_queue.run_once(self.__work_interval_callback, interval, name=self.chat_id_to_job_name[chat_id])

    def __work_interval_callback(self, ctx: CallbackContext):
        chat_id: ChatID = self.job_name_to_chat_id.get(ctx.job.name)
        if chat_id is None:
            print('WTF')
            return
        settings = self.chat_id_to_user_settings.get(chat_id)
        ctx.bot.send_message(chat_id=chat_id, text=settings.work_end_text)
        ctx.job_queue.run_repeating(self.__reminder_interval_callback, settings.reminder_interval, name=ctx.job.name)

    def __reminder_interval_callback(self, ctx: CallbackContext):
        chat_id: ChatID = self.job_name_to_chat_id.get(ctx.job.name)
        if chat_id is None:
            print('WTF')
            return
        settings = self.chat_id_to_user_settings.get(chat_id)
        ctx.bot.send_message(chat_id=chat_id, text=settings.reminder_text)

    def __relax_interval_callback(self, ctx: CallbackContext):
        pass

    def __confirm_command(self, update: Update, ctx: CallbackContext):
        chat_id = ChatID(update.message.chat_id)
        settings = self.chat_id_to_user_settings.get(chat_id)
        job_name = self.chat_id_to_job_name.get(chat_id)
        if job_name is None:
            update.message.reply_text(settings.confirm_on_no_jobs_text)
            return
        for job in ctx.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

    @staticmethod
    def __unset_timer(update: Update, ctx: CallbackContext):
        pass

    def start(self):
        self.__updater.start_polling()
        self.__updater.idle()
