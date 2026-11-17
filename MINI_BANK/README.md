# MINI BANK — Telegram Mini Bank

Закрытая виртуальная банковская система для владельца и друзей.

**Стек:** Python 3.12+, aiogram 3, SQLite, Argon2id, TOTP (Google Authenticator).

## Возможности

- Регистрация пользователей с уникальной виртуальной картой `MB-XXXXXX`
- Основной и накопительный счета (суммы в копейках)
- Переводы по Telegram ID / номеру карты
- Математические задания 6 уровней сложности
- Ежедневный бонус
- Игры с призами (без ставок)
- История операций с пагинацией
- Топ участников
- Админ-панель с паролем + Google Authenticator (TOTP)
- Резервные коды, блокировка при подборе, сессии с таймаутом

## Требования

- Python 3.12 или новее
- Telegram-бот (создаётся через [@BotFather](https://t.me/BotFather))

## Установка

### 1. Распакуйте архив

```bash
unzip MINI_BANK.zip
cd MINI_BANK
```

### 2. Создайте виртуальное окружение и установите зависимости

**Linux / macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows:**

Просто запустите `start.bat` (он создаст venv и установит зависимости).

Или вручную:

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Настройка .env

```bash
cp .env.example .env
```

Отредактируйте `.env`:

```
BOT_TOKEN=123456:ABC-DEF...          # токен от BotFather
OWNER_ID=123456789                   # ваш Telegram ID
DATABASE_PATH=database/mini_bank.db
TIMEZONE=Europe/Moscow
```

Как узнать свой Telegram ID: напишите боту [@userinfobot](https://t.me/userinfobot).

### 4. Запуск

**Linux / macOS:**

```bash
source venv/bin/activate
python bot.py
```

**Windows:**

```cmd
start.bat
```

### 5. Первоначальная настройка администратора

1. Напишите боту `/start` (зарегистрируетесь как обычный пользователь).
2. Отправьте `/apanel`.
3. Придумайте пароль (≥ 8 символов).
4. Отсканируйте QR-код в Google Authenticator (или Authy).
5. Введите 6-значный код.
6. Сохраните резервные коды в надёжном месте.

После этого панель доступна по `/apanel` → пароль → TOTP-код.

## Команды администратора

| Команда | Описание |
|---------|----------|
| `/apanel` | Открыть админ-панель |
| `/newgame` | Создать игру (пошагово) |
| `/startgame <id>` | Запустить игру |
| `/finishgame <id> <tg_id\|draw>` | Завершить игру и выбрать победителя |
| `/cancelgame <id>` | Отменить игру |

## Структура проекта

```
MINI_BANK/
├── bot.py              # Точка входа
├── config.py           # Конфигурация
├── models.py           # Модели пользователей
├── database/           # SQLite
├── handlers/           # Обработчики
├── security.py         # Argon2 + TOTP
├── economy.py          # Балансы и транзакции
├── transfers.py        # Переводы
├── bonuses.py          # Ежедневный бонус
├── savings.py          # Накопительный счёт
├── tasks.py            # Математические задания
├── games.py            # Игровая система
├── keyboards.py        # Inline-клавиатуры
├── notifications.py    # Уведомления
├── tests/              # Автотесты
├── backups/            # Резервные копии
├── requirements.txt
├── .env.example
├── start.bat
└── README.md
```

## Резервное копирование

База данных: `database/mini_bank.db`.

Рекомендуется периодически копировать файл в папку `backups/`:

```bash
cp database/mini_bank.db backups/mini_bank_$(date +%Y%m%d_%H%M%S).db
```

## Безопасность

- Токен бота и пароли **не** хранятся в исходном коде.
- Пароль администратора — Argon2id.
- 2FA через стандартный TOTP (совместим с Google Authenticator).
- Все SQL-запросы параметризованы.
- Денежные операции атомарны, суммы — целые копейки.
- Проверка прав администратора на каждой операции.
- Защита от повторного нажатия и двойного начисления.

## Тесты

```bash
pytest tests/ -v
```

## Лицензия

Проект для личного использования. Все виртуальные средства не имеют реальной ценности.
