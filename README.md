# Microclimate Control System

Система умного климат-контроля для промышленного помещения: автоматическое поддержание температуры с помощью ПИД-регулятора (split-range), физический симулятор микроклимата, ручной режим управления нагревателем/охладителем/вентиляцией, расписание рабочих смен с предпрогревом и веб-интерфейс с графиками телеметрии.

---

## Стек технологий

### Backend

| Категория | Технологии |
|-----------|------------|
| Язык | Python 3 |
| Веб-фреймворк | [FastAPI](https://fastapi.tiangolo.com/) |
| ASGI-сервер | [Uvicorn](https://www.uvicorn.org/) |
| ORM | [SQLAlchemy](https://www.sqlalchemy.org/) 2.x |
| Валидация данных | [Pydantic](https://docs.pydantic.dev/) 2.x |
| База данных | SQLite (`climate.db`) |

### Frontend

| Категория | Технологии |
|-----------|------------|
| Язык | TypeScript |
| UI-фреймворк | [React](https://react.dev/) 19 |
| Сборщик | [Vite](https://vite.dev/) 8 |
| Стили | [Tailwind CSS](https://tailwindcss.com/) 4 |
| HTTP-клиент | [Axios](https://axios-http.com/) |
| Графики | [Recharts](https://recharts.org/) |
| Иконки | [Lucide React](https://lucide.dev/) |

### Инфраструктура

| Категория | Технологии |
|-----------|------------|
| Контейнеризация | [Docker](https://www.docker.com/), [Docker Compose](https://docs.docker.com/compose/) |
| Продакшен-фронтенд | [Nginx](https://nginx.org/) (Alpine) |

---

## Системные требования

Для запуска через Docker достаточно установленного **Docker Desktop** (или Docker Engine + Docker Compose) с запущенной службой Docker.

Для локальной разработки без Docker дополнительно потребуются:

- **Git** — клонирование репозитория
- **Node.js** (LTS) и **npm** — фронтенд
- **Python** 3.10+ и **pip** — бэкенд

---

## Установка окружения с нуля

### 1. Git

Скачайте и установите Git с официального сайта: [https://git-scm.com/](https://git-scm.com/)

Проверка установки:

```bash
git --version
```

### 2. Node.js (для локальной разработки фронтенда)

Скачайте LTS-версию с [https://nodejs.org/](https://nodejs.org/)

Проверка установки:

```bash
node --version
npm --version
```

### 3. Python (для локальной разработки бэкенда)

Скачайте Python 3 с [https://www.python.org/downloads/](https://www.python.org/downloads/)

Проверка установки:

```bash
python --version
pip --version
```

На Windows при установке отметьте опцию **«Add Python to PATH»**.

### 4. Docker и Docker Compose (рекомендуемый способ запуска)

- **Windows / macOS:** установите [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- **Linux:** установите [Docker Engine](https://docs.docker.com/engine/install/) и плагин [Docker Compose](https://docs.docker.com/compose/install/)

После установки **запустите Docker Desktop** (или службу `docker` в Linux) и дождитесь статуса «Running».

Проверка:

```bash
docker --version
docker compose version
```

---

## Быстрый запуск через Docker (рекомендуемый способ)

### Шаг 1. Клонирование и переход в каталог проекта

```bash
git clone <URL-репозитория> microclimate-control-system
cd microclimate-control-system
```

Если репозиторий уже склонирован, перейдите в корневую папку проекта:

```bash
cd microclimate-control-system
```

### Шаг 2. Сборка и запуск контейнеров

```bash
docker compose up --build
```

Команда соберёт образы `backend` и `frontend`, запустит оба сервиса и выведет логи в терминал.

**Фоновый режим** (контейнеры работают в фоне, терминал освобождается):

```bash
docker compose up --build -d
```

### Шаг 3. Проверка работоспособности

| Ресурс | URL |
|--------|-----|
| Веб-интерфейс | [http://localhost:3000](http://localhost:3000) |
| REST API | [http://localhost:8000/api/status](http://localhost:8000/api/status) |
| Swagger-документация API | [http://localhost:8000/docs](http://localhost:8000/docs) |

Фронтенд обращается к API по адресу `http://localhost:8000` — порт бэкенда проброшен на хост, поэтому браузер на вашей машине получает доступ к обоим сервисам.

Файл базы данных `backend/climate.db` монтируется как том: история телеметрии и расписание смен сохраняются на диске хоста и не теряются при перезапуске контейнеров.

### Шаг 4. Остановка контейнеров

```bash
docker compose down
```

Контейнеры будут остановлены и удалены; данные в `backend/climate.db` останутся на хосте.

---

## Локальный запуск (для разработчиков, без Docker)

Запускайте бэкенд и фронтенд в **двух отдельных терминалах**.

### Backend

```bash
cd backend
```

**Windows (PowerShell / CMD):**

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Linux / macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API будет доступен на [http://localhost:8000](http://localhost:8000), документация — на [http://localhost:8000/docs](http://localhost:8000/docs).

При первом запуске в папке `backend` автоматически создаётся файл `climate.db`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite поднимет dev-сервер (обычно [http://localhost:5173](http://localhost:5173)). Адрес будет указан в выводе терминала.

Убедитесь, что бэкенд уже запущен на порту `8000` — фронтенд обращается к `http://localhost:8000`.

---

## Структура проекта

```
microclimate-control-system/
├── backend/
│   ├── Dockerfile
│   ├── main.py           # FastAPI-приложение, API, цикл симуляции
│   ├── database.py       # SQLAlchemy-модели и подключение к SQLite
│   ├── schemas.py        # Pydantic-схемы запросов/ответов
│   ├── simulator.py      # Симулятор помещения и ПИД-регулятор
│   ├── requirements.txt
│   └── climate.db        # SQLite (создаётся при запуске, в .gitignore)
├── frontend/
│   ├── Dockerfile
│   ├── src/
│   │   └── App.tsx       # Основной UI
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml
└── README.md
```

---

## Структура базы данных

База **SQLite** (`backend/climate.db`) содержит две таблицы. Схема создаётся автоматически при старте бэкенда (`init_db()`).

### Таблица `telemetry_logs`

Журнал телеметрии: каждые ~2 секунды симуляция записывает снимок состояния системы.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER | Первичный ключ |
| `timestamp` | DATETIME (UTC) | Время записи |
| `inside_temp` | FLOAT | Температура внутри помещения, °C |
| `outside_temp` | FLOAT | Наружная температура, °C |
| `target_temp` | FLOAT | Целевая температура, °C |
| `heater_power` | FLOAT | Мощность нагревателя, 0–100 % |
| `cooler_power` | FLOAT | Мощность охладителя, 0–100 % |
| `airflow_power` | FLOAT | Мощность вентиляции, 0–100 % |
| `is_manual_mode` | BOOLEAN | `true` — ручной режим, `false` — автоматический (ПИД) |

### Таблица `work_shifts`

Расписание рабочих смен. В активную смену целевая температура берётся из смены; за час до начала включается предпрогрев; вне смен — эко-режим (10 °C).

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER | Первичный ключ |
| `start_time` | STRING(5) | Начало смены, формат `ЧЧ:ММ` (например, `08:00`) |
| `end_time` | STRING(5) | Конец смены, формат `ЧЧ:ММ` (например, `17:00`) |
| `target_temp` | FLOAT | Целевая температура на период смены, °C |

Смены, пересекающие полночь (например, `22:00`–`06:00`), поддерживаются логикой в бэкенде.

---

## Основные API-эндпоинты

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/api/status` | Текущее состояние системы |
| GET | `/api/history` | Последние 50 записей телеметрии |
| POST | `/api/manual` | Переключение в ручной режим |
| POST | `/api/auto` | Возврат в автоматический режим (ПИД) |
| GET/POST | `/api/shifts` | Список / создание смен |
| GET/PUT/DELETE | `/api/shifts/{id}` | Чтение / обновление / удаление смены |

Полное описание схем запросов и ответов — в [Swagger UI](http://localhost:8000/docs).
