import asyncio
import random
import time
from aiogram.dispatcher.filters import Command
import aiosqlite
from aiogram import types
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Замените на ваш токен
API_TOKEN = '8152607752:AAFhdDLKJEFKtPMCaZtS6oqgSRnf6Go1-fQ'
DATABASE = 'database.db'  # Путь к вашей базе данных
ALLOWED_CHAT_ID = -1002281073520
LOD_CHAT = -1002297311385
# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class DuelStates(StatesGroup):
    waiting_for_accept = State()
    battling = State()

async def db_setup():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, coins INTEGER DEFAULT 0, last_bonus INTEGER DEFAULT 0, last_duel INTEGER DEFAULT 0)')
        await db.execute('CREATE TABLE IF NOT EXISTS duels (id INTEGER PRIMARY KEY, challenger_id INTEGER, opponent_id INTEGER, bet INTEGER, accepted INTEGER, winner_id INTEGER)')
        await db.commit()


@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    if message.chat.id != ALLOWED_CHAT_ID:
        await message.answer("❌ Извините, этот бот можно использовать только в разрешенном чате.")
    else:
        async with aiosqlite.connect(DATABASE) as db:
            await db.execute('INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)', (message.from_user.id, message.from_user.username))
            await db.commit()
        await message.answer("🔥Добро пожаловать в бота!\nВведите '/хелп' для списка доступных команд.")


@dp.message_handler(regexp='хелп')
async def help(message: types.Message):
    if message.chat.id != ALLOWED_CHAT_ID:
        await message.answer("❌ Извините, этот бот можно использовать только в разрешенном чате.")
    else:
        text = ("📃 Список доступных команд:\n\n"
                "/start - Зарегистрироваться в боте.\n"
                "/хелп - Вывести это сообщение.\n\n"
                "Еб - Получить бонус (раз в 24 часа). Синонимы: \'еб\'.\n"
                "Дуэль - Пригласить игрока на дуэль. Синонимы: \'дуэль\'.\n"
                "Балик - Вывести свой баланс Kamenk-coins. Синонимы: \'балик\'.\n")
        await message.answer(text)


@dp.message_handler(regexp='Еб|еб')
async def bonus_command(message: types.Message):
    if message.chat.id != ALLOWED_CHAT_ID:
        await message.answer("❌ Извините, этот бот можно использовать только в разрешенном чате.")
    else:
        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute('SELECT coins, last_bonus FROM users WHERE id = ?', (message.from_user.id,))
            row = await cursor.fetchone()
            
            if row is None:
                await message.answer("❗ Сначала зарегистрируйтесь с помощью /start.")
                return
            
            coins, last_bonus = row
            current_time = int(time.time())
            if current_time - last_bonus < 86400:
                await message.answer("🔥 Бонус уже был получен. Вы можете получать бонусы только один раз в сутки.")
                return
            
            bonus_amount = random.randint(10, 20)
            await db.execute('UPDATE users SET coins = coins + ?, last_bonus = ? WHERE id = ?', (bonus_amount, current_time, message.from_user.id))
            await db.commit()
            
            await message.answer(f"🪙 Вы получили {bonus_amount} Kamenk-coins.")

@dp.message_handler(regexp='дуэль|Дуэль')
async def duel_command(message: types.Message, state: FSMContext):
    if message.chat.id != ALLOWED_CHAT_ID:
        await message.answer("❌ Извините, этот бот можно использовать только в разрешенном чате.")
    else:
        parts = message.text.split()
        
        if len(parts) < 3:
            await message.answer("❗ Формат: /дуэль @username количество-Kamenk-coin")
            return

        opponent_username = parts[1].strip().lstrip('@/')  # Удаляем '@' если есть

        try:
            bet = int(parts[2])
        except ValueError:
            await message.answer("🪙 Количество Kamenk-coin должно быть числом.")
            return

        if bet < 5:
            await message.answer("🪙 Ставка на дуэль должна быть не менее 5 Kamenk-coins.")
            return

        if opponent_username == message.from_user.username:
            await message.answer("❌ Вы не можете вызвать сами себя на дуэль.")
            return

        current_time = int(time.time())

        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute('SELECT coins, last_duel FROM users WHERE id = ?', (message.from_user.id,))
            row = await cursor.fetchone()
            
            if row is None:
                await message.answer("❗ Сначала зарегистрируйтесь с помощью /start.")
                return

            user_coins, last_duel = row
            
            if user_coins < bet:
                await message.answer("❌ У вас недостаточно Kamenk-coin для этой ставки.")
                return

            # Проверка времени последнего использования команды
            if current_time - last_duel < 20:  # 300 секунд = 5 минут
                remaining_time = 20 - (current_time - last_duel)
                await message.answer(f"❗ Вы можете использовать команду /дуэль снова через {remaining_time} секунд.")
                return

            # Обновляем время последнего использования команды
            await db.execute('UPDATE users SET last_duel = ? WHERE id = ?', (current_time, message.from_user.id))

            opponent_cursor = await db.execute('SELECT id FROM users WHERE username = ?', (opponent_username,))
            opponent_row = await opponent_cursor.fetchone()

            if opponent_row is None:
                await message.answer(f"❌ Пользователь @{opponent_username} не найден, или не зарегистрирован в боте.")
                return

            await db.execute(
                'INSERT INTO duels (challenger_id, opponent_id, bet, accepted) VALUES (?, ?, ?, ?)',
                (message.from_user.id, opponent_row[0], bet, 0)
            )
            await db.commit()

            duel_id = (await (await db.execute('SELECT last_insert_rowid()')).fetchone())[0]

            await bot.send_message(LOD_CHAT,f"Дуэль создана! ID дуэли: {duel_id}")

        keyboard = InlineKeyboardMarkup(row_width=2)
        accept_button = InlineKeyboardButton("✔️ Принять", callback_data=f'accept_duel:{duel_id}:{opponent_row[0]}')
        decline_button = InlineKeyboardButton("❌ Отказаться", callback_data=f'decline_duel:{duel_id}:{opponent_row[0]}')
        keyboard.add(accept_button, decline_button)

        await state.update_data(duel_id=duel_id)
        await message.answer(f"🔊 Внимание @{opponent_username}, вы получили вызов на дуэль!\n🪙 Ставка: {bet} Kamenk-coin", reply_markup=keyboard)


