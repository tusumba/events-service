from fastapi import APIRouter

from app.api.v1 import events, example

router = APIRouter(prefix="/v1")
router.include_router(example.router)
router.include_router(events.router)
