Ниже — полная рабочая модель репозитория: как запустить, настроить, разрабатывать новую фичу, работать с БД, модулями, Docker и командой.

## 1. Главная идея репозитория

`launchpad` — единое fullstack-приложение:

```text
Browser
   ↓
React/Vite
   ↓ /api/*
FastAPI
   ↓
SQLAlchemy
   ↓
SQLite или PostgreSQL
```

В development работают два процесса:

```text
http://localhost:5173  → Vite/React
http://localhost:8000  → FastAPI
```

Vite проксирует `/api/*` и `/uploads/*` на FastAPI, поэтому frontend обращается просто к `/api`, без CORS и захардкоженного backend URL.

В production/Docker frontend собирается в статические файлы и раздаётся самим FastAPI:

```text
http://localhost:8000/       → React SPA
http://localhost:8000/api/*  → FastAPI
```

## 2. Что нужно установить

Обязательно:

- Git;
- Node.js `>=20.19`;
- npm;
- Python `>=3.11` или `uv`.

Опционально:

- Docker Desktop;
- PostgreSQL.

Проверка:

```powershell
node --version
npm --version
python --version
docker --version
```

Если установлен `uv`, setup автоматически использует его. Иначе создаётся обычный `backend/.venv`.

## 3. Первый запуск после клонирования

```powershell
git clone https://github.com/Y-not-devs/launchpad.git
cd launchpad
npm run setup
npm run dev
```

`npm run setup` выполняет всё необходимое:

1. Копирует `.env.example` в `.env`, только если `.env` ещё не существует.
2. Создаёт Python environment.
3. Устанавливает backend-зависимости и dev tools.
4. Применяет Alembic migrations.
5. Запускает seed с демо-данными.
6. Устанавливает frontend dependencies.

Setup можно запускать повторно:

```powershell
npm run setup
```

Существующий `.env` не перезаписывается, миграции повторно не накатываются, seed не дублирует items.

После запуска:

- frontend: http://localhost:5173
- Swagger: http://localhost:8000/api/docs
- health: http://localhost:8000/api/health
- OpenAPI: http://localhost:8000/api/openapi.json

Остановка обоих процессов:

```text
Ctrl+C
```

## 4. Ежедневная разработка

Основная команда:

```powershell
npm run dev
```

Она:

- применяет свежие миграции;
- запускает FastAPI с `--reload`;
- запускает Vite;
- помечает логи `[api]` и `[web]`;
- останавливает оба процесса по `Ctrl+C`.

Только backend:

```powershell
npm run dev:api
```

Только frontend:

```powershell
npm run dev:web
```

Frontend без backend откроется, но запросы будут возвращать ошибку «Бэкенд недоступен».

После `git pull`, если изменились зависимости, лучше выполнить:

```powershell
npm run setup
```

## 5. Как работает `.env`

Основной конфигурационный файл — корневой [.env.example](<C:/Users/Hamza/OneDrive/Desktop/Notes of Hamza/Programming/Projects/launchpad/.env.example>).

Настоящий `.env`:

- создаётся локально;
- не коммитится;
- исключён из Docker build context;
- может содержать API keys и секреты.

Пример:

```dotenv
APP_NAME="My Hackathon Project"
ENVIRONMENT=dev

API_PORT=8000
WEB_PORT=5173

DATABASE_URL=sqlite:///./data/app.db

ENABLE_AUTH=true
ENABLE_UPLOADS=true
ENABLE_AI=true

SECRET_KEY=случайный-длинный-ключ
MAX_UPLOAD_MB=10

AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-...
AI_MODEL=gpt-4o-mini
```

После изменения `.env` перезапустите `npm run dev`. Настройки FastAPI кэшируются при старте, а включённые router-ы собираются один раз.

### Приоритет настроек

У backend приоритет примерно такой:

```text
Environment variables процесса
    ↓
backend/.env
    ↓
корневой .env
    ↓
defaults в config.py
```

