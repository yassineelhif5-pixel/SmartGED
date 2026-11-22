import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Blocks,
  Bot,
  Boxes,
  BrainCircuit,
  Building2,
  ChevronsUpDown,
  ClipboardCheck,
  Cpu,
  FolderTree,
  GitBranch,
  Inbox,
  LayoutDashboard,
  LogOut,
  Monitor,
  Moon,
  ScrollText,
  Settings,
  Shapes,
  Sun,
  Trash2,
  Users,
  Waypoints,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useCan, useSessionStore, useUiStore } from "@/stores/session";
import type { Session } from "@/types/api";
import { cn, initials } from "@/utils/format";
import {
  DropdownContent,
  DropdownItem,
  DropdownLabel,
  DropdownMenu,
  DropdownSeparator,
  DropdownTrigger,
} from "@/components/ui/overlay";
import { GlobalSearch } from "@/features/GlobalSearch";

type NavItem = { to: string; label: string; icon: typeof LayoutDashboard; perm?: string; soon?: boolean };

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Espace documentaire",
    items: [
      { to: "/", label: "Tableau de bord", icon: LayoutDashboard },
      { to: "/documents", label: "Documents", icon: FolderTree, perm: "document:read" },
      { to: "/objects", label: "Référentiels", icon: Boxes, perm: "business_object:read" },
      { to: "/validation", label: "Validation", icon: ClipboardCheck, perm: "metadata:validate" },
      { to: "/processing", label: "Traitements", icon: Cpu, perm: "processing:read" },
      { to: "/trash", label: "Corbeille", icon: Trash2, perm: "document:delete" },
    ],
  },
  {
    section: "Intelligence",
    items: [
      { to: "/roadmap#ai", label: "Assistant Lina", icon: Bot, soon: true },
      { to: "/roadmap#workflows", label: "Workflows", icon: GitBranch, soon: true },
      { to: "/roadmap#ingestion", label: "Ingestion Hub", icon: Inbox, soon: true },
    ],
  },
  {
    section: "Administration",
    items: [
      { to: "/admin/document-types", label: "Types documentaires", icon: Shapes, perm: "document_type:read" },
      { to: "/admin/ai", label: "Intelligence IA", icon: BrainCircuit, perm: "prompt:read" },
      { to: "/admin/object-types", label: "Types d'objets", icon: Blocks, perm: "object_type:update" },
      { to: "/admin/users", label: "Utilisateurs & rôles", icon: Users, perm: "user:read" },
      { to: "/admin/audit", label: "Journal d'audit", icon: ScrollText, perm: "audit:read" },
    ],
  },
];

function NavEntry({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.to}
      end={item.to === "/"}
      className={({ isActive }) =>
        cn(
          "group flex items-center gap-3 rounded-md px-3 py-2 text-[13px] font-medium transition-colors",
          isActive && !item.soon
            ? "bg-sidebar-active text-white"
            : "text-sidebar-foreground/80 hover:bg-sidebar-active/60 hover:text-white",
        )
      }
    >
      <item.icon className="size-4 shrink-0 opacity-90" />
      <span className="truncate">{item.label}</span>
      {item.soon && (
        <span className="ml-auto rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-sidebar-muted">
          À venir
        </span>
      )}
    </NavLink>
  );
}

