# src/catalog_service/models.py

from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Optional

class ProductDescription(BaseModel):
    """
    Универсальная модель описания товара (одиночного или обобщенного).

    ВАЖНО: низкоуровневый CatalogClient работает со словарями,
    поэтому полей данной модели должны соответствовать ключам в CatalogClient:
    ```
    COMMON_CHARACTERISTICS_FIELD,       # "common_characteristics"
    DIFFERENT_CHARACTERISTICS_FIELD,    # "different_characteristics"
    ARTICLES_FIELD,                     # "articles"
    CATEGORY_FIELD,                     # "category"
    NAME_FIELD,                         # "name"
    CHARACTERISTICS_FIELD               # "characteristics"
    ```
    """
    
    # Общие поля
    name: Optional[str] = None
    category: Optional[str] = None
    
    # Для одиночного товара
    characteristics: Dict[str, str] = Field(default_factory=dict)
    
    # Для обобщенного товара
    articles: List[str] = Field(default_factory=list)
    common_characteristics: Dict[str, str] = Field(default_factory=dict)
    different_characteristics: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    
    @model_validator(mode='after')
    def validate_model_type(self) -> 'ProductDescription':
        # Одиночный товар: есть характеристики, нет обобщенных полей
        if self.characteristics and not self.common_characteristics:
            return self
        
        # Обобщенный товар: есть общие/различные характеристики
        if self.common_characteristics or self.different_characteristics:
            return self
        
        # Минимально валидный случай
        if self.name or self.articles:
            return self
        
        raise ValueError('Invalid product description: no data provided')