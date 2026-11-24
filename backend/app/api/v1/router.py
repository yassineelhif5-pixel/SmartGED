from fastapi import APIRouter

from app.api.v1.routers import (
    ai,
    auth,
    document_types,
    documents,
    folders,
    health,
    insights,
    lina,
    objects,
    platform,
    splitting,
    users,
    views,
)

api_router = APIRouter()
for module in (health, auth, platform, users, folders, document_types, splitting, documents, insights, views, objects, ai, lina):
    api_router.include_router(module.router)