export function AppShell() {
  const session = useSessionStore((s) => s.session)!;
  const setSession = useSessionStore((s) => s.setSession);
  const { theme, setTheme } = useUiStore();
  const can = useCan();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const isPlatform = session.platform_capabilities.includes("platform:read");

  const switchTenant = async (tenantId: string) => {
    try {
      const s = await api<Session>("/auth/switch-tenant", { method: "POST", body: { tenant_id: tenantId } });
      setSession(s);
      qc.clear();
      navigate("/");
      toast.success(`Organisation : ${s.tenant?.name}`);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const logout = async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      setSession(null);
      qc.clear();
      navigate("/login");
    }
  };

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 flex-col bg-sidebar text-sidebar-foreground md:flex">
        <Link to="/" className="flex h-14 items-center gap-2.5 px-5">
          <img src="/favicon.svg" alt="" className="size-7" />
          <span className="text-[15px] font-semibold tracking-tight text-white">
            DocuMind <span className="text-blue-300">AI</span>
          </span>
        </Link>

        {session.tenant && (
          <DropdownMenu>
            <DropdownTrigger asChild>
              <button className="mx-3 mb-3 flex items-center gap-2.5 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-left hover:bg-white/10">
                <div className="flex size-7 items-center justify-center rounded-md bg-blue-500/20 text-xs font-semibold text-blue-200">
                  {initials(session.tenant.name)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-white">{session.tenant.name}</div>
                  <div className="truncate text-[11px] text-sidebar-muted">{session.tenant.slug}</div>
                </div>
                <ChevronsUpDown className="size-3.5 text-sidebar-muted" />
              </button>
            </DropdownTrigger>
            <DropdownContent align="start">
              <DropdownLabel>Organisations</DropdownLabel>
              {session.tenants.map((t) => (
                <DropdownItem key={t.id} onSelect={() => t.id !== session.tenant?.id && switchTenant(t.id)}>
                  <Building2 /> {t.name}
                  {t.id === session.tenant?.id && <span className="ml-auto text-xs text-primary">actif</span>}
                </DropdownItem>
              ))}
            </DropdownContent>
          </DropdownMenu>
        )}

        <nav className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-3 pb-4">
          {session.tenant &&
            NAV.map((group) => {
              const items = group.items.filter((i) => !i.perm || can(i.perm));
              if (!items.length) return null;
              return (
                <div key={group.section}>
                  <div className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-sidebar-muted">
                    {group.section}
                  </div>
                  <div className="space-y-0.5">
                    {items.map((item) => (
                      <NavEntry key={item.to} item={item} />
                    ))}
                  </div>
                </div>
              );
            })}
          {isPlatform && (
            <div>
              <div className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-sidebar-muted">
                Pilot · Plateforme
              </div>
              <NavEntry item={{ to: "/platform", label: "Tenants & plans", icon: Waypoints }} />
            </div>
          )}
        </nav>
        <div className="border-t border-white/10 px-3 py-3">
          <NavEntry item={{ to: "/settings", label: "Paramètres", icon: Settings }} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-4 border-b bg-card px-4 md:px-6">
          {session.tenant ? <GlobalSearch /> : <div className="flex-1" />}
          <div className="ml-auto flex items-center gap-1">
            <button
              className="rounded-md p-2 text-muted-foreground hover:bg-muted"
              aria-label="Changer de thème"
              onClick={() => setTheme(theme === "light" ? "dark" : theme === "dark" ? "system" : "light")}
              title={`Thème : ${theme}`}
            >
              {theme === "light" ? <Sun className="size-4" /> : theme === "dark" ? <Moon className="size-4" /> : <Monitor className="size-4" />}
            </button>
            <DropdownMenu>
              <DropdownTrigger asChild>
                <button className="flex items-center gap-2 rounded-md py-1 pl-1 pr-2 hover:bg-muted" aria-label="Menu utilisateur">
                  <div className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                    {initials(session.user.full_name)}
                  </div>
                  <div className="hidden text-left sm:block">
                    <div className="text-[13px] font-medium leading-tight">{session.user.full_name}</div>
                    <div className="text-[11px] leading-tight text-muted-foreground">{session.user.email}</div>
                  </div>
                </button>
              </DropdownTrigger>
              <DropdownContent>
                <DropdownItem onSelect={() => navigate("/settings")}>
                  <Settings /> Paramètres du compte
                </DropdownItem>
                <DropdownSeparator />
                <DropdownItem onSelect={logout} destructive>
                  <LogOut /> Se déconnecter
                </DropdownItem>
              </DropdownContent>
            </DropdownMenu>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1400px] px-4 py-6 md:px-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
