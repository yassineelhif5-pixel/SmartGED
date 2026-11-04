import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Monitor, Moon, Sun } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useSessionStore, useUiStore } from "@/stores/session";
import { cn } from "@/utils/format";
import { Badge, Button, Card, CardHeader, Field, Input, PageHeader } from "@/components/ui/primitives";

export default function SettingsPage() {
  const session = useSessionStore((s) => s.session)!;
  const { theme, setTheme } = useUiStore();
  const [pwd, setPwd] = useState({ current_password: "", new_password: "" });
  const [busy, setBusy] = useState(false);
  const health = useQuery({ queryKey: ["health"], queryFn: () => api<{ capabilities: Record<string, string>; redis: string; environment: string }>("/health/ready") });

  const changePassword = async () => {
    setBusy(true);
    try {
      await api("/auth/change-password", { method: "POST", body: pwd });
      toast.success("Mot de passe modifié");
      setPwd({ current_password: "", new_password: "" });
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Paramètres" />
      <div className="grid max-w-4xl gap-6">
        <Card>
          <CardHeader title="Apparence" />
          <div className="flex gap-3 p-5">
            {([["light", Sun, "Clair"], ["dark", Moon, "Sombre"], ["system", Monitor, "Système"]] as const).map(([v, Icon, label]) => (
              <button key={v} onClick={() => setTheme(v)}
                      className={cn("flex w-28 flex-col items-center gap-2 rounded-lg border p-4 text-sm", theme === v ? "border-primary bg-accent" : "hover:bg-muted")}>
                <Icon className="size-5" /> {label}
              </button>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Mon compte" description={`${session.user.full_name} · ${session.user.email}`} />
          <div className="grid gap-4 p-5 sm:grid-cols-2">
            <Field label="Mot de passe actuel"><Input type="password" autoComplete="current-password" value={pwd.current_password} onChange={(e) => setPwd({ ...pwd, current_password: e.target.value })} /></Field>
            <Field label="Nouveau mot de passe" hint="10 caractères min., majuscule, minuscule et chiffre"><Input type="password" autoComplete="new-password" value={pwd.new_password} onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })} /></Field>
            <div><Button onClick={changePassword} loading={busy} disabled={!pwd.current_password || !pwd.new_password}>Changer le mot de passe</Button></div>
          </div>
        </Card>
        <Card>
          <CardHeader title="État des services" description="Capacités réellement configurées sur cet environnement" />
          <dl className="grid gap-3 p-5 text-sm sm:grid-cols-2">
            {health.data && Object.entries({ ...health.data.capabilities, redis: health.data.redis, environnement: health.data.environment }).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between rounded-md border px-3 py-2">
                <dt className="capitalize text-muted-foreground">{k}</dt>
                <dd><Badge tone={v === "not_configured" || v === "unavailable" ? "amber" : "green"}>{v === "not_configured" ? "non configuré" : v}</Badge></dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>
    </>
  );
}
