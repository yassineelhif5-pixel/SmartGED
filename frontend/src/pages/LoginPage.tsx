import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useLocation } from "react-router-dom";
import { useState } from "react";
import { FileSearch, ShieldCheck, Sparkles, Workflow } from "lucide-react";
import { api, ApiError } from "@/api/client";
import { useSessionStore } from "@/stores/session";
import type { Session } from "@/types/api";
import { Button, Field, Input } from "@/components/ui/primitives";

const schema = z.object({
  email: z.string().email("Adresse e-mail invalide"),
  password: z.string().min(1, "Mot de passe requis"),
  tenant_slug: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const setSession = useSessionStore((s) => s.setSession);
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [showOrg, setShowOrg] = useState(false);
  const { register, handleSubmit, formState } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    setError(null);
    try {
      const s = await api<Session>("/auth/login", {
        method: "POST",
        body: { ...values, tenant_slug: values.tenant_slug || null },
      });
      setSession(s);
      useSessionStore.getState().markReady();
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? (s.tenant ? "/" : "/platform"), { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connexion impossible");
    }
  };

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden overflow-hidden bg-sidebar p-12 text-sidebar-foreground lg:flex lg:flex-col">
        <div className="absolute inset-0 opacity-[0.15] [background-image:radial-gradient(circle_at_1px_1px,white_1px,transparent_0)] [background-size:24px_24px]" />
        <div className="absolute -right-32 -top-32 size-[28rem] rounded-full bg-blue-500/20 blur-3xl" />
        <div className="relative flex items-center gap-2.5">
          <img src="/favicon.svg" alt="" className="size-9" />
          <span className="text-lg font-semibold text-white">
            DocuMind <span className="text-blue-300">AI</span>
          </span>
        </div>
        <div className="relative mt-auto max-w-lg">
          <h1 className="text-4xl font-semibold leading-tight tracking-tight text-white">
            La GED intelligente qui lit, comprend et classe vos documents.
          </h1>
          <p className="mt-4 text-base text-sidebar-foreground/80">
            Centralisez, indexez et retrouvez chaque information — avec une sécurité de niveau entreprise.
          </p>
          <ul className="mt-10 space-y-4 text-sm">
            {[
              { icon: FileSearch, t: "OCR et recherche plein texte sur tout votre patrimoine documentaire" },
              { icon: Sparkles, t: "Types documentaires et métadonnées configurables, sans développement" },
              { icon: Workflow, t: "Validation humaine, versioning, check-in/check-out" },
              { icon: ShieldCheck, t: "Isolation multi-tenant, RBAC granulaire, audit infalsifiable" },
            ].map(({ icon: Icon, t }) => (
              <li key={t} className="flex items-start gap-3">
                <span className="rounded-md bg-white/10 p-1.5">
                  <Icon className="size-4 text-blue-200" />
                </span>
                <span className="pt-1">{t}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-semibold tracking-tight">Connexion</h2>
          <p className="mt-1 text-sm text-muted-foreground">Accédez à l'espace documentaire de votre organisation.</p>
          <form className="mt-8 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            <Field label="Adresse e-mail" htmlFor="email" error={formState.errors.email?.message}>
              <Input id="email" type="email" autoComplete="username" autoFocus {...register("email")} />
            </Field>
            <Field label="Mot de passe" htmlFor="password" error={formState.errors.password?.message}>
              <Input id="password" type="password" autoComplete="current-password" {...register("password")} />
            </Field>
            {showOrg ? (
              <Field label="Identifiant d'organisation" htmlFor="tenant" hint="Optionnel — ex. acme">
                <Input id="tenant" {...register("tenant_slug")} />
              </Field>
            ) : (
              <button type="button" className="text-xs text-primary hover:underline" onClick={() => setShowOrg(true)}>
                Se connecter à une organisation précise
              </button>
            )}
            {error && (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive" role="alert">
                {error}
              </div>
            )}
            <Button type="submit" className="w-full" loading={formState.isSubmitting}>
              Se connecter
            </Button>
          </form>
          <p className="mt-8 text-center text-xs text-muted-foreground">
            SSO Microsoft Entra ID / SAML : disponible en phase 7 (non configuré).
          </p>
        </div>
      </div>
    </div>
  );
}
