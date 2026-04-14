# src/catalog_service/service.py

"""
Высокоуровневый интерфейс (класс) для работы с каталогом и поиска товаров.
"""

from typing import Optional, Dict, List, Any
from catalog_client import CatalogClient
from http_utils import RetryableHTTPClient, create_signed_client, AuthType
from functools import lru_cache
from .connection_pool import CatalogConnectionPool

import logging
logger = logging.getLogger(__name__)

# Имена полей в структурах (словарях), 
# используемых в catalog_client для информации о товарах из каталога
from catalog_client import (
    COMMON_CHARACTERISTICS_FIELD,
    DIFFERENT_CHARACTERISTICS_FIELD,
    ARTICLES_FIELD,
    CATEGORY_FIELD,
    NAME_FIELD,
    CHARACTERISTICS_FIELD
)

# Константы для названий эндпойнтов поискового сервиса
EP_NAME_SEARCH = "/search"
EP_NAME_SEARCH_BATCH = "/search_batch"
EP_NAME_CATALOG_DELETED = "/catalog_deleted"
EP_NAME_CATALOG_UPDATED = "/catalog_updated"


class CatalogService():

    def __init__(
            self,

            # Параметры поискового сервиса
            search_service_url: Optional[str] = None,
            search_service_api_secret: Optional[str] = None,
            search_service_auth_type: Optional[AuthType] = None,
            search_request_timeout: float = 20.0,
            notification_request_timeout: float = 10.0,
            search_max_retries: int = 3,
            notification_max_retries: int = 3,

            # Параметры CatalogClient
            catalog_connection_pool: Optional[CatalogConnectionPool] = None,
            catalog_host: str = "localhost",
            catalog_port: int = 6379,
            catalog_password: Optional[str] = None,
            catalog_db_number: int = 0,
            catalog_max_connections: int = 100,
            catalog_socket_timeout: float = 10.0,
            catalog_socket_connect_timeout: float = 10.0,
            catalog_health_check_interval: float = 30.0,
            catalog_max_retries: int = 3
        ):
        self._search_service_url = search_service_url

        # Создаем клиенты для запросов к поисковому сервису ТОЛЬКО если указан URL
        if search_service_url:
            # отдельный клиент для поиска
            self._search_client = RetryableHTTPClient(
                base_timeout=search_request_timeout,
                max_retries=search_max_retries
            )
            # и отдельный клиент для уведомлений поискового сервиса об изменениях в каталоге
            self._notification_client = RetryableHTTPClient(
                base_timeout=notification_request_timeout,
                max_retries=notification_max_retries
            )
            # Обернем клиенты для поддержки автоматической аутентификации 
            # на поисковом сервисе, если требуется
            if search_service_api_secret and search_service_auth_type:
                self._search_client = create_signed_client(
                    self._search_client,
                    secret=search_service_api_secret,
                    service_name="catalog-service",
                    auth_type=search_service_auth_type
                )
                self._notification_client = create_signed_client(
                    self._notification_client,
                    secret=search_service_api_secret,
                    service_name="catalog-service",
                    auth_type=search_service_auth_type
                )
        else:
            self._search_client = None
            self._notification_client = None

        # Создаем объект для низкоуровневого взаимодействия с оперативным каталогом CatalogClient, 
        # просто передав ему все параметры, которые имеют к нему отношение
        self._catalog = CatalogClient(
            redis_connection_pool=catalog_connection_pool,
            redis_host=catalog_host,
            redis_port=catalog_port,
            redis_password=catalog_password,
            redis_db_number=catalog_db_number,
            redis_max_connections=catalog_max_connections,
            redis_socket_timeout=catalog_socket_timeout,
            redis_socket_connect_timeout=catalog_socket_connect_timeout,
            redis_health_check_interval=catalog_health_check_interval,
            max_execution_retries=catalog_max_retries
        )

    # микрооптимизация: кэшируем URL поискового сервиса
    @lru_cache(maxsize=1)
    def _get_search_url(self) -> str:
        """Возвращает URL для поисковых запросов"""
        return f"{self._search_service_url}{EP_NAME_SEARCH}"

    @lru_cache(maxsize=1)
    def _get_batch_search_url(self) -> str:
        """Возвращает URL для пакетных поисковых запросов"""
        return f"{self._search_service_url}{EP_NAME_SEARCH_BATCH}"

    async def search_products(
        self,
        query: str, 
        tenant: str, 
        limit: int = 10,
        normalization_power: float = 1.0
    ) -> Dict[str, Any]:
        """
        Выполняет поиск товаров по запросу для указанного тенанта.
        
        Args:
            query: Текст запроса для поиска
            tenant: Идентификатор тенанта
            limit: Максимальное количество результатов
            
        Returns:
            Словарь с результатами поиска:
            {
                "results": [
                    {
                        "result": str,         # Артикул (если by_article=True) или название товара (если by_article=False)
                        "relevance_score": float,
                        "by_article": bool     # True = найдено по артикулу, False = найдено по названию
                    },
                    ...
                ],
                "total_found": int,            # Количество найденных товаров
                "error": Optional[str]         # Описание ошибки или null при успешном поиске
            }
        """
        # Проверяем, настроен ли поисковый сервис
        if not self._search_service_url:
            return {
                "results": [],
                "total_found": 0,
                "error": "Search service is not configured (search_service_url not provided)"
            }
        
        try:
            if not query or len(query.strip()) < 2:
                return {
                    "results": [],
                    "total_found": 0,
                    "error": "Query must be at least 2 characters"
                }
            
            if not tenant:
                return {
                    "results": [],
                    "total_found": 0,
                    "error": "Tenant ID is required"
                }
            
            # Подготавливаем запрос
            request_json = {
                "query": query,
                "tenant_id": tenant,
                "limit": limit,
                "normalization_power": normalization_power
            }
            
            
            # Выполняем запрос к поисковому сервису
            response = await self._search_client.post_with_retry(
                url=self._get_search_url(),
                json=request_json,
                success_statuses={200}
            )
            
            data = response.json()
            
            # Преобразуем формат результатов для единообразия
            formatted_results = []
            for item in data.get("results", []):
                formatted_results.append({
                    "result": item["result"],
                    "relevance_score": item["relevance_score"],
                    "by_article": item["by_article"]
                })
            
            result = {
                "results": formatted_results,
                "total_found": data.get("total_found", len(formatted_results)),
                "error": None
            }
            
            logger.debug(f"Found {result['total_found']} products for query '{query}' (tenant: {tenant})")
            return result
            
        except Exception as e:
            logger.error(f"Search error for query '{query}' (tenant: {tenant}): {e}")
            return {
                "results": [],
                "total_found": 0,
                "error": f"Search error: {str(e)}"
            }

    async def search_products_batch(
        self,
        search_requests: List[Dict[str, Any]],
        relevance_threshold: Optional[float] = None,
        normalization_power: float = 1.0
    ) -> List[Dict[str, Any]]:
        """
        Выполняет пакетный поиск товаров по нескольким запросам.
        
        Args:
            search_requests: Список словарей с параметрами поиска.
                            Каждый словарь должен содержать:
                            - query: текст запроса
                            - tenant_id: идентификатор тенанта
                            - limit: (опционально) максимальное количество результатов, по умолчанию 10
        
        Returns:
            Список результатов в том же порядке, что и запросы.
            Каждый элемент списка - словарь с результатами поиска или информацией об ошибке.
            
            Структура успешного результата:
            {
                "results": [
                    {
                        "result": str,          # Артикул (если by_article=True) 
                                            # или название товара (если by_article=False)
                        "relevance_score": float,
                        "by_article": bool      # True = найдено по артикулу, False = найдено по названию
                    },
                    ...
                ],
                "total_found": int,            # Количество найденных товаров
                "error": null                  # Отсутствует при успешном поиске
            }
            
            Структура результата с ошибкой:
            {
                "results": [],                 # Пустой список
                "total_found": 0,
                "error": str                   # Описание ошибки
            }
        
        Raises:
            Exception: Если произошла общая ошибка при выполнении пакетного запроса
        """
        # Проверяем, настроен ли поисковый сервис
        if not self._search_service_url:
            raise ValueError("Search service is not configured (search_service_url not provided)")
        
        try:
            if not search_requests:
                logger.warning("Empty batch search request")
                return []
            
            if len(search_requests) > 100:
                logger.warning(f"Batch size too large: {len(search_requests)}. Truncating to 100")
                search_requests = search_requests[:100]
            
            logger.info(f"Executing batch search with {len(search_requests)} requests")
            
            # Подготавливаем запросы в формате, ожидаемом API
            formatted_requests = []
            for i, req in enumerate(search_requests):
                if not isinstance(req, dict):
                    logger.warning(f"Invalid request format at index {i}: {req}")
                    continue
                    
                if "query" not in req or "tenant_id" not in req:
                    logger.warning(f"Missing required fields in request at index {i}: {req}")
                    continue
                
                formatted_requests.append({
                    "query": req["query"],
                    "tenant_id": req["tenant_id"],
                    "limit": req.get("limit", 10)
                })
            
            if not formatted_requests:
                logger.error("No valid requests in batch")
                return []
            
            # Выполняем пакетный запрос
            response = await self._search_client.post_with_retry(
                url=self._get_batch_search_url(),
                json={
                    "requests": formatted_requests, 
                    "relevance_threshold": relevance_threshold,
                    "normalization_power": normalization_power
                    },
                success_statuses={200}
            )
            
            data = response.json()
            batch_results = []
            
            for i, result_item in enumerate(data.get("results", [])):
                # Сохраняем результат в том же порядке
                batch_results.append({
                    "results": result_item.get("results", []),
                    "total_found": result_item.get("total_found", 0),
                    "error": result_item.get("error")
                })
            
            logger.info(f"Batch search completed: {len(batch_results)} results returned")
            return batch_results
            
        except Exception as e:
            logger.error(f"Batch search error: {e}")
            raise

    async def delete_tenant_catalog(self, tenant: str):
        """Полное удаление каталога товаров"""
        try:
            await self._catalog.delete_tenant_catalog(tenant)
            logger.info(f"Каталог тенанта {tenant} успешно удален из Redis")
        except Exception as e:
            logger.error(f"Ошибка удаления каталога тенанта {tenant}: {e}")
            raise

    # async def close_catalog(self) -> None:
    #     """Корректное закрытие соединения с Redis"""
    #     await self._catalog.close()

    # async def close_search_clients(self):
    #     """Корректное закрытие HTTP-клиентов поискового сервиса"""
    #     await self._search_client.close()
    #     await self._notification_client.close()

    async def tenant_exists(self, tenant: str) -> bool:
        """Проверка существования тенанта"""
        try:
            return await self._catalog.tenant_exists(tenant)
        except Exception as e:
            logger.error(f"Error checking tenant existence {tenant}: {e}")
            return False

    async def notify_catalog_deleted(self, tenant: str):
        """Уведомление сервиса поиска об удалении каталога с повторными попытками"""
        # Проверяем, настроен ли поисковый сервис
        if not self._search_service_url:
            logger.warning(f"Search service not configured, skipping catalog deletion notification for {tenant}")
            return
        
        try:
            response = await self._notification_client.post_with_retry(
                url=f"{self._search_service_url}{EP_NAME_CATALOG_DELETED}/{tenant}",
                success_statuses={200}
            )
            logger.info(f"Search service notified about catalog deletion for {tenant}")
            
        except Exception as e:
            logger.error(
                f"Failed to notify search service about catalog deletion for {tenant}: {str(e)}\n"
                f"Search service cache for {tenant} may be outdated!"
            )

    async def notify_catalog_updated(self, tenant: str) -> Optional[bool]:
        """Уведомление сервиса поиска об обновлении каталога с повторными попытками"""
        # Проверяем, настроен ли поисковый сервис
        if not self._search_service_url:
            logger.warning(f"Search service not configured, skipping catalog update notification for {tenant}")
            return None
        
        try:
            response = await self._notification_client.post_with_retry(
                url=f"{self._search_service_url}{EP_NAME_CATALOG_UPDATED}/{tenant}",
                success_statuses={200}
            )
            logger.info(f"Search service notified about catalog update for {tenant}")
            return True
            
        except Exception as e:
            logger.critical(
                f"FAILED to notify search service about catalog update for {tenant}: {str(e)}\n"
                f"Search service will continue using OLD catalog data for {tenant}!\n"
                f"Manual intervention may be required: POST {self._search_service_url}{EP_NAME_CATALOG_UPDATED}/{tenant}"
            )
            return False

    async def article_exists(self, article: str, tenant: str) -> bool:
        """Проверка существования артикула"""
        try:
            return await self._catalog.article_exists(article, tenant)
        except Exception as e:
            logger.error(f"Error checking article existence {article} in {tenant}: {e}")
            return False

    async def product_name_exists(self, product_name: str, tenant: str) -> bool:
        """Проверка существования названия товара"""
        try:
            return await self._catalog.product_name_exists(product_name, tenant)
        except Exception as e:
            logger.error(f"Error checking product name existence {product_name} in {tenant}: {e}")
            return False

    async def get_prod_descr_by_article(self, article: str, tenant: str) -> Optional[str]:
        """Получение описания товара по артикулу"""
        if not article:
            return None
        try:
            product_data = await self._catalog.get_by_article(article, tenant)
            if not product_data:
                return None
            return self._format_product_description(product_data)
        except Exception as e:
            logger.error(f"Error getting product by article {article}: {e}")
            return None
    
    async def get_articles_by_product(self, product_name: str, tenant: str) -> List[str]:
        """
        Получение списка артикулов по названию товара.
        
        Args:
            product_name: Название товара (очищенное, как в каталоге)
            tenant: Идентификатор тенанта
            
        Returns:
            Список артикулов для этого товара или пустой список если не найден
        """
        if not product_name or not tenant:
            logger.warning(f"Invalid arguments: product_name={product_name}, tenant={tenant}")
            return []
        try:
            return await self._catalog.get_articles_by_product(product_name, tenant)
        except Exception as e:
            logger.error(f"Error getting articles for product '{product_name}' (tenant: {tenant}): {e}")
            return []

    async def get_product_name_by_article(self, article: str, tenant: str) -> Optional[str]:
        """
        Получение наименования товара по артикулу.
        
        Args:
            article: Артикул товара
            tenant: Идентификатор тенанта
            
        Returns:
            str: Наименование товара или None если не найден
        """
        try:
            return await self._catalog.get_product_name_by_article(article, tenant)
        except Exception as e:
            logger.error(f"Error getting product name for article {article} (tenant: {tenant}): {e}")
            return None

    async def get_prod_descr_by_product(self, product_name: str, tenant: str) -> Optional[str]:
        """Получение описания товара по названию"""
        if not (product_name and tenant):
            return None
        try:
            product_data = await self._catalog.get_by_product(product_name, tenant)
            if not product_data:
                return None
            return self._format_product_description(product_data)
        except Exception as e:
            logger.error(f"Error getting description for product '{product_name}' (tenant: {tenant}): {e}")
            return None

    async def get_prod_descr_str(
            self,
            product: Optional[str] = None, 
            article: Optional[str] = None,
            tenant: str = ""
        ) -> Optional[str]:
        """
        Универсальная функция для получения описания товара.
        Приоритет: article > product
        """
        try:
            if not tenant:
                logger.error("Tenant not specified")
                return None
            
            # Случай 1: Есть артикул
            if article:
                article_desc = await self.get_prod_descr_by_article(article, tenant)
                if article_desc:
                    # Проверка конфликта
                    if product:
                        product_desc = await self.get_prod_descr_by_product(product, tenant)
                        if product_desc and article_desc != product_desc:
                            logger.warning(
                                f"Conflict detected: article={article}, product={product}, tenant={tenant}"
                            )
                    return article_desc
                logger.warning(f"Article {article} not found, trying by product name")
            
            # Случай 2: Есть только название или артикул не найден
            if product:
                return await self.get_prod_descr_by_product(product, tenant)
            
            return None
        except Exception as e:
            logger.error(f"Error in get_prod_descr_str: {e}")
            return None

    async def update_catalog_data(
            self,
            tenant: str, 
            products_by_article: Dict[str, Dict],
            product_index: Dict[str, List[str]],
        ):
        """Обновление каталога"""
        try:
            await self._catalog.update_products_batch(
                tenant=tenant,
                products_by_article=products_by_article,
                product_index=product_index,
            )
            logger.info(f"Сatalog updated for {tenant}: {len(products_by_article)} articles, "
                    f"{len(product_index)} products")
        except Exception as e:
            logger.error(f"Error updating catalog: {e}")
            raise

    def _format_product_description(self, product_data: Dict) -> str:
        """Форматирование данных товара в строку для промпта"""
        try:
            if COMMON_CHARACTERISTICS_FIELD in product_data:
                return self._format_generalized_description(product_data)
            else:
                return self._format_single_product_description(product_data)
        except Exception as e:
            logger.error(f"Error formatting product description: {e}")
            return f"Модель: {product_data.get(NAME_FIELD, 'Unknown')}"

    def _format_single_product_description(self, product_data: Dict) -> str:
        """Форматирование описания одиночного товара"""
        lines = []
        
        name = product_data.get(NAME_FIELD, '')
        category = product_data.get(CATEGORY_FIELD, '')
        
        if name:
            lines.append(f"Модель: {name}")
        if category:
            lines.append(f"Категория: {category}")
        
        characteristics = product_data.get(CHARACTERISTICS_FIELD, {})
        if characteristics:
            lines.append("\nХарактеристики:")
            for key, value in sorted(characteristics.items()):
                if value:
                    lines.append(f"- {key}: {value}")
        
        return "\n".join(lines)

    def _format_generalized_description(self, product_data: Dict) -> str:
        """Форматирование обобщенного описания"""
        lines = []
        
        name = product_data.get(NAME_FIELD, '')
        category = product_data.get(CATEGORY_FIELD, '')
        articles = product_data.get(ARTICLES_FIELD, [])
        common_chars = product_data.get(COMMON_CHARACTERISTICS_FIELD, {})
        diff_chars = product_data.get(DIFFERENT_CHARACTERISTICS_FIELD, {})
        
        if name:
            lines.append(f"Модель: {name}")
        if category:
            lines.append(f"Категория: {category}")
        if articles:
            lines.append(f"Артикулы: {', '.join(articles)}")
        
        if common_chars:
            lines.append("\nОбщие характеристики:")
            for key, value in sorted(common_chars.items()):
                if value:
                    lines.append(f"- {key}: {value}")
        
        if diff_chars:
            lines.append("\nРазличия по конфигурациям:")
            article_data = {}
            for char_name, values_by_article in diff_chars.items():
                for article, value in values_by_article.items():
                    if article not in article_data:
                        article_data[article] = []
                    if value:
                        article_data[article].append(f"{char_name}: {value}")
            
            for article, char_list in sorted(article_data.items()):
                if char_list:
                    lines.append(f"- {article}:")
                    for char_desc in char_list:
                        lines.append(f"  * {char_desc}")
        
        return "\n".join(lines)
    
    
    async def __aenter__(self):
        """Вход в контекстный менеджер."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Выход из контекстного менеджера с гарантированным закрытием ресурсов.
        
        Args:
            exc_type: Тип исключения (если было)
            exc_val: Значение исключения
            exc_tb: Трассировка исключения
        """
        await self.close()
        
    
    async def close(self):
        """Корректное закрытие всех ресурсов"""
        await self._catalog.close()
        
        if self._search_client:
            await self._search_client.close()
        if self._notification_client:
            await self._notification_client.close()
            
        logger.info("CatalogService resources closed")