Настройки описаны в [config.py](<C:/Users/Hamza/OneDrive/Desktop/Notes of Hamza/Programming/Projects/launchpad/backend/app/core/config.py>).

### Переменные frontend

Только переменные с префиксом `VITE_` доступны браузеру.

Например:

```dotenv
VITE_API_URL=https://api.example.com/api
```

Никогда не создавайте:

```dotenv
VITE_SECRET_KEY=...
VITE_AI_API_KEY=...
```

Такие значения попадут в JavaScript bundle и будут видны пользователю.

При стандартном локальном запуске `VITE_API_URL` не нужен — frontend использует `/api` через Vite proxy.

## 6. Backend-архитектура

Основной поток:

```text
main.py
  → api.py
    → feature/router.py
      → feature/service.py
        → feature/models.py
          → database
```

### Назначение файлов feature

Каждая feature находится в:

```text
backend/app/features/<feature>/
```

Стандартная структура:

```text
models.py   → SQLAlchemy-таблицы
schemas.py  → Pydantic request/response contracts
service.py  → бизнес-логика
router.py   → HTTP endpoints
```

Правило:

- `router.py` принимает HTTP-запрос и вызывает service;
- `service.py` содержит бизнес-логику;
- `models.py` знает о БД;
- `schemas.py` определяет публичный API-контракт.

Не нужно складывать бизнес-логику непосредственно в router.

### Работа с БД в router

Используется dependency:

```python
from app.core.db import DbSession

@router.get("")
def list_entities(db: DbSession):
    ...
```

FastAPI откроет SQLAlchemy session и закроет её после запроса.

### Ошибки

Сервисы выбрасывают доменные ошибки:

```python
raise NotFoundError("Entity not found")
raise ConflictError("Entity already exists")
raise UnauthorizedError()
raise ExternalServiceError()
```

Они автоматически превращаются в JSON:

```json
{
  "detail": "Entity not found",
  "code": null
}
```

Не нужно вручную создавать `JSONResponse` в каждом router.

## 7. Как добавить новую backend feature

Допустим, нужна feature `projects`.

Создайте:

```text
backend/app/features/projects/
├── __init__.py
├── models.py
├── schemas.py
├── service.py
└── router.py
```

Порядок работы:

1. Создать SQLAlchemy model.
2. Создать Pydantic schemas.
3. Реализовать service functions.
4. Создать router.
5. Подключить router в `backend/app/api.py`.
6. Создать migration.
7. Добавить тесты.

Подключение router:

```python
from app.features.projects.router import router as projects_router

api.include_router(projects_router)
```

Модели для Alembic обнаруживаются автоматически, если файл называется `models.py` и лежит внутри package в `app/features`.

После создания model:

```powershell
npm run db:revision -- "add projects"
```

Обязательно откройте сгенерированный файл migration и проверьте его.

Затем:

```powershell
npm run db:migrate
npm run test
```

## 8. База данных

### SQLite

По умолчанию:

```dotenv
DATABASE_URL=sqlite:///./data/app.db
```

Поскольку backend запускается с рабочей директорией `backend`, физический файл находится здесь:

```text
backend/data/app.db
```

Плюсы для хакатона:

- не нужен отдельный сервер;
- база создаётся автоматически;
- файл не коммитится;
- удобно сбросить и начать заново.

### Команды Alembic

Применить migrations:

```powershell
npm run db:migrate
```

Создать migration:

```powershell
npm run db:revision -- "add project owner"
```

Откатить последнюю migration:

```powershell
npm run db:downgrade
```

Запустить seed:

```powershell
npm run db:seed
```

Полностью пересоздать схему:

```powershell
npm run db:reset
```

`db:reset` удаляет данные. Используйте его только когда это действительно нужно.

### PostgreSQL локально

Пример:

```dotenv
DATABASE_URL=postgresql+psycopg://app:password@localhost:5432/app
```

Драйвер `psycopg3` уже установлен.

После изменения:

```powershell
npm run db:migrate
npm run dev
```

### PostgreSQL внутри Compose

