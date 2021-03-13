import dotenv
import os
from bot_controller import MyBot


if __name__ == '__main__':
    dotenv.load_dotenv(f'../.env')

    bot = MyBot(os.getenv('TOKEN'))

    bot.start()
