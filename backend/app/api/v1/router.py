from fastapi import APIRouter

from app.api.v1.routers import (
    ai,
    auth,
    document_types,
    documents,
    folders,
    health,
    insights,
    objects,
    platform,
    users,
    views,
)

api_router = APIRouter()
for module in (health, auth, platform, users, folders, document_types, documents, insights, views, objects, ai):
    api_router.include_router(module.router)
