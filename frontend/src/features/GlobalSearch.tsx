import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bot, FileText, Search } from "lucide-react";
import { api } from "@/api/client";
import { useCan } from "@/stores/session";
import type { SearchResponse } from "@/types/api";
import { cn } from "@/utils/format";
import { Spinner } from "@/components/ui/primitives";

/** Header search: hybrid (keyword + semantic) results as you type; Enter → full results list. */
export function GlobalSearch() {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const can = useCan();
  const ref = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    const onClick = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, []);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);

  const { data, isFetching } = useQuery({
    queryKey: ["hybrid-search", debounced],
    queryFn: () => api<SearchResponse>("/search", { query: { q: debounced, limit: 6 } }),
    enabled: debounced.length >= 2,
    staleTime: 30_000,
  });
  const close = () => { setOpen(false); ref.current?.blur(); };

  return (
    <div ref={box} className="relative w-full max-w-md">
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) { close(); navigate(`/documents?q=${encodeURIComponent(q.trim())}`); } }}>
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <input
          ref={ref} value={q} onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onKeyDown={(e) => e.key === "Escape" && close()}
          placeholder="Rechercher dans tous les documents…" aria-label="Recherche globale"
          className="h-9 w-full rounded-md border border-input bg-muted/40 pl-9 pr-14 text-sm placeholder:text-muted-foreground focus:bg-card focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border bg-card px-1.5 text-[10px] text-muted-foreground sm:block">Ctrl K</kbd>
      </form>
      {open && debounced.length >= 2 && (
        <div className="absolute left-0 right-0 top-11 z-50 overflow-hidden rounded-lg border bg-card shadow-lg">
          {!data && isFetching && <div className="flex justify-center p-4"><Spinner className="size-4" /></div>}
          {data && data.hits.length === 0 && <p className="p-4 text-center text-sm text-muted-foreground">Aucun résultat</p>}
          {data?.hits.map((h) => (
            <Link key={h.document.id} to={`/documents/${h.document.id}`} onClick={close}
                  className="flex gap-3 border-b px-3 py-2.5 last:border-0 hover:bg-muted">
              <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium">{h.document.title}</span>
                  {h.match !== "keyword" && <span className={cn("shrink-0 rounded px-1 text-[10px]", "bg-primary/10 text-primary")}>{h.match === "both" ? "mots + sens" : "sens"}</span>}
                </div>
                {h.passage && <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{h.page_from ? `p. ${h.page_from} · ` : ""}{h.passage}</p>}
              </div>
            </Link>
          ))}
          <div className="flex items-center justify-between gap-2 bg-muted/40 px-3 py-2 text-xs">
            <button className="text-primary hover:underline" onClick={() => { close(); navigate(`/documents?q=${encodeURIComponent(debounced)}`); }}>
              Tous les résultats
            </button>
            {can("ai_assistant:read") && (
              <button className="flex items-center gap-1 text-primary hover:underline" onClick={() => { close(); navigate(`/lina?q=${encodeURIComponent(debounced)}`); }}>
                <Bot className="size-3.5" /> Demander à Lina
              </button>
            )}
            {data && <span className="text-muted-foreground">{data.semantic === "completed" ? "Recherche hybride" : "Mots-clés"}</span>}
          </div>
        </div>
      )}
    </div>
  );
}
