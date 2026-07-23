from aiogram import Router
from .channel import router as channel_router
from .private import router as private_router

router = Router()
router.include_router(channel_router)
router.include_router(private_router)