Раскомментируйте `db` и `volumes` в [docker-compose.yml](<C:/Users/Hamza/OneDrive/Desktop/Notes of Hamza/Programming/Projects/launchpad/docker-compose.yml>).

В `.env` используйте hostname сервиса `db`:

```dotenv
DATABASE_URL=postgresql+psycopg://app:app@db:5432/app
```

Не `localhost`: внутри контейнера `localhost` означает сам контейнер приложения.

## 9. Готовые API endpoints

### System

| Method | URL | Назначение |
|---|---|---|
| GET | `/api/health` | Проверка API и БД |
| GET | `/api/meta` | Название, environment, включённые features |
| GET | `/api/docs` | Swagger |
| GET | `/api/openapi.json` | OpenAPI schema |

### Items

| Method | URL | Назначение |
|---|---|---|
| GET | `/api/items` | Список, поиск, фильтр, pagination |
| POST | `/api/items` | Создание |
| GET | `/api/items/{id}` | Получение |
| PATCH | `/api/items/{id}` | Частичное обновление |
| DELETE | `/api/items/{id}` | Удаление |

Фильтры:

```text
/api/items?q=demo
/api/items?status=done
/api/items?limit=20&offset=40
```

### Auth

Доступны только при:

```dotenv
ENABLE_AUTH=true
```

| Method | URL |
|---|---|
| POST | `/api/auth/register` |
| POST | `/api/auth/login` |
| GET | `/api/auth/me` |

Items автоматически не становятся защищёнными после включения auth. Для защиты endpoint нужно добавить dependency из `auth/deps.py`.

Frontend хранит JWT в `localStorage` и отправляет:

```http
Authorization: Bearer <token>
```

Сгенерировать секрет:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Полученное значение записать:

```dotenv
SECRET_KEY=...
```

Смена `SECRET_KEY` инвалидирует выданные JWT.

### Uploads

Доступны при:

```dotenv
ENABLE_UPLOADS=true
```

| Method | URL |
|---|---|
| POST | `/api/uploads` |
| GET | `/api/uploads` |
| GET | `/uploads/{filename}` |

Настройки:

```dotenv
UPLOAD_DIR=./data/uploads
MAX_UPLOAD_MB=10
```

Файлы сохраняются под случайным UUID-именем. Размер проверяется потоково.

Важно: сейчас сервер не использует whitelist MIME-типов. `content_type` определяется по расширению сохранённого файла. Если проект принимает только изображения/PDF, добавьте отдельную серверную MIME-проверку.

### AI

Доступен при:

```dotenv
ENABLE_AI=true
```

Endpoint:

```text
POST /api/ai/chat
```

Если `AI_API_KEY` пуст:

```dotenv
AI_API_KEY=
```

backend возвращает mock-response. Это позволяет делать frontend без реального провайдера.

OpenAI:

```dotenv
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-...
AI_MODEL=gpt-4o-mini
```

Groq:

```dotenv
AI_BASE_URL=https://api.groq.com/openai/v1
AI_API_KEY=gsk_...
AI_MODEL=llama-3.3-70b-versatile
```

Ollama при локальной разработке:

```dotenv
AI_BASE_URL=http://localhost:11434/v1
AI_API_KEY=ollama
AI_MODEL=llama3.2
```

Для Docker Desktop вместо `localhost` обычно нужен:

```dotenv
AI_BASE_URL=http://host.docker.internal:11434/v1
```

Из другого backend service можно использовать:

```python
from app.features.ai.service import complete

text = complete(
    "Придумай название проекта",
    system="Ты продуктовый маркетолог",
)
```

## 10. Frontend-архитектура

Основные уровни:

```text
main.tsx
  → Providers
    → App.tsx
      → AppLayout
        → feature pages
```

Providers:

- `MetaProvider` — загружает `/api/meta` и `/api/health`;
- `AuthProvider` — восстанавливает пользователя по JWT;
- `ToastProvider` — уведомления.

### API-клиент

Все HTTP-запросы должны идти через:

