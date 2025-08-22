import sqlite3
import os

# Настройки базы данных
def init_db():
    conn = sqlite3.connect('shop.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Создание таблицы users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            stars_balance INTEGER DEFAULT 0
        )
    ''')
    
    # Проверка и добавление колонки notifications_enabled
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    if "notifications_enabled" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN notifications_enabled INTEGER DEFAULT 1")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            stars_price INTEGER NOT NULL,
            desc TEXT,
            file_path TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount_stars INTEGER,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Новая таблица для статистики
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY,
            total_purchases INTEGER DEFAULT 0,
            total_stars_deposited INTEGER DEFAULT 0,
            total_users INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Инициализация статистики, если таблица пустая
    cursor.execute("SELECT COUNT(*) FROM stats")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO stats (id) VALUES (1)")
        conn.commit()
    
    return conn, cursor

# Конфигурационные параметры
TOKEN = "
SUPPORT_USERNAME = ""
ADMIN_IDS = []  # ID админа для уведомлений

# Инициализация базы данных
conn, cursor = init_db()

# Загрузка товаров
def load_products():
    try:
        cursor.execute("SELECT id, name, stars_price, desc, file_path FROM products")
        products_db = cursor.fetchall()
        products = {}
        for product in products_db:
            products[product[0]] = {
                "name": product[1],
                "stars_price": product[2],
                "desc": product[3],
                "file_path": product[4]
            }
        return products
    except Exception as e:
        print(f"Ошибка загрузки товаров: {e}")
        return {}

products = load_products()

# Функции для работы с базой данных
def get_stars_balance(user_id):
    cursor.execute("SELECT stars_balance FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

def get_purchases_count(user_id):
    cursor.execute("SELECT COUNT(*) FROM purchases WHERE user_id=?", (user_id,))
    return cursor.fetchone()[0]

def get_stats():
    cursor.execute("SELECT total_purchases, total_stars_deposited, total_users FROM stats WHERE id=1")
    return cursor.fetchone()

def update_stats():
    cursor.execute("SELECT COUNT(*) FROM purchases")
    total_purchases = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(amount_stars) FROM deposits")
    total_stars_deposited = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("""
        UPDATE stats SET 
            total_purchases = ?,
            total_stars_deposited = ?,
            total_users = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = 1
    """, (total_purchases, total_stars_deposited, total_users))
    conn.commit()

def get_notifications_enabled(user_id):
    cursor.execute("SELECT notifications_enabled FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 1  # По умолчанию уведомления включены

def set_notifications_enabled(user_id, enabled):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, notifications_enabled) VALUES (?, ?)", (user_id, enabled))
    cursor.execute("UPDATE users SET notifications_enabled = ? WHERE user_id=?", (enabled, user_id))
    conn.commit()
