import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { createBrowserRouter, Navigate, Outlet, useLocation } from "react-router-dom";
import { refreshSession } from "@/api/client";
import { useCan, useSessionStore } from "@/stores/session";
import { AppShell } from "@/layouts/AppShell";
import { LoginPage } from "@/pages/LoginPage";
import { Spinner } from "@/components/ui/primitives";

const DashboardPage = lazy(() => import("@/pages/DashboardPage"));
const DocumentsPage = lazy(() => import("@/pages/DocumentsPage"));
const DocumentViewerPage = lazy(() => import("@/pages/DocumentViewerPage"));
const ValidationPage = lazy(() => import("@/pages/ValidationPage"));
const ProcessingPage = lazy(() => import("@/pages/ProcessingPage"));
const TrashPage = lazy(() => import("@/pages/TrashPage"));
const DocumentTypesPage = lazy(() => import("@/pages/DocumentTypesPage"));
const UsersPage = lazy(() => import("@/pages/UsersPage"));
const AuditPage = lazy(() => import("@/pages/AuditPage"));
const PlatformPage = lazy(() => import("@/pages/PlatformPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const RoadmapPage = lazy(() => import("@/pages/RoadmapPage"));
const ObjectsPage = lazy(() => import("@/pages/ObjectsPage"));
const ObjectTypesPage = lazy(() => import("@/pages/ObjectTypesPage"));

function FullScreenLoader() {
  return (
    <div className="flex h-full items-center justify-center">
      <Spinner className="size-6" />
    </div>
  );
}

/** Restores the session from the httpOnly refresh cookie on first load. */
function RequireAuth() {
  const { session, ready, markReady } = useSessionStore();
  const location = useLocation();
  useEffect(() => {
    if (!ready) refreshSession().finally(markReady);
  }, [ready, markReady]);
  if (!ready) return <FullScreenLoader />;
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <Outlet />;
}

function RequirePerm({ perm, children }: { perm: string; children: ReactNode }) {
  const can = useCan();
  if (!can(perm)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function RequirePlatform({ children }: { children: ReactNode }) {
  const caps = useSessionStore((s) => s.session?.platform_capabilities ?? []);
  if (!caps.includes("platform:read")) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function TenantHome() {
  const session = useSessionStore((s) => s.session);
  if (!session?.tenant) return <Navigate to="/platform" replace />;
  return <DashboardPage />;
}

const s = (node: ReactNode) => <Suspense fallback={<FullScreenLoader />}>{node}</Suspense>;

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: s(<TenantHome />) },
          { path: "/documents", element: s(<RequirePerm perm="document:read"><DocumentsPage /></RequirePerm>) },
          { path: "/documents/:id", element: s(<RequirePerm perm="document:read"><DocumentViewerPage /></RequirePerm>) },
          { path: "/validation", element: s(<RequirePerm perm="metadata:validate"><ValidationPage /></RequirePerm>) },
          { path: "/processing", element: s(<RequirePerm perm="processing:read"><ProcessingPage /></RequirePerm>) },
          { path: "/trash", element: s(<RequirePerm perm="document:delete"><TrashPage /></RequirePerm>) },
          { path: "/admin/document-types", element: s(<RequirePerm perm="document_type:read"><DocumentTypesPage /></RequirePerm>) },
          { path: "/objects", element: s(<RequirePerm perm="business_object:read"><ObjectsPage /></RequirePerm>) },
          { path: "/admin/object-types", element: s(<RequirePerm perm="object_type:read"><ObjectTypesPage /></RequirePerm>) },
          { path: "/admin/users", element: s(<RequirePerm perm="user:read"><UsersPage /></RequirePerm>) },
          { path: "/admin/audit", element: s(<RequirePerm perm="audit:read"><AuditPage /></RequirePerm>) },
          { path: "/platform", element: s(<RequirePlatform><PlatformPage /></RequirePlatform>) },
          { path: "/settings", element: s(<SettingsPage />) },
          { path: "/roadmap", element: s(<RoadmapPage />) },
          { path: "*", element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
]);
