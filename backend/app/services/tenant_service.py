"""Tenant lifecycle: provisioning, suspension, reactivation, archiving.

All functions here are *platform* operations and must be called with a
session opened in bypass mode by an authorised platform principal.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models import (
    Document,
    DocumentType,
    DocumentVersion,
    Folder,
    MembershipStatus,
    MetadataDataType,
    MetadataDefinition,
    ObjectType,
    Permission,
    Role,
    RolePermission,
    SubscriptionPlan,
    SystemSetting,
    Tenant,
    TenantModule,
    TenantQuota,
    TenantStatus,
    User,
    UserRole,
    UserTenant,
)
from app.security.crypto import hash_password, validate_password_strength
from app.security.permissions import ALL_PERMISSIONS, SYSTEM_ROLES

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$")

DEFAULT_PLANS = [
    {"code": "starter", "name": "Starter", "max_users": 10, "max_storage_bytes": 20 * 1024**3,
     "monthly_ai_credits": 2_000, "modules": ["ged", "ocr"]},
    {"code": "business", "name": "Business", "max_users": 100, "max_storage_bytes": 500 * 1024**3,
     "monthly_ai_credits": 25_000, "modules": ["ged", "ocr", "ai", "search", "workflows", "connectors"]},
    {"code": "enterprise", "name": "Enterprise", "max_users": 5_000, "max_storage_bytes": 10 * 1024**4,
     "monthly_ai_credits": 250_000,
     "modules": ["ged", "ocr", "ai", "search", "workflows", "connectors", "projects", "reporting", "sso"]},
]

DEFAULT_SYSTEM_SETTINGS = {
    "ocr.languages": {"value": "fra+eng", "description": "Default Tesseract languages"},
    "ai.confidence_threshold": {"value": 0.85, "description": "Below this score a field requires human validation"},
    "ai.business_rules": {"value": "", "description": "Free-text business rules given to the extraction prompt"},
    "documents.retention_days_trash": {"value": 30, "description": "Days before trashed documents may be purged"},
}

# Starter document types created for every new tenant (editable; nothing is hard-coded in the engine).
STARTER_TYPES: list[dict] = [
    {
        "code": "invoice", "name": "Facture", "color": "#2563eb", "icon": "receipt", "requires_validation": True,
        "classification_hints": "Facture fournisseur: numéro de facture, TVA, montant TTC, échéance.",
        "fields": [
            ("invoice_number", "N° de facture", MetadataDataType.text, True),
            ("invoice_date", "Date de facture", MetadataDataType.date, True),
            ("supplier_ref", "Fiche fournisseur", MetadataDataType.reference, False,
             {"object_type_code": "supplier", "autofill": True}),
            ("supplier_name", "Fournisseur", MetadataDataType.text, True),
            ("supplier_vat", "TVA fournisseur", MetadataDataType.text, False),
            ("total_amount", "Montant TTC", MetadataDataType.currency, True),
            ("vat_amount", "Montant TVA", MetadataDataType.currency, False),
            ("currency", "Devise", MetadataDataType.text, False),
            ("due_date", "Échéance", MetadataDataType.date, False),
        ],
    },
    {
        "code": "contract", "name": "Contrat", "color": "#7c3aed", "icon": "file-signature", "requires_validation": True,
        "classification_hints": "Contrat entre parties: objet, durée, date d'effet, signature.",
        "fields": [
            ("contract_reference", "Référence", MetadataDataType.text, False),
            ("counterparty", "Cocontractant", MetadataDataType.text, True),
            ("effective_date", "Date d'effet", MetadataDataType.date, True),
            ("end_date", "Date de fin", MetadataDataType.date, False),
            ("contract_value", "Montant", MetadataDataType.currency, False),
        ],
    },
    {
        "code": "letter", "name": "Courrier", "color": "#0891b2", "icon": "mail", "requires_validation": False,
        "classification_hints": "Courrier entrant ou sortant: expéditeur, destinataire, objet.",
        "fields": [
            ("sender", "Expéditeur", MetadataDataType.text, False),
            ("recipient", "Destinataire", MetadataDataType.text, False),
            ("subject", "Objet", MetadataDataType.text, False),
            ("letter_date", "Date", MetadataDataType.date, False),
        ],
    },
]


# Starter business-object types (non-document reference data). Fully editable by the tenant.
STARTER_OBJECT_TYPES: list[dict] = [
    {
        "code": "supplier", "name": "Fournisseur", "color": "#0d9488", "icon": "truck",
        "description": "Référentiel fournisseurs : alimente automatiquement les factures.",
        "fields": [
            ("supplier_vat", "N° TVA", MetadataDataType.text, False),
            ("siret", "SIRET", MetadataDataType.text, False),
            ("iban", "IBAN", MetadataDataType.text, False, {}, True),
            ("email", "E-mail", MetadataDataType.text, False),
            ("address", "Adresse", MetadataDataType.long_text, False),
            ("payment_terms_days", "Délai de paiement (jours)", MetadataDataType.integer, False),
        ],
    },
    {
        "code": "customer", "name": "Client", "color": "#ea580c", "icon": "building",
        "description": "Référentiel clients.",
        "fields": [
            ("customer_vat", "N° TVA", MetadataDataType.text, False),
            ("email", "E-mail", MetadataDataType.text, False),
            ("address", "Adresse", MetadataDataType.long_text, False),
        ],
    },
    {
        "code": "project", "name": "Projet", "color": "#4f46e5", "icon": "folder-kanban",
        "description": "Projets auxquels rattacher contrats, factures et livrables.",
        "fields": [
            ("project_manager", "Chef de projet", MetadataDataType.text, False),
            ("start_date", "Début", MetadataDataType.date, False),
            ("end_date", "Fin", MetadataDataType.date, False),
            ("budget", "Budget", MetadataDataType.currency, False),
        ],
    },
]


def sync_permission_catalogue(db: Session) -> None:
    existing = set(db.scalars(select(Permission.code)).all())
    for code in ALL_PERMISSIONS:
        if code not in existing:
            resource, action = code.split(":")
            db.add(Permission(code=code, resource=resource, action=action))
    db.flush()


def ensure_platform_defaults(db: Session) -> None:
    sync_permission_catalogue(db)
    existing_plans = set(db.scalars(select(SubscriptionPlan.code)).all())
    for plan in DEFAULT_PLANS:
        if plan["code"] not in existing_plans:
            db.add(SubscriptionPlan(**plan))
    existing_settings = set(db.scalars(select(SystemSetting.key)).all())
    for key, spec in DEFAULT_SYSTEM_SETTINGS.items():
        if key not in existing_settings:
            db.add(SystemSetting(key=key, value=spec["value"], description=spec["description"]))
    db.flush()


def ensure_system_roles(db: Session, tenant_id: uuid.UUID) -> dict[str, Role]:
    roles = {r.code: r for r in db.scalars(select(Role).where(Role.tenant_id == tenant_id)).all()}
    for code, spec in SYSTEM_ROLES.items():
        role = roles.get(code)
        if role is None:
            role = Role(tenant_id=tenant_id, code=code, name=str(spec["name"]),
                        description=str(spec["description"]), is_system=True)
            db.add(role)
            db.flush()
            roles[code] = role
        current = {p.permission_code for p in role.permissions}
        for perm in spec["permissions"]:  # type: ignore[union-attr]
            if perm not in current:
                role.permissions.append(RolePermission(tenant_id=tenant_id, permission_code=perm))
    db.flush()
    return roles


@dataclass
class ProvisionResult:
    tenant: Tenant
    admin: User
    created_admin: bool


def provision_tenant(
    db: Session,
    *,
    name: str,
    slug: str,
    plan_code: str,
    admin_email: str,
    admin_full_name: str,
    admin_password: str | None,
    with_starter_types: bool = True,
) -> ProvisionResult:
    slug = slug.lower().strip()
    if not SLUG_RE.match(slug):
        raise ValidationFailed("Slug must be 3-63 chars of lowercase letters, digits and hyphens")
    if db.scalar(select(Tenant.id).where(Tenant.slug == slug)):
        raise Conflict("A tenant with this slug already exists", code="slug_taken")
    plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == plan_code, SubscriptionPlan.is_active))
    if plan is None:
        raise NotFound(f"Unknown plan '{plan_code}'")

    # 1-2. identifier + organisation
    tenant = Tenant(name=name.strip(), slug=slug, plan_id=plan.id, status=TenantStatus.provisioning,
                    storage_provider=get_settings().storage_provider)
    db.add(tenant)
    db.flush()

    # 5-6, 8. plan, quotas, modules
    for metric, limit in (("users", plan.max_users), ("storage_bytes", plan.max_storage_bytes),
                          ("ai_credits_monthly", plan.monthly_ai_credits)):
        db.add(TenantQuota(tenant_id=tenant.id, metric=metric, limit_value=limit))
    for module in plan.modules:
        db.add(TenantModule(tenant_id=tenant.id, module=module, enabled=True))

    # Roles + 4. administrator
    roles = ensure_system_roles(db, tenant.id)
    email = admin_email.strip().lower()
    admin = db.scalar(select(User).where(User.email == email))
    created_admin = False
    if admin is None:
        if not admin_password:
            raise ValidationFailed("admin_password is required for a new administrator")
        validate_password_strength(admin_password)
        admin = User(email=email, full_name=admin_full_name, password_hash=hash_password(admin_password),
                     password_changed_at=datetime.now(UTC))
        db.add(admin)
        db.flush()
        created_admin = True
    db.add(UserTenant(tenant_id=tenant.id, user_id=admin.id, status=MembershipStatus.active))
    db.add(UserRole(tenant_id=tenant.id, user_id=admin.id, role_id=roles["tenant_admin"].id))

    # 10. document space
    for folder_name in ("Général", "Factures", "Contrats", "Courrier"):
        db.add(Folder(tenant_id=tenant.id, name=folder_name, created_by=admin.id))
    if with_starter_types:
        for spec in STARTER_OBJECT_TYPES:
            create_object_type_from_spec(db, tenant.id, spec)
        for spec in STARTER_TYPES:
            create_type_from_spec(db, tenant.id, spec)

    tenant.status = TenantStatus.active
    db.flush()
    return ProvisionResult(tenant=tenant, admin=admin, created_admin=created_admin)


def create_type_from_spec(db: Session, tenant_id: uuid.UUID, spec: dict) -> DocumentType:
    dtype = DocumentType(
        tenant_id=tenant_id, code=spec["code"], name=spec["name"], color=spec.get("color"),
        icon=spec.get("icon"), requires_validation=spec.get("requires_validation", False),
        classification_hints=spec.get("classification_hints"),
    )
    for pos, (tech, label, dtype_enum, required, *rest) in enumerate(spec["fields"]):
        dtype.fields.append(MetadataDefinition(
            tenant_id=tenant_id, technical_name=tech, display_name=label, data_type=dtype_enum,
            required=required, position=pos, validation_rules=rest[0] if rest else {},
            ai_extraction_enabled=dtype_enum != MetadataDataType.reference,
            requires_human_validation=dtype_enum in (MetadataDataType.currency, MetadataDataType.decimal),
        ))
    db.add(dtype)
    db.flush()
    return dtype


def create_object_type_from_spec(db: Session, tenant_id: uuid.UUID, spec: dict) -> ObjectType:
    otype = ObjectType(tenant_id=tenant_id, code=spec["code"], name=spec["name"], color=spec.get("color"),
                       icon=spec.get("icon"), description=spec.get("description"))
    db.add(otype)
    db.flush()
    for pos, (tech, label, dtype_enum, required, *rest) in enumerate(spec["fields"]):
        otype.fields.append(MetadataDefinition(
            tenant_id=tenant_id, object_type_id=otype.id, technical_name=tech, display_name=label,
            data_type=dtype_enum, required=required, position=pos, validation_rules=rest[0] if rest else {},
            sensitive=bool(rest[1]) if len(rest) > 1 else False, ai_extraction_enabled=False))
    db.flush()
    return otype


def set_status(db: Session, tenant_id: uuid.UUID, status: TenantStatus) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFound("Tenant not found")
    now = datetime.now(UTC)
    tenant.status = status
    if status == TenantStatus.suspended:
        tenant.suspended_at = now
    elif status == TenantStatus.active:
        tenant.suspended_at = None
    elif status == TenantStatus.archived:
        tenant.archived_at = now
    db.flush()
    return tenant


def tenant_usage(db: Session, tenant_id: uuid.UUID) -> dict[str, int]:
    users = db.scalar(select(func.count()).select_from(UserTenant).where(
        UserTenant.tenant_id == tenant_id, UserTenant.status != MembershipStatus.disabled)) or 0
    docs = db.scalar(select(func.count()).select_from(Document).where(
        Document.tenant_id == tenant_id, Document.deleted_at.is_(None))) or 0
    storage = db.scalar(select(func.coalesce(func.sum(DocumentVersion.file_size), 0)).where(
        DocumentVersion.tenant_id == tenant_id)) or 0
    return {"users": int(users), "documents": int(docs), "storage_bytes": int(storage)}


def get_quota(db: Session, tenant_id: uuid.UUID, metric: str) -> int | None:
    return db.scalar(select(TenantQuota.limit_value).where(
        TenantQuota.tenant_id == tenant_id, TenantQuota.metric == metric))
