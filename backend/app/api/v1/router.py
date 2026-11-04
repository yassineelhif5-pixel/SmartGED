from fastapi import APIRouter

from app.api.v1.routers import auth, document_types, documents, folders, health, insights, platform, users

api_router = APIRouter()
for module in (health, auth, platform, users, folders, document_types, documents, insights):
    api_router.include_router(module.router)
