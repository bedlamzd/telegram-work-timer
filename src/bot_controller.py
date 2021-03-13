from telegram import Update
from telegram.ext import Updater, Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext


class MyBot:
    __updater: Updater
    __dispatcher: Dispatcher

    def __init__(self, token):
        self.__updater = Updater(token)
        self.__dispatcher = self.__updater.dispatcher
        self.__register_handlers()

    def __register_handlers(self):
        self.__dispatcher.add_handler(CommandHandler('start', self.__start_command))
        self.__dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, self.__echo_message))

    @staticmethod
    def __start_command(update: Update, ctx: CallbackContext):
        update.message.reply_text('Hello and welcome!')

    @staticmethod
    def __echo_message(update: Update, ctx: CallbackContext):
        update.message.reply_text(update.message.text)

    def start(self):
        self.__updater.start_polling()
        self.__updater.idle()
