import os
import logging
import asyncio
from aiogram import Bot, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    LabeledPrice, 
    FSInputFile, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    PreCheckoutQuery
)
from aiogram import Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# Импорт конфигурации
from config import (
    TOKEN, SUPPORT_USERNAME, ADMIN_IDS, conn, cursor, 
    products, get_stars_balance, get_purchases_count, 
    get_stats, update_stats, get_notifications_enabled, 
    set_notifications_enabled, load_products
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Состояния для FSM
class Form(StatesGroup):
    add_product_name = State()
    add_product_stars_price = State()
    add_product_desc = State()
    add_product_file = State()
    edit_product_select = State()
    edit_product_field = State()
    edit_product_value = State()
    delete_product_confirm = State()
    deposit_stars_amount = State()

# Главное меню
def get_main_menu():
    builder = ReplyKeyboardBuilder()
    builder.add(
        KeyboardButton(text="🛍 Каталог товаров"),
        KeyboardButton(text="👤 Личный кабинет"),
        KeyboardButton(text="🆘 Техподдержка")
    )
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# Админ меню
def get_admin_menu():
    builder = ReplyKeyboardBuilder()
    builder.add(
        KeyboardButton(text="📦 Управление товарами"),
        KeyboardButton(text="📊 Статистика"),
        KeyboardButton(text="📩 Уведомления"),
        KeyboardButton(text="🔙 В главное меню")
    )
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

# Меню уведомлений
def get_notifications_menu(user_id):
    enabled_purchase = get_notifications_enabled(user_id) & 1  # Покупки
    enabled_deposit = (get_notifications_enabled(user_id) >> 1) & 1  # Пополнения
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(
            text=f"🔔 Уведомления о покупке {'включены' if enabled_purchase else 'выключены'}",
            callback_data="toggle_purchase_notifications"
        ),
        InlineKeyboardButton(
            text=f"🔔 Уведомления об оплате {'включены' if enabled_deposit else 'выключены'}",
            callback_data="toggle_deposit_notifications"
        ),
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")
    )
    builder.adjust(1)
    return builder.as_markup()

# Меню управления товарами
def get_products_menu():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="➕ Добавить товар", callback_data="add_product"),
        InlineKeyboardButton(text="✏️ Редактировать товар", callback_data="edit_product"),
        InlineKeyboardButton(text="🗑 Удалить товар", callback_data="delete_product"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")
    )
    builder.adjust(1)
    return builder.as_markup()

# Команда /start
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    update_stats()  # Обновляем статистику при первом входе
    
    if user_id in ADMIN_IDS:
        await message.answer("👋 Добро пожаловать в админ-панель!", reply_markup=get_admin_menu())
        return
    
    stars_balance = get_stars_balance(user_id)
    text = (
        "🛒 Добро пожаловать в магазин цифровых товаров!\n"
        f"⭐ Ваши звезды: {stars_balance}\n\n"
        "Используйте кнопки ниже для навигации:"
    )
    
    await message.answer(text, reply_markup=get_main_menu())

