import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, MoreHorizontal, Plus, ShieldCheck, UserMinus, UserX, UserCheck } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useMembers, useRoles } from "@/hooks/queries";
import { useCan, useSessionStore } from "@/stores/session";
import type { Member, Role } from "@/types/api";
import { cn, formatDateTime, initials } from "@/utils/format";
import { Badge, Button, Card, Field, Input, PageHeader, Switch } from "@/components/ui/primitives";
import { ConfirmDialog, Dialog, DropdownContent, DropdownItem, DropdownMenu, DropdownSeparator, DropdownTrigger } from "@/components/ui/overlay";

export default function UsersPage() {
  const [tab, setTab] = useState<"members" | "roles">("members");
  const can = useCan();
  return (
    <>
      <PageHeader title="Utilisateurs & rôles" description="Gérez les membres de votre organisation, leurs rôles et leurs permissions." />
      <div className="mb-4 flex gap-1 border-b">
        {(["members", "roles"] as const).filter((t) => t === "members" || can("role:read")).map((t) => (
          <button key={t} onClick={() => setTab(t)}
                  className={cn("border-b-2 px-4 py-2 text-sm font-medium", tab === t ? "border-primary" : "border-transparent text-muted-foreground")}>
            {t === "members" ? "Membres" : "Rôles & permissions"}
          </button>
        ))}
      </div>
      {tab === "members" ? <Members /> : <Roles />}
    </>
  );
}

