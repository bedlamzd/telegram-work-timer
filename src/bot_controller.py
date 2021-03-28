from dataclasses import dataclass
import enum
from enum import Enum
from typing import Any, Callable, cast, Dict, List, NewType, Optional, Tuple, Union

from telegram import Update
from telegram.ext import Updater, Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

TimerID = NewType('TimerID', str)
ChatID = NewType('ChatID', int)
JobName = NewType('JobName', str)


class TimerRoutine:
    class CycleType(Enum):
        RELAX = enum.auto()
        WORK = enum.auto()

    def __init__(self,
                 total_time: float, work_time: float, relax_time: float,
                 work_callback: Callable, relax_callback: Callable):
        self.__work_time = work_time
        self.__relax_time = relax_time
        self.__total_time = total_time

        self.__work_callback = work_callback
        self.__relax_callback = relax_callback

        self.__work_cycles_counter = 0
        self.__relax_cycles_counter = 0

        self.__current_cycle = self.CycleType.WORK
        self.__current_cycle_done = False


    def get_next_callback_and_interval(self) -> Tuple[Callable, float]:
        if self.current_cycle == self.CycleType.WORK:
            return self.__work_callback, self.__work_time
        else:
            return self.__relax_callback, self.__relax_time

    @property
    def is_over(self) -> bool:
        return self.__work_cycles_counter * self.__work_time + self.__relax_cycles_counter * self.__relax_time >= self.__total_time

    @property
    def current_cycle(self) -> CycleType:
        return self.__current_cycle

    def complete_cycle(self):
        self.__current_cycle_done = True

    def increment_cycle(self):
        if self.current_cycle == self.CycleType.WORK:
            self.__current_cycle = self.CycleType.RELAX
            self.__work_cycles_counter += 1
        else:
            self.__current_cycle = self.CycleType.WORK
            self.__relax_cycles_counter += 1
        self.__current_cycle_done = False

    @property
    def is_cycle_done(self) -> bool:
        return self.__current_cycle_done


@dataclass
class UserSettings:
    total_time: float = 3600 * 8
    work_time: float = 3600
    relax_time: float = 1200
    reminder_interval: float = 300
    work_end_text: str = 'Work time has ended!'
    relax_end_text: str = 'Relax time has ended!'
    reminder_text: str = 'Did you hear me?! Interval has passed!'
    confirm_on_no_jobs_text: str = 'Nothing to confirm, all intervals are ended.'
    end_routine_text: str = "Today's routine has ended, good job!"
    unset_on_no_jobs_text: str = "Nothing to unset, all routines complete."
    unset_routine_text: str = "Routine unset successfully."
    pause_on_no_jobs_text: str = "Nothing to pause, all routines complete."
    pause_routine_text: str = "Paused routine successfully."
    resume_on_no_jobs_text: str = "Nothing to resume, all routines complete."
    resume_routine_text: str = "Resumed successfully."
    status_on_no_jobs_text: str = "No routines."


