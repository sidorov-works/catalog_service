# src/catalog_service/__init__.py

from .service import CatalogService
from .connection_pool import CatalogConnectionPool
from .models import ProductDescription
from http_utils import AuthType


# Это то, что будет доступно при "from catalog_service import *"
__all__ = [
    "CatalogService",        # Основной класс для импорта
    "CatalogConnectionPool", # Класс, представляющий пул соединений с каталогом
    "AuthType",              # Тип аутентификации поискового сервиса
    "ProductDescription"     # pydantic модель описания товара
]