# Catalog Service

Высокоуровневый клиент для работы с каталогом товаров и поисковым сервисом.

## Возможности

- 🔍 Поиск товаров по запросу (одиночный и пакетный)
- 📦 Управление каталогом (обновление, удаление)
- 🏷️ Работа с артикулами и названиями товаров
- 🔄 Автоматические повторные попытки при сбоях
- 🔐 Поддержка аутентифицированных запросов к поисковому сервису
- 🗄️ Эффективное управление пулом соединений (по умолчанию — Redis)
- 🎯 Опциональное подключение поискового сервиса (только для методов поиска)

## Требования

- **Product Search Service** — запущенный экземпляр поискового сервиса (требуется только для методов поиска и уведомлений)
- **Хранилище каталога** — бэкенд, где хранятся данные о товарах (реализация скрыта внутри `CatalogClient`; по умолчанию используется Redis)

## Установка

```bash
pip install git+https://github.com/sidorov-works/catalog_service.git@v0.1.6
```

## Быстрый старт

### Полная функциональность (с поиском)

```python
import asyncio
from catalog_service import CatalogService

async def main():
    async with CatalogService(
        search_service_url="http://product-search:8298",  # URL Product Search Service
        catalog_host="localhost",
        catalog_db_number=0
    ) as service:
        
        # Поиск товаров
        result = await service.search_products(
            query="потянет ли ноутбук 1406 видео в 4к?",
            tenant="azerty",
            limit=5
        )
        
        print(f"Найдено товаров: {result['total_found']}")
        for item in result['results']:
            print(f"  - {item['result']} (релевантность: {item['relevance_score']})")
        
        # Получение описания товара
        description = await service.get_prod_descr_by_article(
            article="120-0550",
            tenant="azerty"
        )
        print(f"\nОписание: {description}")

asyncio.run(main())
```

### Только управление каталогом (без поиска)

```python
import asyncio
from catalog_service import CatalogService

async def main():
    # search_service_url не указан — методы поиска будут недоступны
    async with CatalogService(
        catalog_host="localhost",
        catalog_db_number=0
    ) as service:
        
        # Эти методы работают
        await service.update_catalog_data(
            tenant="azerty",
            products_by_article={
                "120-0550": {"name": "Ноутбук Azerty AZ-1406", "category": "Ноутбуки"}
            },
            product_index={
                "Ноутбук Azerty AZ-1406": ["120-0550"]
            }
        )
        
        desc = await service.get_prod_descr_by_article("120-0550", "azerty")
        
        # Эти методы вернут ошибку (поиск не настроен)
        result = await service.search_products("ноутбук", "azerty")
        # -> {"results": [], "total_found": 0, "error": "Search service is not configured..."}

asyncio.run(main())
```

## Как это работает

`CatalogService` предоставляет единый интерфейс для работы с каталогом, скрывая детали реализации:

1. **Поиск товаров** — делегируется **Product Search Service** (отдельный микросервис)
2. **Управление каталогом** — напрямую работает с хранилищем через `CatalogClient`
3. **Детали хранения** — полностью скрыты от вызывающего кода (текущая реализация использует Redis)

**Архитектура:**
- Вызывающий код работает только с `CatalogService`
- `CatalogService` сам решает, когда обращаться к Product Search Service, а когда — напрямую к хранилищу
- Конкретная реализация хранилища инкапсулирована в `CatalogClient`

## Основные методы

### Поиск (требуют Product Search Service)

| Метод | Описание | Поведение без search_service_url |
|-------|----------|----------------------------------|
| `search_products()` | Поиск товаров по запросу | Возвращает ошибку в поле `error` |
| `search_products_batch()` | Пакетный поиск (до 100 запросов) | Выбрасывает `ValueError` |

### Управление каталогом (работают всегда)

| Метод | Описание |
|-------|----------|
| `update_catalog_data()` | Обновление каталога |
| `delete_tenant_catalog()` | Удаление всего каталога тенанта |
| `tenant_exists()` | Проверка существования тенанта |

### Работа с товарами (работают всегда)

| Метод | Описание |
|-------|----------|
| `article_exists()` | Проверка существования артикула |
| `get_prod_descr_by_article()` | Получение описания по артикулу |
| `get_prod_descr_by_product()` | Получение описания по названию |
| `get_articles_by_product()` | Получение списка артикулов по названию |
| `get_product_name_by_article()` | Получение названия по артикулу |
| `get_prod_descr_str()` | Универсальное получение описания (приоритет: article > product) |

### Уведомления (требуют Product Search Service)

| Метод | Описание | Когда вызывать | Поведение без search_service_url |
|-------|----------|----------------|----------------------------------|
| `notify_catalog_updated()` | Уведомить поисковый сервис об обновлении | После изменения каталога | Логирует warning, возвращает `None` |
| `notify_catalog_deleted()` | Уведомить поисковый сервис об удалении | После удаления каталога | Логирует warning, ничего не делает |

**Важно:** Без вызова `notify_catalog_updated()` поисковый сервис будет использовать устаревшие данные из кэша!

