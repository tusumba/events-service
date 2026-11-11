from fastapi import APIRouter

from app.api.v1 import example

router = APIRouter(prefix="/v1")
router.include_router(example.router)
