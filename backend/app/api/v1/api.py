from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.admin import router as admin_router
from app.api.v1.messages import router as messages_router
from app.api.v1.devices import router as devices_router
from app.api.v1.incoming import router as incoming_router
from app.api.v1.webhooks import router as webhooks_router

api_v1_router = APIRouter()

api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(messages_router)
api_v1_router.include_router(devices_router)
api_v1_router.include_router(incoming_router)
api_v1_router.include_router(webhooks_router)