function Members() {
  const { data: members = [] } = useMembers();
  const { data: roles = [] } = useRoles();
  const can = useCan();
  const me = useSessionStore((s) => s.session?.user.id);
  const qc = useQueryClient();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [editing, setEditing] = useState<Member | null>(null);
  const [pwdFor, setPwdFor] = useState<Member | null>(null);
  const [removing, setRemoving] = useState<Member | null>(null);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", department: "", job_title: "", roles: ["standard_user"] });
  const [pwd, setPwd] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = () => qc.invalidateQueries({ queryKey: ["members"] });

  const run = async (fn: () => Promise<unknown>, ok: string, after?: () => void) => {
    setBusy(true);
    try {
      await fn();
      toast.success(ok);
      refresh();
      after?.();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const toggleRole = (code: string) =>
    setForm((f) => ({ ...f, roles: f.roles.includes(code) ? f.roles.filter((r) => r !== code) : [...f.roles, code] }));

  return (
    <Card>
      <div className="flex items-center justify-between border-b px-5 py-3">
        <span className="text-sm text-muted-foreground">{members.length} membre(s)</span>
        {can("user:create") && (
          <Button size="sm" onClick={() => { setForm({ email: "", full_name: "", password: "", department: "", job_title: "", roles: ["standard_user"] }); setInviteOpen(true); }}>
            <Plus /> Ajouter un utilisateur
          </Button>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
            <tr>
              <th className="px-5 py-2.5 text-left font-medium">Utilisateur</th>
              <th className="px-4 py-2.5 text-left font-medium">Rôles</th>
              <th className="hidden px-4 py-2.5 text-left font-medium md:table-cell">Service</th>
              <th className="px-4 py-2.5 text-left font-medium">Statut</th>
              <th className="hidden px-4 py-2.5 text-left font-medium lg:table-cell">Dernière connexion</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {members.map((m) => (
              <tr key={m.user.id}>
                <td className="px-5 py-3">
                  <div className="flex items-center gap-3">
                    <div className="flex size-8 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">{initials(m.user.full_name)}</div>
                    <div>
                      <div className="font-medium">{m.user.full_name} {m.user.id === me && <span className="text-xs text-muted-foreground">(vous)</span>}</div>
                      <div className="text-xs text-muted-foreground">{m.user.email}</div>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3"><div className="flex flex-wrap gap-1">{m.roles.map((r) => <Badge key={r.id} tone="blue">{r.name}</Badge>)}</div></td>
                <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">{m.department ?? "—"}</td>
                <td className="px-4 py-3">
                  <Badge tone={m.status === "active" ? "green" : m.status === "invited" ? "amber" : "neutral"}>
                    {m.status === "active" ? "Actif" : m.status === "invited" ? "Invité" : "Désactivé"}
                  </Badge>
                </td>
                <td className="hidden px-4 py-3 text-muted-foreground lg:table-cell">{formatDateTime(m.user.last_login_at)}</td>
                <td className="px-2 py-3">
                  {m.user.id !== me && (can("user:update") || can("user:delete")) && (
                    <DropdownMenu>
                      <DropdownTrigger asChild><button className="rounded p-1 hover:bg-muted" aria-label="Actions"><MoreHorizontal className="size-4" /></button></DropdownTrigger>
                      <DropdownContent>
                        {can("user:update") && (
                          <DropdownItem onSelect={() => { setEditing(m); setForm({ ...form, roles: m.roles.map((r) => r.code) }); }}>
                            <ShieldCheck /> Modifier les rôles
                          </DropdownItem>
                        )}
                        {can("user:administer") && (
                          <DropdownItem onSelect={() => { setPwd(""); setPwdFor(m); }}><KeyRound /> Définir le mot de passe</DropdownItem>
                        )}
                        {can("user:update") && (
                          m.status === "disabled" ? (
                            <DropdownItem onSelect={() => run(() => api(`/users/${m.user.id}`, { method: "PATCH", body: { status: "active" } }), "Compte réactivé")}><UserCheck /> Réactiver</DropdownItem>
                          ) : (
                            <DropdownItem onSelect={() => run(() => api(`/users/${m.user.id}`, { method: "PATCH", body: { status: "disabled" } }), "Compte désactivé")}><UserX /> Désactiver</DropdownItem>
                          )
                        )}
                        {can("user:delete") && (<><DropdownSeparator /><DropdownItem destructive onSelect={() => setRemoving(m)}><UserMinus /> Retirer de l'organisation</DropdownItem></>)}
                      </DropdownContent>
                    </DropdownMenu>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={inviteOpen} onOpenChange={setInviteOpen} title="Ajouter un utilisateur"
              description="Sans mot de passe, le compte est créé « invité » : il devra être activé par un administrateur (l'envoi d'invitations par e-mail arrive avec le service de notifications)."
              footer={<><Button variant="outline" onClick={() => setInviteOpen(false)}>Annuler</Button>
                <Button loading={busy} onClick={() => run(() => api("/users", { method: "POST", body: { email: form.email, full_name: form.full_name, password: form.password || null, department: form.department || null, job_title: form.job_title || null, role_codes: form.roles } }), "Utilisateur ajouté", () => setInviteOpen(false))}>Ajouter</Button></>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nom complet"><Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
          <Field label="E-mail"><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="Service"><Input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} /></Field>
          <Field label="Fonction"><Input value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="Mot de passe initial" hint="10 caractères min., majuscule, minuscule et chiffre"><Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} autoComplete="new-password" /></Field></div>
        </div>
        <RolePicker roles={roles} selected={form.roles} onToggle={toggleRole} />
      </Dialog>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)} title={`Rôles de ${editing?.user.full_name}`} size="sm"
              footer={<><Button variant="outline" onClick={() => setEditing(null)}>Annuler</Button>
                <Button loading={busy} onClick={() => run(() => api(`/users/${editing!.user.id}`, { method: "PATCH", body: { role_codes: form.roles } }), "Rôles mis à jour", () => setEditing(null))}>Enregistrer</Button></>}>
        <RolePicker roles={roles} selected={form.roles} onToggle={toggleRole} />
      </Dialog>

      <Dialog open={!!pwdFor} onOpenChange={(o) => !o && setPwdFor(null)} title="Définir le mot de passe" size="sm"
              footer={<><Button variant="outline" onClick={() => setPwdFor(null)}>Annuler</Button>
                <Button loading={busy} onClick={() => run(() => api(`/users/${pwdFor!.user.id}/password`, { method: "POST", body: { password: pwd } }), "Mot de passe défini", () => setPwdFor(null))}>Enregistrer</Button></>}>
        <Field label="Nouveau mot de passe"><Input type="password" value={pwd} onChange={(e) => setPwd(e.target.value)} autoComplete="new-password" /></Field>
      </Dialog>

      <ConfirmDialog open={!!removing} onOpenChange={(o) => !o && setRemoving(null)} destructive loading={busy}
                     title="Retirer l'utilisateur ?" confirmLabel="Retirer"
                     description={`${removing?.user.full_name} perdra immédiatement l'accès à l'organisation. Ses documents sont conservés.`}
                     onConfirm={() => run(() => api(`/users/${removing!.user.id}`, { method: "DELETE" }), "Utilisateur retiré", () => setRemoving(null))} />
    </Card>
  );
}

function RolePicker({ roles, selected, onToggle }: { roles: Role[]; selected: string[]; onToggle: (c: string) => void }) {
  return (
    <div className="mt-5">
      <div className="mb-2 text-sm font-medium">Rôles</div>
      <div className="grid gap-2 sm:grid-cols-2">
        {roles.map((r) => (
          <label key={r.id} className={cn("flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm", selected.includes(r.code) && "border-primary bg-accent/50")}>
            <input type="checkbox" className="mt-0.5 accent-[hsl(var(--primary))]" checked={selected.includes(r.code)} onChange={() => onToggle(r.code)} />
            <span>
              <span className="block font-medium">{r.name}</span>
              <span className="text-xs text-muted-foreground">{r.description ?? `${r.permissions.length} permissions`}</span>
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}

const ACTION_LABELS: Record<string, string> = {
  create: "Créer", read: "Lire", update: "Modifier", delete: "Supprimer", download: "Télécharger", share: "Partager",
  validate: "Valider", approve: "Approuver", administer: "Administrer",
};

function Roles() {
  const { data: roles = [] } = useRoles();
  const { data: perms = [] } = useQuery({ queryKey: ["permissions"], queryFn: () => api<{ code: string; resource: string; action: string }[]>("/permissions") });
  const can = useCan();
  const qc = useQueryClient();
  const [edit, setEdit] = useState<{ id?: string; code: string; name: string; description: string; permissions: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const byResource = useMemo(() => {
    const m = new Map<string, string[]>();
    perms.forEach((p) => m.set(p.resource, [...(m.get(p.resource) ?? []), p.action]));
    return m;
  }, [perms]);
  const actions = Object.keys(ACTION_LABELS);

  const save = async () => {
    if (!edit) return;
    setBusy(true);
    try {
      await api(edit.id ? `/roles/${edit.id}` : "/roles", { method: edit.id ? "PUT" : "POST", body: edit });
      toast.success("Rôle enregistré");
      qc.invalidateQueries({ queryKey: ["roles"] });
      setEdit(null);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="mb-4 flex justify-end">
        {can("role:create") && <Button size="sm" onClick={() => setEdit({ code: "", name: "", description: "", permissions: [] })}><Plus /> Rôle personnalisé</Button>}
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {roles.map((r) => (
          <Card key={r.id} className="p-5">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="font-semibold">{r.name}</h3>
                <p className="mt-0.5 text-xs text-muted-foreground">{r.description}</p>
              </div>
              {r.is_system && <Badge tone="outline">Système</Badge>}
            </div>
            <div className="mt-3 text-xs text-muted-foreground">{r.permissions.length} permissions</div>
            {can("role:update") && r.code !== "tenant_admin" && (
              <Button variant="outline" size="sm" className="mt-4"
                      onClick={() => setEdit({ id: r.id, code: r.code, name: r.name, description: r.description ?? "", permissions: [...r.permissions] })}>
                Modifier les permissions
              </Button>
            )}
          </Card>
        ))}
      </div>
      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)} title={edit?.id ? `Rôle : ${edit.name}` : "Nouveau rôle"} size="xl"
              footer={<><Button variant="outline" onClick={() => setEdit(null)}>Annuler</Button><Button loading={busy} onClick={save}>Enregistrer</Button></>}>
        {edit && (
          <>
            <div className="mb-5 grid gap-4 sm:grid-cols-3">
              <Field label="Nom"><Input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
              <Field label="Code" hint="minuscules et _"><Input value={edit.code} disabled={!!edit.id} onChange={(e) => setEdit({ ...edit, code: e.target.value })} className="font-mono text-xs" /></Field>
              <Field label="Description"><Input value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field>
            </div>
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-xs">
                <thead className="bg-muted/40"><tr><th className="px-3 py-2 text-left">Ressource</th>{actions.map((a) => <th key={a} className="px-2 py-2">{ACTION_LABELS[a]}</th>)}</tr></thead>
                <tbody className="divide-y">
                  {[...byResource.entries()].map(([res, acts]) => (
                    <tr key={res}>
                      <td className="px-3 py-2 font-medium">{res}</td>
                      {actions.map((a) => {
                        const code = `${res}:${a}`;
                        return (
                          <td key={a} className="px-2 py-2 text-center">
                            {acts.includes(a) && (
                              <Switch checked={edit.permissions.includes(code)} label={code}
                                      onChange={(v) => setEdit({ ...edit, permissions: v ? [...edit.permissions, code] : edit.permissions.filter((p) => p !== code) })} />
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Dialog>
    </>
  );
}
