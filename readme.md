# Catalog Service

Высокоуровневый клиент для работы с каталогом товаров и поисковым сервисом.

## Возможности

- 🔍 Поиск товаров по запросу (одиночный и пакетный)
- 📦 Управление каталогом (обновление, удаление)
- 🏷️ Работа с артикулами и названиями товаров
- 🔄 Автоматические повторные попытки при сбоях
- 🔐 Поддержка аутентифицированных запросов к поисковому сервису
- 🗄️ Эффективное управление пулом соединений (по умолчанию — Redis)

## Требования

- **Product Search Service** — запущенный экземпляр поискового сервиса (предоставляет API для поиска)
- **Хранилище каталога** — бэкенд, где хранятся данные о товарах (реализация скрыта внутри `CatalogClient`; по умолчанию используется Redis)

## Установка

```bash
pip install git+https://github.com/sidorov-works/catalog_service.git@v0.1.1
```

## Быстрый старт

```python
import asyncio
from catalog_service import CatalogService

async def main():
    # CatalogService скрывает детали работы с хранилищем
    async with CatalogService(
        search_service_url="http://product-search:8298",  # URL Product Search Service
        catalog_host="localhost",      # Деталь реализации (Redis)
        catalog_db_number=0            # Деталь реализации (Redis)
    ) as service:
        
        # Поиск товаров (через Product Search Service)
        result = await service.search_products(
            query="потянет ли ноутбук 1406 видео в 4к?",
            tenant="azerty",
            limit=5
        )
        
        print(f"Найдено товаров: {result['total_found']}")
        for item in result['results']:
            print(f"  - {item['result']} (релевантность: {item['relevance_score']})")
        
        # Получение описания товара (напрямую из хранилища)
        description = await service.get_prod_descr_by_article(
            article="120-0550",
            tenant="azerty"
        )
        print(f"\nОписание: {description}")

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

### Поиск (через Product Search Service)

| Метод | Описание |
|-------|----------|
| `search_products()` | Поиск товаров по запросу |
| `search_products_batch()` | Пакетный поиск (до 100 запросов) |

### Управление каталогом (напрямую в хранилище)

| Метод | Описание |
|-------|----------|
| `update_catalog_data()` | Обновление каталога |
| `delete_tenant_catalog()` | Удаление всего каталога тенанта |
| `tenant_exists()` | Проверка существования тенанта |

### Работа с товарами (напрямую в хранилище)

| Метод | Описание |
|-------|----------|
| `article_exists()` | Проверка существования артикула |
| `get_prod_descr_by_article()` | Получение описания по артикулу |
| `get_prod_descr_by_product()` | Получение описания по названию |
| `get_articles_by_product()` | Получение списка артикулов по названию |
| `get_product_name_by_article()` | Получение названия по артикулу |

### Уведомления (вебхуки для Product Search Service)

| Метод | Описание | Когда вызывать |
|-------|----------|----------------|
| `notify_catalog_updated()` | Уведомить поисковый сервис об обновлении | После изменения каталога |
| `notify_catalog_deleted()` | Уведомить поисковый сервис об удалении | После удаления каталога |

**Важно:** Без вызова `notify_catalog_updated()` поисковый сервис будет использовать устаревшие данные из кэша!

## Конфигурация

### Параметры `CatalogService`

**Product Search Service:**
- `search_service_url` (обязательный) — URL запущенного Product Search Service
- `search_service_api_secret` — секрет для аутентификации (если требуется)
- `search_service_auth_type` — тип аутентификации
- `search_request_timeout` — таймаут поисковых запросов (по умолчанию: 20.0)
- `search_max_retries` — количество повторов при ошибках (по умолчанию: 3)

**Хранилище каталога (текущая реализация — Redis):**
- `catalog_connection_pool` — готовый пул соединений (продвинутое использование)
- `catalog_host` — хост хранилища (по умолчанию: localhost)
- `catalog_port` — порт (по умолчанию: 6379)
- `catalog_db_number` — номер базы данных (по умолчанию: 0)
- `catalog_max_connections` — макс. соединений в пуле (по умолчанию: 100)

> **Примечание:** Параметры `catalog_host`, `catalog_port` и другие — это детали текущей реализации на Redis. Они могут измениться в будущих версиях при смене бэкенда хранилища. Для изоляции от деталей реализации рекомендуется использовать `catalog_connection_pool`.

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
                "120-0550": {"name": "Ноутбук Azerty AZ-1406", "category": "Ноутбуки"}
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
        
        # 4. Получаем описание
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

## Лицензия

MIT