```text
frontend/src/lib/api.ts
```

Примеры:

```typescript
const page = await api.get<Page<Item>>('/items', {
  query: { q: 'demo', limit: 20 },
})

const item = await api.post<Item>('/items', {
  title: 'Prepare demo',
})

await api.patch<Item>(`/items/${id}`, {
  status: 'done',
})

await api.delete(`/items/${id}`)
```

API client автоматически:

- добавляет `/api`;
- сериализует JSON;
- добавляет JWT;
- обрабатывает `204`;
- преобразует ошибки FastAPI;
- очищает токен при `401`.

### Добавление frontend feature

Рекомендуемая структура:

```text
frontend/src/features/projects/
├── api.ts
├── ProjectsPage.tsx
└── ProjectModal.tsx
```

В `api.ts`:

```typescript
export const projectsApi = {
  list: () => api.get<Page<Project>>('/projects'),
  create: (data: ProjectCreate) => api.post<Project>('/projects', data),
}
```

Общие TypeScript types можно добавить в:

```text
frontend/src/types/index.ts
```

После этого подключить страницу в `App.tsx` и навигацию в `AppLayout.tsx`.

Импорты через alias:

```typescript
import { api } from '@/lib/api'
import { Button } from '@/components/ui'
```

## 11. UI-kit и стили

Общие компоненты находятся в:

```text
frontend/src/components/ui/
```

Перед созданием нового компонента проверьте существующие:

- `Button`
- `Card`
- `Modal`
- `Input`
- `Select`
- `Textarea`
- `Segmented`
- `Badge`
- `Spinner`
- `Skeleton`
- `Toast`
- `EmptyState`
- `ErrorState`

Дизайн-токены:

```text
frontend/src/styles/tokens.css
```

Глобальные стили:

```text
frontend/src/styles/global.css
```

Для изменения темы сначала меняйте токены, а не цвета во всех компонентах.

## 12. Проверки перед commit/merge

Полный минимальный набор:

```powershell
npm run lint
npm run test
npm run build
```

Что именно проверяется:

```text
npm run lint
├── Ruff для Python
└── TypeScript typecheck

npm run test
└── pytest backend tests

npm run build
├── TypeScript typecheck
└── Vite production build
```

Автоформатирование Python:

```powershell
npm run format
```

Сейчас frontend ESLint/Prettier и frontend unit tests не настроены. `npm run test` запускает только pytest.

Backend tests используют отдельную in-memory SQLite и не трогают `backend/data/app.db`.

## 13. Запуск production без Docker

```powershell
npm run start
```

Команда:

1. собирает frontend;
2. запускает FastAPI на `0.0.0.0:8000`;
3. FastAPI раздаёт React SPA и API с одного порта.

Открыть:

```text
http://localhost:8000
```

Это удобно для быстрой демонстрации без Docker.

## 14. Docker

### Как `.env` работает с Docker

Важно различать build и runtime.

Во время build:

```text
Dockerfile
→ собирает код
→ не получает ваш настоящий .env
→ секреты не попадают в image
```

Во время `docker compose up`:

```text
корневой .env
→ Docker Compose подставляет ${VARIABLE}
→ environment контейнера
→ Pydantic Settings
```

Например:

```yaml
- SECRET_KEY=${SECRET_KEY:-dev-secret-change-me-please-32-bytes-min}
```

Если в `.env` есть:

```dotenv
SECRET_KEY=my-real-secret
```

контейнер получит `my-real-secret`.

`.dockerignore` исключает:

- `.env`;
- `.git`;
- `.venv`;
- `node_modules`;
- SQLite;
- uploads/data;
- Python caches;
- старый frontend build.

### Сборка и запуск

```powershell
docker compose up --build
```

В фоне:

```powershell
docker compose up --build -d
```

Логи:

```powershell
docker compose logs -f app
```

Остановка:

```powershell
docker compose down
```

Пересборка:

```powershell
docker compose build --no-cache
docker compose up
```

При старте контейнер:

1. применяет migrations;
2. запускает seed;
3. запускает Uvicorn;
4. раздаёт API и собранную SPA.

Seed идемпотентен: если items существуют, он ничего не добавляет.

### Данные Docker

Compose подключает:

```yaml
./backend/data:/app/backend/data
```

Поэтому SQLite и uploads сохраняются на хосте после пересоздания контейнера.

`docker compose down` не удаляет `backend/data`.

Для полной очистки SQLite вручную используйте проектную команду `npm run db:reset` либо удаляйте данные только когда уверены, что они не нужны.

### Текущий локальный нюанс

На вашей машине Docker Desktop Linux engine во время последней проверки возвращал `500 Internal Server Error`. Перед Docker-командами нужно перезапустить Docker Desktop и проверить:

```powershell
docker version
docker info
```

Обе команды должны показывать секции Client и Server.

## 15. Работа командой

Рекомендуемый цикл:

```text
git pull
→ npm run setup
→ создать feature branch
→ изменить model/schema/service/router/UI
→ создать migration
→ npm run lint
→ npm run test
→ npm run build
→ commit
→ push
```

В Git коммитить:

- исходный код;
- migration-файлы;
- `package-lock.json`;
- `.env.example`, если появилась новая настройка;
- README, если изменился workflow.

Не коммитить:

- `.env`;
- `backend/.venv`;
- `frontend/node_modules`;
- `backend/data`;
- SQLite;
- uploads;
- `frontend/dist`;
- API keys.

При добавлении env-переменной:

1. Добавьте поле в `Settings`.
2. Добавьте пример в `.env.example`.
3. Если значение нужно в Compose — добавьте interpolation в `docker-compose.yml`.
4. Если это секрет — никогда не добавляйте префикс `VITE_`.

## 16. Типичные проблемы

### Backend Offline

```powershell
npm run setup
npm run dev:api
```

Проверить:

```powershell
curl.exe http://localhost:8000/api/health
```

### Endpoint возвращает 404

Для optional module проверьте:

```dotenv
ENABLE_AUTH=true
ENABLE_UPLOADS=true
ENABLE_AI=true
```

После изменения перезапустите сервер.

### Порт занят

```dotenv
API_PORT=8001
WEB_PORT=5174
```

Vite автоматически направит proxy на новый `API_PORT`.

### Migration не применяется

```powershell
npm run db:migrate
```

Проверьте:

- `DATABASE_URL`;
- запущен ли PostgreSQL;
- нет ли конфликтующих Alembic revisions;
- закоммичены ли migrations товарища.

### AI отвечает mock

Это означает, что `AI_API_KEY` пуст. Сам модуль при этом работает корректно.

### JWT перестал работать

Возможные причины:

- изменился `SECRET_KEY`;
- истёк token;
- localStorage содержит token от старого окружения.

Выйдите из аккаунта или очистите ключ `hs_token` в localStorage.

### Upload не сохраняется

Проверьте:

```dotenv
ENABLE_UPLOADS=true
UPLOAD_DIR=./data/uploads
MAX_UPLOAD_MB=10
```

И права записи в `backend/data`.

## 17. Практический workflow для хакатона

В начале проекта:

1. Переименовать `APP_NAME`.
2. Включить нужные modules.
3. Заменить demo items/domain.
4. Создать основную feature.
5. Сразу создать migration.
6. Сделать основной end-to-end сценарий.
7. Добавить реалистичный seed.
8. Подключить AI только после рабочего базового сценария.
9. Проверить production build.
10. За несколько часов до demo проверить Docker или `npm run start`.

Минимум перед презентацией:

```powershell
npm run lint
npm run test
npm run build
npm run start
```

Затем открыть:

```text
http://localhost:8000
http://localhost:8000/api/health
http://localhost:8000/api/docs
```

Главная мысль: корневые npm-команды — единая точка управления проектом; backend features развиваются вертикальными slices; `.env` управляет окружением и modules; migrations всегда коммитятся; frontend общается с backend только через общий API client.