async def start_duel(duel_id, callback_query):
    if callback_query.message is None:  # Проверка на наличие сообщения
        return

    chat_id = callback_query.message.chat.id

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute('SELECT challenger_id, opponent_id, bet FROM duels WHERE id = ?', (duel_id,))
        duel_info = await cursor.fetchone()

    if duel_info is None:
        await bot.send_message(chat_id, "❌ Дуэль не найдена.")
        return  # Завершение функции, чтобы избежать дальнейших действий

    challenger_id, opponent_id, bet = duel_info
  
    # Получаем имена игроков
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute('SELECT username FROM users WHERE id IN (?, ?)', (challenger_id, opponent_id))
        usernames = await cursor.fetchall()
    
    challenger_username = usernames[0][0]
    opponent_username = usernames[1][0]
    
    health = {
        challenger_id: 100,
        opponent_id: 100
    }

    turn = challenger_id  # Начинает первый
    battle_result = []

    await bot.send_message(chat_id, f"Дуэль началась между @{challenger_username} и @{opponent_username}!")

    while health[challenger_id] > 0 and health[opponent_id] > 0:
        damage = random.randint(5, 50)
        health[turn] -= damage
        
        battle_message = f"⚔️ Игрок {challenger_username if turn == challenger_id else opponent_username} нанес {damage} урона.\n\n🛡️ Осталось здоровья у {opponent_username}: {health[challenger_id]}\n🛡️ Осталось здоровья у {challenger_username}: {health[opponent_id]}."
        battle_result.append(battle_message)
        await bot.send_message(chat_id, battle_message)

        await asyncio.sleep(2)

        if health[challenger_id] <= 0 or health[opponent_id] <= 0:
            winner = challenger_id if health[opponent_id] <= 0 else opponent_id
            loser = challenger_id if winner == opponent_id else opponent_id
            break

        turn = opponent_id if turn == challenger_id else challenger_id

    await finish_duel(duel_id, winner, loser, bet, chat_id)

async def finish_duel(duel_id, winner_id, loser_id, bet, chat_id):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute('UPDATE users SET coins = coins + ? WHERE id = ?', (bet, loser_id))
        await db.execute('UPDATE users SET coins = coins - ? WHERE id = ?', (bet, winner_id))
        await db.execute('DELETE FROM duels WHERE id = ?', (duel_id,))
        await db.commit()

        cursor = await db.execute('SELECT username FROM users WHERE id = ?', (loser_id,))
        winner_data = await cursor.fetchone()
        winner_username = winner_data[0] if winner_data else "Unknown User"

    await bot.send_message(chat_id, f"🏅 Победитель: @{winner_username}!\n🪙 Ставка была {bet}")

@dp.callback_query_handler(lambda c: c.data.startswith('accept_duel:'))
async def accept_duel(callback_query: types.CallbackQuery):
    duel_id, opponent_id = map(int, callback_query.data.split(':')[1:])

    # Проверка, что пользователь, принявший дуэль, является противником
    if callback_query.from_user.id != opponent_id:
        await callback_query.answer("❌ Это не для вас!")
        return
    
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute('UPDATE duels SET accepted = 1 WHERE id = ?', (duel_id,))
        await db.commit()

    await callback_query.answer("✔️ Вы приняли вызов на дуэль!")
    await start_duel(duel_id, callback_query)

@dp.callback_query_handler(lambda c: c.data.startswith('decline_duel:'))
async def decline_duel(callback_query: types.CallbackQuery):
    duel_id, opponent_id = map(int, callback_query.data.split(':')[1:])

    # Проверка, что пользователь, отказавший от дуэли, является противником
    if callback_query.from_user.id != opponent_id:
        await callback_query.answer("❌ Это не для вас!")
        return

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute('DELETE FROM duels WHERE id = ?', (duel_id,))
        await db.commit()

    # Удаление сообщения с приглашением на дуэль
    await callback_query.message.delete()
    
    await callback_query.answer("❌ Вы отказались от дуэли.")


@dp.message_handler(regexp='Балик|балик')
async def balance_command(message: types.Message):
    if message.chat.id != ALLOWED_CHAT_ID:
        await message.answer("❌ Извините, этот бот можно использовать только в разрешенном чате.")
    else:
        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute('SELECT coins FROM users WHERE id = ?', (message.from_user.id,))
            row = await cursor.fetchone()
            if row is None:
                await message.answer("❗ Сначала зарегистрируйтесь с помощью /start.")
                return
            await message.answer(f"🪙 Ваш баланс: {row[0]} Kamenk-coins.")


# Запускаем бота
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db_setup())
    executor.start_polling(dp, skip_updates=True)
