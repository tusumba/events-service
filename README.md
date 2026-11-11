# events-service

Сервис **Events & Clubs** системы Tusumba: каталог и поиск мероприятий и клубов, страницы мероприятий и клубов, версии текстов, команда мероприятия и роли.

**Ответственный:** Михаил Коротков (задача #18891, OpenAPI делается вместе с Глебом Эстраихом).

## Что делает

- каталог мероприятий с сортировкой по дате, поиском по названию (`pg_trgm`) и фильтрами;
- каталог клубов и страница клуба;
- редактирование мероприятий и страниц клубов: каждое изменение создаёт новую версию текста (`event_versions`, `club_versions`), жалоба ссылается на конкретную версию;
- команда мероприятия и роли (владелец, администратор, редактор, контролёр), приглашения в команду;
- единственный источник правды о правах: остальные сервисы спрашивают роль пользователя у этого сервиса;
- создание мероприятия или клуба после одобрения заявки (событие `ApplicationApproved` от Moderation);
- загрузка фото на диск сервера через интерфейс `PhotoStorage`.

База данных `events_db`: `events`, `event_versions`, `clubs`, `club_versions`, `club_admins`, `event_team_members`, `team_invitations`.

## API

Внешний: `GET /v1/events`, `GET /v1/events/{id}`, `GET /v1/clubs`, `GET /v1/clubs/{id}`, `PATCH /v1/events/{id}`, `PATCH /v1/clubs/{id}`, `PUT /v1/events/{id}/photo`, `PUT /v1/clubs/{id}/photo`, `GET /v1/events/{id}/team`, `POST /v1/events/{id}/team/invitations`, `POST /v1/team-invitations/{id}/accept`, `PATCH` и `DELETE /v1/events/{id}/team/{userId}`, `GET /v1/events/{id}/versions`, `GET /v1/clubs/{id}/stats`.

Внутренний: `GET /internal/events/{id}/permissions`, `GET /internal/events/{id}/versions/{versionId}`, `GET /internal/clubs/{id}/versions/{versionId}`.

События в брокер: `EventPublished`, `EventUpdated`. Потребляет `ApplicationApproved`.

Закрывает требования: #18091, #18093, #18098, #18103, #18105, #18110, #18111, #18112, #18113, каталог и поиск клубов (#18626, #18627).

## Стек

Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL 16 (расширение `pg_trgm`), RabbitMQ (FastStream).

## Что уже сделано

- таблицы `events` и `event_versions` в схеме PostgreSQL `events` (миграция Alembic);
- таблица `event_team_members` и `GET /internal/events/{id}/permissions?user_id=` - роль пользователя в команде мероприятия (`owner`, `admin`, `editor`, `scanner`; `is_member = false`, если его нет в команде), 404 `event_not_found` для несуществующего и удалённого мероприятия; клиент с кешем Redis - `PermissionsClient` в tusumba-common (#19039);
- `GET /v1/events` - каталог: опубликованные мероприятия с сегодняшней даты (по Новосибирску), ближайшие выше, пагинация `page` и `size`.
- фильтры каталога: тип `is_free`, даты `date_from` и `date_to`, часть адреса `place`, статусы подтверждения `status` (можно несколько); применяются вместе и с пагинацией.
- `GET /v1/events/{id}` - страница мероприятия: текущая версия текста, дата, место, цена, организатор (секция или пользователь), `my_role` для участника команды; 404 `event_not_found` для несуществующего и удалённого мероприятия.

Поиск по названию и фильтр по секции `club_id`, название секции-организатора на странице мероприятия, секции (в том числе `GET /internal/clubs/{id}/permissions` - после #19045), управление командой и остальное API из OpenAPI - в следующих задачах.

## Запуск

Сервис создан из [service-template](https://github.com/tusumba/service-template).

```bash
uv sync
cp .env.example .env
uv run python -m tusumba_common.testing dev-keys
docker compose up -d postgres
uv run alembic upgrade head
uv run --env-file .env uvicorn app.main:create_app --factory --reload
```

## Проверки

```bash
uv run ruff format .
uv run ruff check .
uv run mypy app tests migrations
uv run pytest
```

## Документация

- [OpenAPI v1](docs/openapi.yaml) - API разделов «Каталог и поиск», «Мероприятия и секции», статистика секции и внутренние вызовы архитектуры.

Wiki проекта: https://ai.nsu.ru/projects/tusumba/wiki/Архитектура. Контракт API: OpenAPI v1 (#18891). Задачи ведутся в Redmine: https://ai.nsu.ru/projects/tusumba. Issues и Wiki GitHub выключены.

## Правила работы

Ветки, коммиты, pull request и code review описаны в [CONTRIBUTING.md](https://github.com/tusumba/.github/blob/main/CONTRIBUTING.md). Коротко:

- ветка называется `feature/<номер задачи Redmine>-<пара слов>`, например `feature/18901-login`;
- номер задачи указывается в каждом коммите и в названии PR;
- в `main` изменения попадают только через PR с одним одобрением и зелёным CI, прямой push и force push запрещены.
