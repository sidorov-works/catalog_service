# src/catalog_service/connection_pool.py

"""
Класс-обертка над оригинальным пулом соединений Redis 
(чтобы полностью абстрагироваться от Redis в вызывающем коде)
"""

from redis.asyncio import ConnectionPool
from typing import Optional

class CatalogConnectionPool(ConnectionPool):
    """
    Пул соединений для каталога Redis.
    
    Создается через URL с явно заданными параметрами.
    Полностью совместим с оригинальным ConnectionPool.

    Args:
        url: URL подключения к БД с оперативным каталогом
        max_connections: Максимальное количество соединений в пуле. По умолчанию 100
        socket_timeout: Таймаут операций с сокетом (секунды). По умолчанию 10.0
        socket_connect_timeout: Таймаут подключения сокета (секунды). По умолчанию 10.0
        health_check_interval: Интервал проверки здоровья соединений (секунды). По умолчанию 30.0
        retry_on_timeout: Повторять операции при таймауте. По умолчанию True
        socket_keepalive: Включить keepalive для долгоживущих соединений. По умолчанию True
        decode_responses: Декодировать ответы в строки (False для бинарных данных). По умолчанию False
        **kwargs: Дополнительные параметры для ConnectionPool
    
    Пример:
    ```
        pool = CatalogConnectionPool(
            url="redis://localhost:6379/0", # URL подключения к БД с оперативным каталогом
            max_connections=10,             # Максимальное количество соединений в пуле
            socket_keepalive=True           # Включить keepalive для долгоживущих соединений
            )
        client = CatalogClient(redis_connection_pool=pool)
    ```
    """
    
    def __new__(
        cls,
        url: str,
        max_connections: Optional[int] = 100,
        socket_timeout: Optional[float] = 10.0,
        socket_connect_timeout: Optional[float] = 10.0,
        health_check_interval: Optional[float] = 30.0,
        retry_on_timeout: bool = True,
        socket_keepalive: bool = True,
        decode_responses: bool = False,
        **kwargs
    ) -> 'CatalogConnectionPool':
        """
        Создает пул соединений для каталога.
        
        Args:
            url: URL подключения к БД с оперативным каталогом
            max_connections: Максимальное количество соединений в пуле
            socket_timeout: Таймаут операций с сокетом (секунды)
            socket_connect_timeout: Таймаут подключения сокета (секунды)
            health_check_interval: Интервал проверки здоровья соединений (секунды)
            retry_on_timeout: Повторять операции при таймауте
            socket_keepalive: Включить keepalive для долгоживущих соединений
            decode_responses: Декодировать ответы в строки (False для бинарных данных)
            **kwargs: Дополнительные параметры для ConnectionPool
            
        Returns:
            CatalogConnectionPool: Экземпляр пула соединений
        """
        # ConnectionPool.from_url возвращает экземпляр ConnectionPool
        # Нам нужно вернуть экземпляр CatalogConnectionPool, но это тот же объект
        # Так как мы не добавляем новых атрибутов, можно просто вернуть результат from_url
        pool = ConnectionPool.from_url(
            url=url,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            health_check_interval=health_check_interval,
            retry_on_timeout=retry_on_timeout,
            socket_keepalive=socket_keepalive,
            decode_responses=decode_responses,
            **kwargs
        )
        # Меняем класс на наш (без изменения внутреннего состояния)
        pool.__class__ = cls
        return pool