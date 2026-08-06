class CatalogError(Exception):
    """Base exception for catalog business rules."""


class ProductNotFoundError(CatalogError):
    def __init__(self, query: str) -> None:
        super().__init__(f"Product not found: {query}")
        self.query = query