class MyBot:
    __updater: Updater
    __dispatcher: Dispatcher

    known_users: List[ChatID] = list()
    chat_id_to_job_name: Dict[ChatID, JobName] = dict()
    chat_id_to_user_settings: Dict[ChatID, UserSettings] = dict()
    chat_id_to_timer_routine: Dict[ChatID, TimerRoutine] = dict()

    @property
    def job_name_to_chat_id(self) -> Dict[JobName, ChatID]:
        return {v: k for k, v in self.chat_id_to_job_name.items()}

    def __init__(self, token):
        self.__updater = Updater(token)
        self.__dispatcher = self.__updater.dispatcher
        self.__register_handlers()

    def __register_handlers(self):
        self.__dispatcher.add_handler(CommandHandler('start', self.__start_command))
        self.__dispatcher.add_handler(CommandHandler('set', self.__set_timer))
        self.__dispatcher.add_handler(CommandHandler('unset', self.__unset_timer))
        self.__dispatcher.add_handler(CommandHandler('pause', self.__pause_timer))
        self.__dispatcher.add_handler(CommandHandler('resume', self.__resume_timer))
        self.__dispatcher.add_handler(CommandHandler('confirm', self.__confirm_command))
        self.__dispatcher.add_handler(CommandHandler('status', self.__status_command))
        self.__dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, self.__echo_message))

    def __start_command(self, update: Update, ctx: CallbackContext):
        update.message.reply_text('Hello and welcome!')
        chat_id: ChatID = ChatID(update.message.chat_id)
        self.known_users.append(chat_id)
        self.chat_id_to_user_settings.setdefault(chat_id, UserSettings())

    @staticmethod
    def __echo_message(update: Update, ctx: CallbackContext):
        update.message.reply_text(update.message.text)

    @staticmethod
    def __parse_timer_args(args: List[str]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        if args and (any(not arg.isnumeric() for arg in args) or len(args) > 3):
            raise ValueError  # also handles empty list and ensures at least one value is present
        args = (float(_) for _ in args)
        return tuple(next(args, None) for _ in range(3))

    def __set_user_interval_settings(self,
                                     chat_id: ChatID,
                                     work_time: Optional[float] = None,
                                     relax_time: Optional[float] = None,
                                     total_time: Optional[float] = None):
        settings = self.chat_id_to_user_settings[chat_id]
        if work_time is not None:
            settings.work_time = work_time
        if relax_time is not None:
            settings.relax_time = relax_time
        if total_time is not None:
            settings.total_time = total_time

    def __set_timer(self, update: Update, ctx: CallbackContext):
        chat_id = ChatID(update.message.chat_id)
        if chat_id not in self.known_users:
            update.message.reply_text("Unknown user!")
            return

        try:
            work_time, relax_time, total_time = self.__parse_timer_args(ctx.args)
            self.__set_user_interval_settings(chat_id, work_time, relax_time, total_time)
        except ValueError:
            cmd = update.message.text.split(maxsplit=1)
            update.message.reply_text(f'"{cmd}" takes only up to three numeric argument.')
            return

        settings = self.chat_id_to_user_settings[chat_id]
        self.chat_id_to_job_name[chat_id] = str(chat_id)
        self.chat_id_to_timer_routine[chat_id] = TimerRoutine(settings.total_time, settings.work_time,
                                                              settings.relax_time,
                                                              self.__work_time_end_callback,
                                                              self.__relax_time_end_callback)
        next_callback, next_interval = self.chat_id_to_timer_routine[chat_id].get_next_callback_and_interval()

        update.message.reply_text(f'Timer started!\n'
                                  f'Work time: {settings.work_time}\n'
                                  f'Relax time: {settings.relax_time}\n'
                                  f'Total time: {settings.total_time}\n'
                                  f'Reminder interval: {settings.reminder_interval}')
        ctx.job_queue.run_once(next_callback, next_interval, name=self.chat_id_to_job_name[chat_id])

    def __work_time_end_callback(self, ctx: CallbackContext):
        chat_id: ChatID = self.job_name_to_chat_id.get(ctx.job.name)
        if chat_id is None:
            print('WTF')
            return
        settings = self.chat_id_to_user_settings[chat_id]
        self.chat_id_to_timer_routine[chat_id].complete_cycle()
        ctx.bot.send_message(chat_id=chat_id, text=settings.work_end_text)
        ctx.job_queue.run_repeating(self.__reminder_callback, settings.reminder_interval, name=ctx.job.name)

    def __relax_time_end_callback(self, ctx: CallbackContext):
        chat_id: ChatID = self.job_name_to_chat_id.get(ctx.job.name)
        if chat_id is None:
            print('WTF')
            return
        settings = self.chat_id_to_user_settings[chat_id]
        self.chat_id_to_timer_routine[chat_id].complete_cycle()
        ctx.bot.send_message(chat_id=chat_id, text=settings.relax_end_text)
        ctx.job_queue.run_repeating(self.__reminder_callback, settings.reminder_interval, name=ctx.job.name)

    def __reminder_callback(self, ctx: CallbackContext):
        chat_id: ChatID = self.job_name_to_chat_id.get(ctx.job.name)
        if chat_id is None:
            print('WTF')
            return
        settings = self.chat_id_to_user_settings.get(chat_id)
        ctx.bot.send_message(chat_id=chat_id, text=settings.reminder_text)

    def __confirm_command(self, update: Update, ctx: CallbackContext):
        chat_id = ChatID(update.message.chat_id)
        if chat_id not in self.known_users:
            update.message.reply_text("Unknown user!")
            return

        settings = self.chat_id_to_user_settings.get(chat_id)
        job_name = self.chat_id_to_job_name.get(chat_id)
        timer_routine = self.chat_id_to_timer_routine.get(chat_id)

        if job_name is None:
            update.message.reply_text(settings.confirm_on_no_jobs_text)
            return

        if timer_routine.is_cycle_done:
            timer_routine.increment_cycle()
            for job in ctx.job_queue.get_jobs_by_name(job_name):
                job.schedule_removal()
                del self.chat_id_to_job_name[chat_id]

        if timer_routine.is_over:
            update.message.reply_text(settings.end_routine_text)
            del self.chat_id_to_timer_routine[chat_id]
            return

        self.chat_id_to_job_name[chat_id] = str(chat_id)
        next_callback, next_interval = timer_routine.get_next_callback_and_interval()
        ctx.job_queue.run_once(next_callback, next_interval, name=self.chat_id_to_job_name[chat_id])

    def __unset_timer(self, update: Update, ctx: CallbackContext):
        chat_id = ChatID(update.message.chat_id)
        if chat_id not in self.known_users:
            update.message.reply_text("Unknown user!")
            return

        settings = self.chat_id_to_user_settings.get(chat_id)
        job_name = self.chat_id_to_job_name.get(chat_id)
        if job_name is None:
            update.message.reply_text(settings.unset_on_no_jobs_text)
            return
        for job in ctx.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
            del self.chat_id_to_job_name[chat_id]
        update.message.reply_text(settings.unset_routine_text)

    def __pause_timer(self, update: Update, ctx: CallbackContext):
        chat_id = ChatID(update.message.chat_id)
        if chat_id not in self.known_users:
            update.message.reply_text("Unknown user!")
            return

        settings = self.chat_id_to_user_settings.get(chat_id)
        job_name = self.chat_id_to_job_name.get(chat_id)
        if job_name is None:
            update.message.reply_text(settings.pause_on_no_jobs_text)
            return
        for job in ctx.job_queue.get_jobs_by_name(job_name):
            job.enabled = False
        update.message.reply_text(settings.pause_routine_text)

    def __resume_timer(self, update: Update, ctx: CallbackContext):
        chat_id = ChatID(update.message.chat_id)
        if chat_id not in self.known_users:
            update.message.reply_text("Unknown user!")
            return

        settings = self.chat_id_to_user_settings.get(chat_id)
        job_name = self.chat_id_to_job_name.get(chat_id)
        if job_name is None:
            update.message.reply_text(settings.resume_on_no_jobs_text)
            return
        for job in ctx.job_queue.get_jobs_by_name(job_name):
            job.enabled = True
        update.message.reply_text(settings.resume_routine_text)

    def __status_command(self, update: Update, ctx: CallbackContext):
        chat_id: ChatID = ChatID(update.message.chat_id)
        if chat_id not in self.known_users:
            update.message.reply_text("Unknown user!")
            return

        settings = self.chat_id_to_user_settings[chat_id]
        job_name = self.chat_id_to_job_name.get(chat_id)
        if job_name is None:
            update.message.reply_text(settings.status_on_no_jobs_text)
            return

        for job in ctx.job_queue.get_jobs_by_name(job_name):
            if job.removed:
                continue
            update.message.reply_text(
                    f'Routine is {"active" if job.enabled else "paused"} '
                    f'and will go off at {job.next_t}.'
                    )

    def start(self):
        self.__updater.start_polling()
        self.__updater.idle()
