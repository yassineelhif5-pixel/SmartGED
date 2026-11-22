import { useState } from "react";
import { useObjects } from "@/hooks/queries";
import type { MetadataField } from "@/types/api";
import { Input, Select, Textarea } from "@/components/ui/primitives";

/** Select a business object of a given type (used by `reference` fields). */
export function ObjectPicker({ typeCode, value, label, onChange, disabled }: {
  typeCode: string;
  value: string | null;
  label?: string | null;
  onChange: (id: string | null) => void;
  disabled?: boolean;
}) {
  const [q, setQ] = useState("");
  const { data, isFetching } = useObjects({ type_code: typeCode, q: q || undefined, status: "active", page_size: 50 }, !disabled);
  const items = data?.items ?? [];
  return (
    <div className="flex gap-2">
      {!disabled && <Input className="w-32 shrink-0" placeholder="Filtrer…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filtrer les objets" />}
      <Select value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">{isFetching ? "Chargement…" : "—"}</option>
        {value && !items.some((o) => o.id === value) && <option value={value}>{label ?? "Objet sélectionné"}</option>}
        {items.map((o) => <option key={o.id} value={o.id}>{o.code} — {o.name}</option>)}
      </Select>
    </div>
  );
}

/** One input per data type, shared by document metadata and object attributes. */
export function FieldEditor({ def, value, onChange, disabled, displayValue }: {
  def: Pick<MetadataField, "data_type" | "allowed_values" | "validation_rules">;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
  displayValue?: string | null;
}) {
  const v = value === null || value === undefined ? "" : value;
  switch (def.data_type) {
    case "long_text":
      return <Textarea value={String(v)} onChange={(e) => onChange(e.target.value)} disabled={disabled} rows={3} />;
    case "date":
      return <Input type="date" value={String(v)} onChange={(e) => onChange(e.target.value)} disabled={disabled} />;
    case "datetime":
      return <Input type="datetime-local" value={String(v).slice(0, 16)} onChange={(e) => onChange(e.target.value)} disabled={disabled} />;
    case "integer":
    case "decimal":
    case "currency":
      return <Input inputMode="decimal" value={String(v)} onChange={(e) => onChange(e.target.value)} disabled={disabled} className="tabular" />;
    case "boolean":
      return (
        <Select value={v === "" ? "" : String(v)} onChange={(e) => onChange(e.target.value === "" ? null : e.target.value === "true")} disabled={disabled}>
          <option value="">—</option><option value="true">Oui</option><option value="false">Non</option>
        </Select>
      );
    case "dropdown":
      return (
        <Select value={String(v)} onChange={(e) => onChange(e.target.value || null)} disabled={disabled}>
          <option value="">—</option>
          {def.allowed_values?.map((a) => <option key={a} value={a}>{a}</option>)}
        </Select>
      );
    case "multi_select":
      return (
        <Select multiple value={Array.isArray(v) ? (v as string[]) : []} disabled={disabled} className="h-auto"
                onChange={(e) => onChange(Array.from(e.target.selectedOptions).map((o) => o.value))}>
          {def.allowed_values?.map((a) => <option key={a} value={a}>{a}</option>)}
        </Select>
      );
    case "reference": {
      const code = def.validation_rules?.object_type_code as string | undefined;
      if (code) return <ObjectPicker typeCode={code} value={v ? String(v) : null} label={displayValue} onChange={onChange} disabled={disabled} />;
      return <Input value={String(v)} onChange={(e) => onChange(e.target.value)} disabled={disabled} />;
    }
    case "calculated":
      return <Input value={String(v)} disabled />;
    default:
      return <Input value={String(v)} onChange={(e) => onChange(e.target.value)} disabled={disabled} />;
  }
}
