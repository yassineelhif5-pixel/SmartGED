"""Import every model so Alembic and the mapper registry see the full schema."""

from app.models.ai import (
    AIModelPrice,
    AIPrompt,
    AIPromptTest,
    AIPromptVersion,
    AIProvider,
    AIUsageEvent,
    PromptStatus,
    ProviderKind,
)
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
from app.models.knowledge import DocumentChunk, LinaConversation, LinaMessage
from app.models.objects import BusinessObject, DocumentObjectLink, ObjectStatus, ObjectType
from app.models.splitting import DocumentSplitProposal, SplitStatus
from app.models.tenant import (
    SubscriptionPlan,
    SystemSetting,
    Tenant,
    TenantModule,
    TenantQuota,
    TenantSetting,
    TenantStatus,
)
from app.models.views import DocumentView, UserPreference, ViewScope

__all__ = [
    "DocumentChunk", "LinaConversation", "LinaMessage",
    "DocumentSplitProposal", "SplitStatus",
    "AuditLog", "Notification", "Document", "DocumentMetadataValue", "DocumentRelation", "DocumentStatus",
    "DocumentTag", "DocumentType", "DocumentVersion", "Folder", "MetadataDataType", "MetadataDefinition",
    "OcrPage", "ProcessingJob", "StepStatus", "Group", "GroupMember", "MembershipStatus", "Permission",
    "PlatformRole", "Role", "RolePermission", "User", "UserRole", "UserSession", "UserTenant",
    "SubscriptionPlan", "SystemSetting", "Tenant", "TenantModule", "TenantQuota", "TenantSetting",
    "TenantStatus", "BusinessObject", "DocumentObjectLink", "ObjectStatus", "ObjectType", "DocumentView",
    "UserPreference", "ViewScope", "AIModelPrice", "AIPrompt", "AIPromptTest", "AIPromptVersion", "AIProvider",
    "AIUsageEvent", "PromptStatus", "ProviderKind",
]
