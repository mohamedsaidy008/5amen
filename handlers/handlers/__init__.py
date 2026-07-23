from aiogram import Router
from .common import router as common_router
from .admin import router as admin_router
from .player import router as player_router

router = Router()
router.include_router(common_router)
router.include_router(admin_router)
router.include_router(player_router)