# Команда /givestars
@dp.message(Command("givestars"))
async def give_stars(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("❌ Использование: /givestars <user_id> количество (например, /givestars 123456789 100)")
            return
        
        user_id = parts[1]
        amount = int(parts[2])
        
        if amount <= 0:
            await message.answer("❌ Количество звёзд должно быть больше 0.")
            return
        
        try:
            user_id = int(user_id)
        except ValueError:
            await message.answer("❌ User ID должен быть целым числом. Используйте /givestars <user_id> количество.")
            return
        
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        cursor.execute("UPDATE users SET stars_balance = stars_balance + ? WHERE user_id=?", (amount, user_id))
        conn.commit()
        
        await bot.send_message(
            chat_id=user_id,
            text=f"🎁 Вам начислено {amount} ⭐ в подарок! Новый баланс: {get_stars_balance(user_id)}"
        )
        
        await message.answer(f"✅ Пользователю с ID {user_id} выдано {amount} звезд. Новый баланс: {get_stars_balance(user_id)}")
    except ValueError:
        await message.answer("❌ Неверный формат количества. Введите целое число.")
    except Exception as e:
        logger.error(f"Ошибка при выдаче звезд: {e}")
        await message.answer("⚠️ Произошла ошибка. Проверьте формат команды или обратитесь в поддержку.")

# Команда /starsdelete
@dp.message(Command("starsdelete"))
async def delete_stars(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("❌ Использование: /starsdelete <user_id> количество (например, /starsdelete 123456789 100)")
            return
        
        user_id = parts[1]
        amount = int(parts[2])
        
        if amount <= 0:
            await message.answer("❌ Количество звёзд должно быть больше 0.")
            return
        
        try:
            user_id = int(user_id)
        except ValueError:
            await message.answer("❌ User ID должен быть целым числом. Используйте /starsdelete <user_id> количество.")
            return
        
        current_balance = get_stars_balance(user_id)
        if current_balance < amount:
            await message.answer(f"❌ Недостаточно звезд у пользователя. Текущий баланс: {current_balance}")
            return
        
        cursor.execute("UPDATE users SET stars_balance = stars_balance - ? WHERE user_id=?", (amount, user_id))
        conn.commit()
        
        await message.answer(f"✅ У пользователя с ID {user_id} списано {amount} звезд. Новый баланс: {get_stars_balance(user_id)}")
    except ValueError:
        await message.answer("❌ Неверный формат количества. Введите целое число.")
    except Exception as e:
        logger.error(f"Ошибка при списании звезд: {e}")
        await message.answer("⚠️ Произошла ошибка. Проверьте формат команды или обратитесь в поддержку.")

# Админ панель
@dp.message(F.text == "📦 Управление товарами")
async def manage_products(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    
    await message.answer("📦 Управление товарами:", reply_markup=get_products_menu())

# Статистика
@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    
    update_stats()
    total_purchases, total_stars_deposited, total_users = get_stats()
    text = (
        "📊 Статистика:\n"
        f"🛍 Количество покупок: {total_purchases}\n"
        f"⭐ Всего пополнено звёзд: {total_stars_deposited}\n"
        f"👥 Количество пользователей: {total_users}"
    )
    await message.answer(text, reply_markup=get_admin_menu())

# Уведомления
@dp.message(F.text == "📩 Уведомления")
async def manage_notifications(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    
    await message.answer("📩 Настройка уведомлений:", reply_markup=get_notifications_menu(message.from_user.id))

@dp.callback_query(F.data.in_(["toggle_purchase_notifications", "toggle_deposit_notifications"]))
async def toggle_notifications(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    current_state = get_notifications_enabled(user_id)
    if callback.data == "toggle_purchase_notifications":
        new_state = current_state ^ 1  # Инверсия бита для покупок
    else:  # toggle_deposit_notifications
        new_state = current_state ^ 2  # Инверсия бита для пополнений
    set_notifications_enabled(user_id, new_state)
    await callback.message.edit_text(
        "📩 Настройка уведомлений:",
        reply_markup=get_notifications_menu(user_id)
    )
    await callback.answer()

# Добавление товара
@dp.callback_query(F.data == "add_product")
async def add_product_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ У вас нет доступа.")
        return
    
    await callback.message.answer("Введите название товара:")
    await state.set_state(Form.add_product_name)
    await callback.answer()

@dp.message(Form.add_product_name)
async def add_product_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите цену товара в звездах (например: 1000):")
    await state.set_state(Form.add_product_stars_price)

@dp.message(Form.add_product_stars_price)
async def add_product_stars_price(message: types.Message, state: FSMContext):
    try:
        stars_price = int(message.text)
        if stars_price <= 0:
            await message.answer("❌ Цена должна быть больше 0")
            return
            
        await state.update_data(stars_price=stars_price)
        await message.answer("Введите описание товара:")
        await state.set_state(Form.add_product_desc)
    except ValueError:
        await message.answer("❌ Неверный формат цены. Введите целое число, например: 1000")

@dp.message(Form.add_product_desc)
async def add_product_desc(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await message.answer("Отправьте файл для товара (документ, архив и т.д.):")
    await state.set_state(Form.add_product_file)

@dp.message(Form.add_product_file, F.document)
async def add_product_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    if not os.path.exists("products_files"):
        os.makedirs("products_files")
    
    file_id = message.document.file_id
    file = await bot.get_file(file_id)
    file_path = f"products_files/{file_id}_{message.document.file_name}"
    await bot.download_file(file.file_path, file_path)
    
    cursor.execute("SELECT MAX(id) FROM products")
    max_id = cursor.fetchone()[0] or 0
    new_id = max_id + 1
    
    cursor.execute(
        "INSERT INTO products (id, name, stars_price, desc, file_path) VALUES (?, ?, ?, ?, ?)",
        (new_id, data['name'], data['stars_price'], data['desc'], file_path)
    )
    conn.commit()
    
    global products
    products = load_products()
    
    await message.answer(f"✅ Товар \"{data['name']}\" успешно добавлен!", reply_markup=get_admin_menu())
    await state.clear()

# Редактирование товара
@dp.callback_query(F.data == "edit_product")
async def edit_product_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ У вас нет доступа.")
        return
    
    if not products:
        await callback.message.answer("❌ Нет товаров для редактирования.")
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for id, product in products.items():
        builder.add(InlineKeyboardButton(
            text=f"{product['name']} - {product['stars_price']}⭐", 
            callback_data=f"edit_select_{id}"
        ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        "Выберите товар для редактирования:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_select_"))
async def edit_product_select(callback: types.CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data="edit_field_name")],
        [InlineKeyboardButton(text="⭐ Цена", callback_data="edit_field_stars_price")],
        [InlineKeyboardButton(text="📝 Описание", callback_data="edit_field_desc")],
        [InlineKeyboardButton(text="📁 Файл", callback_data="edit_field_file")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="edit_product")]
    ])
    
    await callback.message.edit_text(
        "Выберите что хотите изменить:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_field_"))
async def edit_product_field(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.replace("edit_field_", "")  # Упрощаем извлечение поля
    logger.debug(f"Получено callback_data: {callback.data}, извлечено поле: {field}")
    valid_fields = {"name": "Название", "stars_price": "Цена", "desc": "Описание", "file": "Файл"}
    
    if field not in valid_fields:
        logger.error(f"Некорректное поле для редактирования: {field} (callback_data: {callback.data})")
        await callback.answer("❌ Неверное поле для редактирования. Обратитесь в поддержку.")
        return
    
    await state.update_data(field=field)
    
    if field == "file":
        await callback.message.answer("Отправьте новый файл для товара:")
    else:
        await callback.message.answer(f"Введите новое значение для {valid_fields[field]}:")
    
    await state.set_state(Form.edit_product_value)
    await callback.answer()

@dp.message(Form.edit_product_value)
async def edit_product_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get('product_id')
    
    if not product_id:
        await message.answer("❌ Ошибка: ID товара не найден. Вернитесь в меню управления товарами.")
        await state.clear()
        return
    
    field = data.get('field')
    
    if field == "file":
        if not message.document:
            await message.answer("❌ Пожалуйста, отправьте файл.")
            return
            
        cursor.execute("SELECT file_path FROM products WHERE id=?", (product_id,))
        old_file_path = cursor.fetchone()[0]
        
        if os.path.exists(old_file_path):
            try:
                os.remove(old_file_path)
            except Exception as e:
                logger.error(f"Ошибка удаления файла: {e}")
        
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        new_file_path = f"products_files/{file_id}_{message.document.file_name}"
        await bot.download_file(file.file_path, new_file_path)
        
        cursor.execute(
            "UPDATE products SET file_path=? WHERE id=?",
            (new_file_path, product_id)
        )
    else:
        if field == "stars_price":
            try:
                value = int(message.text)
                if value <= 0:
                    await message.answer("❌ Цена должна быть больше 0")
                    return
            except ValueError:
                await message.answer("❌ Неверный формат цены. Введите целое число, например: 1000")
                return
        else:
            value = message.text
        
        cursor.execute(
            f"UPDATE products SET {field}=? WHERE id=?",
            (value, product_id)
        )
    
    conn.commit()
    global products
    products = load_products()
    
    await message.answer("✅ Товар успешно обновлен!", reply_markup=get_admin_menu())
    await state.clear()

# Удаление товара
@dp.callback_query(F.data == "delete_product")
async def delete_product_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ У вас нет доступа.")
        return
    
    if not products:
        await callback.message.answer("❌ Нет товаров для удаления.")
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for id, product in products.items():
        builder.add(InlineKeyboardButton(
            text=f"{product['name']} - {product['stars_price']}⭐", 
            callback_data=f"delete_select_{id}"
        ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        "Выберите товар для удаления:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_select_"))
async def delete_product_select(callback: types.CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    product = products[product_id]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_confirm_{product_id}")],
        [InlineKeyboardButton(text="❌ Нет, отмена", callback_data="delete_product")]
    ])
    
    await callback.message.edit_text(
        f"Вы уверены, что хотите удалить товар:\n\n"
        f"{product['name']} - {product['stars_price']}⭐\n\n"
        f"Это действие нельзя отменить!",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_confirm_"))
async def delete_product_confirm(callback: types.CallbackQuery):
    global products
    
    try:
        product_id = int(callback.data.split("_")[2])
        product = products[product_id]
        
        if os.path.exists(product['file_path']):
            os.remove(product['file_path'])
        
        cursor.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.commit()
        
        products = load_products()
        
        await callback.message.edit_text(
            f"✅ Товар \"{product['name']}\" успешно удален!",
            reply_markup=get_admin_menu()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при удалении товара: {e}")
        await callback.answer("❌ Произошла ошибка при удалении товара!")

# Каталог товаров
@dp.message(F.text == "🛍 Каталог товаров")
@dp.message(Command("shop"))
async def shop(message: types.Message):
    if not products:
        await message.answer("📭 В магазине пока нет товаров.")
        return
    
    builder = InlineKeyboardBuilder()
    for id, product in products.items():
        builder.add(InlineKeyboardButton(
            text=f"{product['name']} - {product['stars_price']}⭐", 
            callback_data=f"view_{id}"
        ))
    builder.adjust(1)
    
    await message.answer(
        "📚 Каталог товаров:",
        reply_markup=builder.as_markup()
    )

# Просмотр товара
@dp.callback_query(F.data.startswith("view_"))
async def view_product(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    product = products.get(product_id)
    user_id = callback.from_user.id
    
    if not product:
        await callback.answer("❌ Товар не найден!")
        return
    
    stars_balance = get_stars_balance(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Купить", callback_data=f"buy_{product_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shop")]
    ])
    
    await callback.message.edit_text(
        f"<b>{product['name']}</b>\n\n"
        f"{product['desc']}\n\n"
        f"⭐ Цена: <b>{product['stars_price']}</b>\n"
        f"🆔 ID товара: <code>{product_id}</code>\n\n"
        f"Ваши звезды: {stars_balance}",
        reply_markup=keyboard
    )
    await callback.answer()

# Покупка товара
@dp.callback_query(F.data.startswith("buy_"))
async def buy_product(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    product = products.get(product_id)
    user_id = callback.from_user.id
    
    if not product:
        await callback.answer("❌ Товар не найден!")
        return
        
    stars_balance = get_stars_balance(user_id)
    stars_price = product['stars_price']
    
    if stars_balance >= stars_price:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{product_id}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"view_{product_id}")]
        ])
        
        await callback.message.edit_text(
            f"✅ Подтверждение покупки\n\n"
            f"Товар: {product['name']}\n"
            f"Цена: {stars_price}⭐\n\n"
            f"Ваши звезды: {stars_balance}\n"
            f"Останется: {stars_balance - stars_price}⭐",
            reply_markup=keyboard
        )
        await callback.answer()
    else:
        await callback.answer(
            f"❌ Недостаточно звезд. Нужно {stars_price}", 
            show_alert=True
        )

# Подтверждение покупки
@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_purchase(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    product = products.get(product_id)
    user_id = callback.from_user.id
    
    if not product:
        await callback.answer("❌ Товар не найден!")
        return
        
    stars_price = product['stars_price']
    
    cursor.execute("UPDATE users SET stars_balance = stars_balance - ? WHERE user_id=?", 
                  (stars_price, user_id))
    cursor.execute("INSERT INTO purchases (user_id, product_id) VALUES (?, ?)", 
                  (user_id, product_id))
    conn.commit()
    update_stats()  # Обновляем статистику
    
    # Уведомление админу с обработкой ошибок
    try:
        if get_notifications_enabled(ADMIN_IDS[0]):
            username = callback.from_user.username or str(user_id)
            new_balance = get_stars_balance(user_id)
            await bot.send_message(
                ADMIN_IDS[0],
                f"🔔 Новая покупка\n"
                f"🆔 ID: {user_id}\n"
                f"@{username} оплатил товар {product['name']}\n"
                f"💰 Сумма покупки: {stars_price} звезд\n"
                f"💸 Остаток его баланса: {new_balance}"
            )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления админу: {e}")
    
    try:
        file = FSInputFile(product['file_path'])
        await bot.send_document(
            chat_id=user_id,
            document=file,
            caption=(
                f"✅ Спасибо за покупку! Товар <b>{product['name']}</b> активирован.\n"
                f"⭐ Остаток: {get_stars_balance(user_id)}"
            )
        )
    except Exception as e:
        logger.error(f"Ошибка отправки файла: {e}")
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"✅ Покупка <b>{product['name']}</b> за {stars_price}⭐ завершена!\n"
                f"⚠️ Ошибка отправки файла. Обратитесь в поддержку."
            )
        )
    
    await callback.message.edit_text(
        f"✅ Покупка <b>{product['name']}</b> за {stars_price}⭐ завершена!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🛍 Продолжить", callback_data="back_to_shop")]
            ]
        )
    )
    await callback.answer()