## Конфигурация

### Параметры `CatalogService`

**Product Search Service (опционально):**
- `search_service_url` (опциональный) — URL запущенного Product Search Service. Если не указан, методы поиска и уведомлений будут недоступны.
- `search_service_api_secret` — секрет для аутентификации (если требуется)
- `search_service_auth_type` — тип аутентификации
- `search_request_timeout` — таймаут поисковых запросов (по умолчанию: 20.0)
- `notification_request_timeout` — таймаут уведомлений (по умолчанию: 10.0)
- `search_max_retries` — количество повторов при ошибках поиска (по умолчанию: 3)
- `notification_max_retries` — количество повторов при ошибках уведомлений (по умолчанию: 3)

**Хранилище каталога (текущая реализация — Redis):**
- `catalog_connection_pool` — готовый пул соединений (продвинутое использование)
- `catalog_host` — хост хранилища (по умолчанию: localhost)
- `catalog_port` — порт (по умолчанию: 6379)
- `catalog_password` — пароль (опционально)
- `catalog_db_number` — номер базы данных (по умолчанию: 0)
- `catalog_max_connections` — макс. соединений в пуле (по умолчанию: 100)
- `catalog_socket_timeout` — таймаут операций с сокетом (по умолчанию: 10.0)
- `catalog_socket_connect_timeout` — таймаут подключения (по умолчанию: 10.0)
- `catalog_health_check_interval` — интервал проверки здоровья (по умолчанию: 30.0)
- `catalog_max_retries` — количество повторов при ошибках (по умолчанию: 3)

> **Примечание:** Параметры `catalog_host`, `catalog_port` и другие — это детали текущей реализации на Redis. Они могут измениться в будущих версиях при смене бэкенда хранилища. Для изоляции от деталей реализации рекомендуется использовать `catalog_connection_pool`.

### Параметры `CatalogConnectionPool`

Если вы хотите создать пул соединений вручную:

```python
from catalog_service import CatalogConnectionPool

pool = CatalogConnectionPool(
    url="redis://localhost:6379/0",
    max_connections=100,
    socket_timeout=10.0,
    socket_connect_timeout=10.0,
    health_check_interval=30.0,
    retry_on_timeout=True,
    socket_keepalive=True,
    decode_responses=False
)
```

## Структура ответа поиска

```python
{
    "results": [
        {
            "result": "Ноутбук Azerty AZ-1406",  # артикул или название
            "relevance_score": 0.95,              # оценка релевантности (0.0-1.0)
            "by_article": False                  # True — найден по артикулу
        }
    ],
    "total_found": 1,                            # всего найдено
    "error": None                                # описание ошибки (если есть)
}
```

### Пример ответа с ошибкой

```python
{
    "results": [],
    "total_found": 0,
    "error": "Search service is not configured (search_service_url not provided)"
}
```

## Пример полного цикла работы

```python
async def update_and_search():
    async with CatalogService(
        search_service_url="http://product-search:8298",
        catalog_host="localhost"
    ) as service:
        
        # 1. Обновляем каталог
        await service.update_catalog_data(
            tenant="azerty",
            products_by_article={
                "120-0550": {
                    "name": "Ноутбук Azerty AZ-1406",
                    "category": "Ноутбуки",
                    "characteristics": {
                        "процессор": "Intel Core i5",
                        "оперативная память": "16GB",
                        "SSD": "512GB"
                    }
                }
            },
            product_index={
                "Ноутбук Azerty AZ-1406": ["120-0550"]
            }
        )
        
        # 2. Уведомляем поисковый сервис
        await service.notify_catalog_updated("azerty")
        
        # 3. Ищем товары
        results = await service.search_products(
            query="ноутбук 1406",
            tenant="azerty"
        )
        
        # 4. Получаем описание для каждого результата
        for item in results["results"]:
            if item["by_article"]:
                desc = await service.get_prod_descr_by_article(
                    item["result"], 
                    "azerty"
                )
            else:
                desc = await service.get_prod_descr_by_product(
                    item["result"], 
                    "azerty"
                )
            print(f"{item['result']}: {desc}")
```

## Форматирование описаний

Методы `get_prod_descr_by_article()` и `get_prod_descr_by_product()` возвращают отформатированное описание товара:

### Для одиночного товара:
```
Модель: Ноутбук Azerty AZ-1406
Категория: Ноутбуки

Характеристики:
- процессор: Intel Core i5
- оперативная память: 16GB
- SSD: 512GB
```

### Для обобщенного товара (несколько артикулов):
```
Модель: Ноутбук Azerty AZ-1400
Категория: Ноутбуки
Артикулы: 120-0550, 120-0551, 120-0552

Общие характеристики:
- процессор: Intel Core i5
- диагональ экрана: 15.6"

Различия по конфигурациям:
- 120-0550:
  * оперативная память: 16GB
  * SSD: 512GB
- 120-0551:
  * оперативная память: 32GB
  * SSD: 1TB
```

## Лицензия

MIT