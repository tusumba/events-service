from fastapi import APIRouter

from app.api.v1 import clubs, events, example

router = APIRouter(prefix="/v1")
router.include_router(example.router)
router.include_router(events.router)
router.include_router(clubs.router)
