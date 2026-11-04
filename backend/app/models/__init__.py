"""Import every model so Alembic and the mapper registry see the full schema."""

from app.models.audit import AuditLog, Notification
from app.models.ged import (
    Document,
    DocumentMetadataValue,
    DocumentRelation,
    DocumentStatus,
    DocumentTag,
    DocumentType,
    DocumentVersion,
    Folder,
    MetadataDataType,
    MetadataDefinition,
    OcrPage,
    ProcessingJob,
    StepStatus,
)
from app.models.identity import (
    Group,
    GroupMember,
    MembershipStatus,
    Permission,
    PlatformRole,
    Role,
    RolePermission,
    User,
    UserRole,
    UserSession,
    UserTenant,
)
from app.models.tenant import (
    SubscriptionPlan,
    SystemSetting,
    Tenant,
    TenantModule,
    TenantQuota,
    TenantSetting,
    TenantStatus,
)

__all__ = [
    "AuditLog", "Notification", "Document", "DocumentMetadataValue", "DocumentRelation", "DocumentStatus",
    "DocumentTag", "DocumentType", "DocumentVersion", "Folder", "MetadataDataType", "MetadataDefinition",
    "OcrPage", "ProcessingJob", "StepStatus", "Group", "GroupMember", "MembershipStatus", "Permission",
    "PlatformRole", "Role", "RolePermission", "User", "UserRole", "UserSession", "UserTenant",
    "SubscriptionPlan", "SystemSetting", "Tenant", "TenantModule", "TenantQuota", "TenantSetting",
    "TenantStatus",
]
