import { useEffect, useState } from "react";
import { Boxes, CheckCircle2, Circle, EyeOff, ShieldCheck, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/api/client";
import { useInvalidateDocs } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { DocumentDetail, DocumentType } from "@/types/api";
import { cn } from "@/utils/format";
import { Button } from "@/components/ui/primitives";
import { FieldEditor } from "@/features/objects/FieldEditor";


export function MetadataPanel({ doc, type }: { doc: DocumentDetail; type?: DocumentType }) {
  const can = useCan();
  const invalidate = useInvalidateDocs();
  const editable = can("metadata:update") && !doc.deleted_at;
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(Object.fromEntries(doc.metadata.map((m) => [m.technical_name, m.value])));
    setErrors({});
  }, [doc.metadata]);

  if (!doc.document_type)
    return (
      <div className="p-6 text-center text-sm text-muted-foreground">
        Attribuez un type documentaire (bouton « Modifier ») pour saisir ses métadonnées.
      </div>
    );

  const changed = doc.metadata.filter((m) => JSON.stringify(draft[m.technical_name] ?? null) !== JSON.stringify(m.value ?? null));

  const submit = async (validate: string[]) => {
    setSaving(true);
    setErrors({});
    try {
      const values = Object.fromEntries(changed.map((m) => [m.technical_name, draft[m.technical_name] ?? null]));
      await api(`/documents/${doc.id}/metadata`, { method: "PUT", body: { values, validate_fields: validate } });
      toast.success(validate.length ? "Métadonnées validées" : "Métadonnées enregistrées");
      invalidate();
    } catch (e) {
      if (e instanceof ApiError && Array.isArray(e.details)) {
        setErrors(Object.fromEntries((e.details as { field: string; message: string }[]).map((d) => [d.field, d.message])));
      } else if (e instanceof ApiError && e.details && typeof e.details === "object" && "field" in (e.details as object)) {
        const d = e.details as { field: string };
        setErrors({ [d.field]: e.message });
      }
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const toValidate = doc.metadata
    .filter((m) => m.validation_status !== "completed" || changed.some((c) => c.technical_name === m.technical_name))
    .filter((m) => m.required || (draft[m.technical_name] ?? null) !== null)
    .map((m) => m.technical_name);

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto p-5">
        {doc.metadata.map((m) => {
          const def = type?.fields.find((f) => f.technical_name === m.technical_name);
          const masked = m.sensitive && !revealed.has(m.technical_name);
          return (
            <div key={m.technical_name}>
              <div className="mb-1.5 flex items-center gap-1.5 text-xs">
                <span className="font-medium">{m.display_name}</span>
                {m.required && <span className="text-destructive">*</span>}
                {m.source === "object" && (
                  <span className="inline-flex items-center gap-0.5 text-teal-600 dark:text-teal-400" title={m.source_text ?? undefined}>
                    <Boxes className="size-3" /> Référentiel
                  </span>
                )}
                {m.source === "ai" && (
                  <span className="inline-flex items-center gap-0.5 text-primary" title={m.source_text ?? undefined}>
                    <Sparkles className="size-3" /> IA {m.confidence !== null && `${Math.round(m.confidence * 100)} %`}
                  </span>
                )}
                <span className="ml-auto inline-flex items-center gap-1 text-muted-foreground">
                  {m.validation_status === "completed" ? (
                    <><CheckCircle2 className="size-3 text-success" /> Validé</>
                  ) : (
                    <><Circle className="size-3" /> Non validé</>
                  )}
                </span>
              </div>
              {masked ? (
                <button className="flex h-9 w-full items-center gap-2 rounded-md border border-dashed px-3 text-xs text-muted-foreground"
                        onClick={() => setRevealed((s) => new Set(s).add(m.technical_name))}>
                  <EyeOff className="size-3.5" /> Champ sensible — cliquer pour afficher
                </button>
              ) : (
                <FieldEditor def={{ data_type: m.data_type, allowed_values: def?.allowed_values, validation_rules: def?.validation_rules ?? {} }}
                             displayValue={m.display_value} value={draft[m.technical_name]} disabled={!editable}
                            onChange={(v) => setDraft((d) => ({ ...d, [m.technical_name]: v }))} />
              )}
              {errors[m.technical_name] && <p className="mt-1 text-xs text-destructive">{errors[m.technical_name]}</p>}
            </div>
          );
        })}
      </div>
      {editable && (
        <div className={cn("flex flex-wrap justify-end gap-2 border-t bg-muted/30 px-5 py-3")}>
          <Button variant="outline" size="sm" disabled={!changed.length} loading={saving} onClick={() => submit([])}>
            Enregistrer
          </Button>
          {can("metadata:validate") && (
            <Button size="sm" loading={saving} disabled={!toValidate.length} onClick={() => submit(toValidate)}>
              <ShieldCheck /> Enregistrer et valider
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