# Возврат в каталог
@dp.callback_query(F.data == "back_to_shop")
async def back_to_shop(callback: types.CallbackQuery):
    if not products:
        await callback.message.edit_text("📭 В магазине пока нет товаров.")
        return
    
    builder = InlineKeyboardBuilder()
    for id, product in products.items():
        builder.add(InlineKeyboardButton(
            text=f"{product['name']} - {product['stars_price']}⭐", 
            callback_data=f"view_{id}"
        ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        "📚 Каталог товаров:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Личный кабинет
@dp.message(F.text == "👤 Личный кабинет")
async def profile(message: types.Message):
    user_id = message.from_user.id
    stars_balance = get_stars_balance(user_id)
    purchases = get_purchases_count(user_id)
    
    text = (
        "👤 Личный кабинет\n"
        f"🆔 ID: {user_id}\n"
        f"⭐ Звезды: <b>{stars_balance}</b>\n"
        f"🛍 Куплено товаров: {purchases}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 История покупок", callback_data="purchase_history")],
        [InlineKeyboardButton(text="📈 История пополнений", callback_data="deposit_history")],
        [InlineKeyboardButton(text="⭐ Пополнить", callback_data="deposit_stars")],
        [InlineKeyboardButton(text="🆘 Техподдержка", url=f"https://t.me/{SUPPORT_USERNAME[1:]}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    
    await message.answer(text, reply_markup=keyboard)

# Пополнение звездами
@dp.callback_query(F.data == "deposit_stars")
async def deposit_stars(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Введите количество звезд для пополнения (мин. 10):",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Form.deposit_stars_amount)
    await callback.answer()

@dp.message(Form.deposit_stars_amount)
async def process_deposit_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        if amount < 10:
            await message.answer("❌ Минимальная сумма пополнения - 10 звезд")
            return
            
        await create_stars_invoice(message.from_user.id, amount, "Пополнение звездами")
        await state.clear()
        await message.answer("Ожидайте инвойс для оплаты...", reply_markup=get_main_menu())
    except ValueError:
        await message.answer("❌ Неверный формат. Введите целое число, например: 50")

async def create_stars_invoice(user_id: int, amount: int, description: str):
    await bot.send_invoice(
        chat_id=user_id,
        title=description,
        description=f"Пополнение на {amount} звезд",
        provider_token="",  # Пустой provider_token для Telegram Stars
        currency="XTR",
        prices=[LabeledPrice(label="Звезды", amount=amount)],
        payload=f"stars_deposit_{user_id}_{amount}",
        need_email=False,
        need_phone_number=False,
        need_shipping_address=False,
        is_flexible=False,
        max_tip_amount=0
    )

# Обработка предпроверки платежа
@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

# Обработка успешного платежа
@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    try:
        payload = message.successful_payment.invoice_payload
        if payload.startswith("stars_deposit_"):
            parts = payload.split("_")
            user_id = int(parts[2])
            amount_stars = int(parts[3])
            
            cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            cursor.execute("UPDATE users SET stars_balance = stars_balance + ? WHERE user_id=?", 
                          (amount_stars, user_id))
            cursor.execute("INSERT INTO deposits (user_id, amount_stars) VALUES (?, ?)", 
                          (user_id, amount_stars))
            conn.commit()
            update_stats()  # Обновляем статистику
            
            # Уведомление админу с обработкой ошибок
            try:
                if get_notifications_enabled(ADMIN_IDS[0]):
                    username = message.from_user.username or str(user_id)
                    new_balance = get_stars_balance(user_id)
                    await bot.send_message(
                        ADMIN_IDS[0],
                        f"🔔 Пополнение баланса\n"
                        f"🆔 ID: {user_id}\n"
                        f"@{username} пополнил свой баланс на {amount_stars} звезд\n"
                        f"💰 Его баланс: {new_balance}"
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу: {e}")
            
            await message.answer(
                f"✅ Баланс пополнен на {amount_stars} звезд!\n"
                f"⭐ Текущий баланс: {get_stars_balance(user_id)}",
                reply_markup=get_main_menu()
            )
    except Exception as e:
        logger.error(f"Ошибка обработки платежа: {e}")
        await message.answer("⚠️ Ошибка обработки платежа. Обратитесь в поддержку.", reply_markup=get_main_menu())

# История покупок
@dp.callback_query(F.data == "purchase_history")
async def purchase_history(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    cursor.execute("""
        SELECT 
            p.id,
            p.product_id,
            strftime('%d.%m.%Y %H:%M', p.date, 'localtime') as date,
            COALESCE(pr.name, 'Удалённый товар') as name,
            COALESCE(pr.stars_price, 0) as price
        FROM purchases p
        LEFT JOIN products pr ON p.product_id = pr.id
        WHERE p.user_id = ?
        ORDER BY p.date DESC
        LIMIT 10
    """, (user_id,))
    
    purchases = cursor.fetchall()
    
    if not purchases:
        text = "📭 У вас пока нет покупок."
    else:
        text = "🛒 История покупок:\n\n"
        for i, purchase in enumerate(purchases, 1):
            text += (
                f"{i}. {purchase[3]}\n"
                f"   💫 Цена: {purchase[4]}⭐\n"
                f"   🕒 Дата: {purchase[2]}\n"
                f"   🆔 Товара: {purchase[1]}\n\n"
            )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

# История пополнений
@dp.callback_query(F.data == "deposit_history")
async def deposit_history(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    cursor.execute("""
        SELECT 
            amount_stars,
            strftime('%d.%m.%Y %H:%M', date, 'localtime') as date
        FROM deposits 
        WHERE user_id = ? 
        ORDER BY date DESC 
        LIMIT 10
    """, (user_id,))
    
    deposits = cursor.fetchall()
    
    if not deposits:
        text = "📭 У вас пока нет пополнений."
    else:
        text = "📈 История пополнений:\n\n"
        for i, deposit in enumerate(deposits, 1):
            text += f"{i}. +{deposit[0]}⭐\n   🕒 {deposit[1]}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

# Возврат в профиль
@dp.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: types.CallbackQuery):
    await profile(callback.message)
    await callback.answer()

# Возврат в главное меню
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.answer("🔙 Вернулись в главное меню!", reply_markup=get_main_menu())
    await callback.answer()

# Возврат в админ-панель
@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: types.CallbackQuery):
    await callback.message.answer("👋 Добро пожаловать в админ-панель!", reply_markup=get_admin_menu())
    await callback.answer()

# Техподдержка
@dp.message(F.text == "🆘 Техподдержка")
async def support(message: types.Message):
    await message.answer(
        f"Если у вас возникли вопросы или проблемы, обратитесь в нашу техническую поддержку: {SUPPORT_USERNAME}",
        reply_markup=get_main_menu()
    )

# Запуск бота
async def main():
    if not os.path.exists("products_files"):
        os.makedirs("products_files")
    
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
