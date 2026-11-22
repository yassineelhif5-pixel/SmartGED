"""Permission catalogue and system role templates.

Permissions are ``resource:action`` codes. Tenant roles are rows in the DB and
fully customisable; the templates below are only used when a tenant is
provisioned (and to keep the catalogue in sync on startup).
"""

from __future__ import annotations

RESOURCES: dict[str, list[str]] = {
    "document": ["create", "read", "update", "delete", "download", "share", "validate", "approve"],
    "folder": ["create", "read", "update", "delete"],
    "document_type": ["create", "read", "update", "delete"],
    "metadata": ["read", "update", "validate"],
    "user": ["create", "read", "update", "delete", "administer"],
    "role": ["create", "read", "update", "delete"],
    "group": ["create", "read", "update", "delete"],
    "tenant_settings": ["read", "administer"],
    "audit": ["read"],
    "processing": ["read", "administer"],
    "workflow": ["create", "read", "update", "delete", "approve"],
    "connector": ["create", "read", "update", "delete", "administer"],
    "ai_assistant": ["read"],
    "prompt": ["create", "read", "update", "delete", "administer"],
    "license": ["read", "administer"],
    "report": ["read"],
    # Saved document views: every user manages their own; "administer" = shared tenant views.
    "document_view": ["administer"],
    # Non-document business objects (suppliers, customers, projects…) and their designer.
    "object_type": ["create", "read", "update", "delete"],
    "business_object": ["create", "read", "update", "delete"],
}

ALL_PERMISSIONS: list[str] = [f"{r}:{a}" for r, actions in RESOURCES.items() for a in actions]

_READ = [p for p in ALL_PERMISSIONS if p.endswith(":read") and not p.startswith(("audit", "user", "role", "license", "tenant_settings", "prompt", "connector"))]

SYSTEM_ROLES: dict[str, dict[str, object]] = {
    "tenant_admin": {
        "name": "Tenant Admin",
        "description": "Full administration of the organisation",
        "permissions": ALL_PERMISSIONS,
    },
    "department_admin": {
        "name": "Department Admin",
        "description": "Manages users and documents of a department",
        "permissions": sorted(
            set(_READ)
            | {"user:read", "user:create", "user:update", "group:read", "group:update", "role:read"}
            | {"document_view:administer", "business_object:create", "business_object:update"}
            | {f"document:{a}" for a in RESOURCES["document"]}
            | {f"folder:{a}" for a in RESOURCES["folder"]}
            | {"metadata:update", "metadata:validate"}
        ),
    },
    "document_manager": {
        "name": "Document Manager",
        "description": "Manages documents, folders, document types and validation",
        "permissions": sorted(
            set(_READ)
            | {f"document:{a}" for a in RESOURCES["document"]}
            | {f"folder:{a}" for a in RESOURCES["folder"]}
            | {f"document_type:{a}" for a in RESOURCES["document_type"]}
            | {f"object_type:{a}" for a in RESOURCES["object_type"]}
            | {f"business_object:{a}" for a in RESOURCES["business_object"]}
            | {"metadata:update", "metadata:validate", "processing:administer", "document_view:administer"}
        ),
    },
    "workflow_manager": {
        "name": "Workflow Manager",
        "description": "Designs and operates workflows",
        "permissions": sorted(set(_READ) | {f"workflow:{a}" for a in RESOURCES["workflow"]}),
    },
    "standard_user": {
        "name": "Standard User",
        "description": "Uploads, edits and downloads documents",
        "permissions": sorted(
            set(_READ)
            | {"document:create", "document:update", "document:download", "folder:create", "metadata:update",
               "business_object:create"}
        ),
    },
    "read_only": {
        "name": "Read Only User",
        "description": "Consults documents",
        "permissions": sorted(set(_READ) | {"document:download"}),
    },
}

# Platform roles map to capabilities on the platform (not inside a tenant).
PLATFORM_CAPABILITIES: dict[str, set[str]] = {
    "super_admin": {"platform:read", "platform:administer"},
    "support_admin": {"platform:read"},
    "auditor": {"platform:read", "platform:audit"},
}
