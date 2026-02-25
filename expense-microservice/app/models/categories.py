from pydantic import BaseModel, Field


class CategoryResponse(BaseModel):
    category_code: int
    name: str


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
