import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Bot, FileText, MessageSquarePlus, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useDocument, useFolders } from "@/hooks/queries";
import { useCan } from "@/stores/session";
import type { LinaCitation, LinaConversation, LinaMessage, LinaStatus } from "@/types/api";
import { cn, timeAgo } from "@/utils/format";
import { Badge, Button, Card, Select, Spinner } from "@/components/ui/primitives";

const SUGGESTIONS = [
  "Quelles factures du fournisseur Atlas ai-je reçues ?",
  "Quel est le préavis de résiliation du contrat de nettoyage ?",
  "Résume les documents arrivés cette semaine.",
];

export default function LinaPage() {
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const can = useCan();
  const scopedDoc = params.get("document");
  const { data: status } = useQuery({ queryKey: ["lina-status"], queryFn: () => api<LinaStatus>("/lina/status") });
  const { data: conversations = [] } = useQuery({
    queryKey: ["lina-conversations"], queryFn: () => api<LinaConversation[]>("/lina/conversations"),
  });
  const { data: folders = [] } = useFolders();
  const { data: doc } = useDocument(scopedDoc ?? "");
  const [activeId, setActiveId] = useState<string | null>(params.get("c"));
  const [messages, setMessages] = useState<LinaMessage[]>([]);
  const [folderId, setFolderId] = useState("");
  const [question, setQuestion] = useState(params.get("q") ?? "");
  const [sending, setSending] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const active = conversations.find((c) => c.id === activeId);

  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    api<LinaConversation>(`/lina/conversations/${activeId}`).then((c) => setMessages(c.messages ?? [])).catch(() => setActiveId(null));
  }, [activeId]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const scopeLabel = useMemo(() => {
    const s = active?.scope;
    if (s?.document_ids?.length) return `${s.document_ids.length} document(s) sélectionné(s)`;
    if (s?.folder_id) return `Dossier « ${folders.find((f) => f.id === s.folder_id)?.name ?? "…"} »`;
    if (active) return "Tous vos documents";
    if (scopedDoc) return `Document « ${doc?.title ?? "…"} »`;
    if (folderId) return `Dossier « ${folders.find((f) => f.id === folderId)?.name ?? ""} »`;
    return "Tous vos documents";
  }, [active, scopedDoc, doc, folderId, folders]);

  const send = async (text = question) => {
    const q = text.trim();
    if (!q || sending) return;
    setSending(true);
    setQuestion("");
    const optimistic: LinaMessage = { id: `tmp-${Date.now()}`, role: "user", content: q, citations: [], meta: {}, created_at: new Date().toISOString() };
    setMessages((m) => [...m, optimistic]);
    try {
      const scope = activeId ? undefined : scopedDoc ? { document_ids: [scopedDoc] } : folderId ? { folder_id: folderId } : undefined;
      const r = await api<{ conversation: LinaConversation; message: LinaMessage }>("/lina/ask", {
        method: "POST", body: { question: q, conversation_id: activeId, scope },
      });
      setMessages((m) => [...m, r.message]);
      if (!activeId) {
        setActiveId(r.conversation.id);
        setParams({ c: r.conversation.id }, { replace: true });
      }
      qc.invalidateQueries({ queryKey: ["lina-conversations"] });
    } catch (e) {
      setMessages((m) => m.filter((x) => x.id !== optimistic.id));
      setQuestion(q);
      toast.error((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  const newConversation = () => {
    setActiveId(null);
    setParams({}, { replace: true });
  };
  const remove = async (id: string) => {
    await api(`/lina/conversations/${id}`, { method: "DELETE" });
    if (id === activeId) newConversation();
    qc.invalidateQueries({ queryKey: ["lina-conversations"] });
  };

  const notConfigured = status && !status.chat_configured;

  return (
    <div className="-my-2 grid h-[calc(100vh-7rem)] gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      <Card className="hidden min-h-0 flex-col overflow-hidden lg:flex">
        <div className="border-b p-3">
          <Button className="w-full" variant="outline" size="sm" onClick={newConversation}><MessageSquarePlus /> Nouvelle conversation</Button>
        </div>
        <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2">
          {conversations.length === 0 && <p className="px-2 py-6 text-center text-xs text-muted-foreground">Vos conversations apparaîtront ici.</p>}
          {conversations.map((c) => (
            <div key={c.id} className={cn("group flex items-center gap-1 rounded-md px-2 py-1.5 text-sm hover:bg-muted", c.id === activeId && "bg-accent text-accent-foreground")}>
              <button className="min-w-0 flex-1 text-left" onClick={() => { setActiveId(c.id); setParams({ c: c.id }, { replace: true }); }}>
                <span className="block truncate">{c.title}</span>
                <span className="block text-[11px] text-muted-foreground">{timeAgo(c.updated_at)}</span>
              </button>
              <button aria-label="Supprimer la conversation" className="opacity-0 transition group-hover:opacity-100" onClick={() => remove(c.id)}>
                <Trash2 className="size-3.5 text-muted-foreground hover:text-destructive" />
              </button>
            </div>
          ))}
        </div>
      </Card>

      <Card className="flex min-h-0 flex-col overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b px-5 py-3">
          <div className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-primary"><Bot className="size-4" /></div>
          <div className="min-w-0 flex-1">
            <h1 className="text-sm font-semibold">Lina</h1>
            <p className="truncate text-xs text-muted-foreground">
              Répond uniquement à partir de vos documents, avec les sources · Périmètre : {scopeLabel}
            </p>
          </div>
          {!activeId && !scopedDoc && (
            <Select className="h-8 w-52 text-xs" value={folderId} onChange={(e) => setFolderId(e.target.value)} aria-label="Périmètre">
              <option value="">Tous vos documents</option>
              {folders.map((f) => <option key={f.id} value={f.id}>Dossier : {f.name}</option>)}
            </Select>
          )}
          {status && (
            <Badge tone={status.semantic_configured ? "green" : "neutral"} title={status.semantic_configured ? `Embeddings ${status.embedding_model}` : "Recherche par mots-clés uniquement"}>
              {status.semantic_configured ? "Recherche hybride" : "Mots-clés"}
            </Badge>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
          {notConfigured ? (
            <div className="mx-auto max-w-md py-16 text-center">
              <Sparkles className="mx-auto size-8 text-muted-foreground" />
              <h2 className="mt-3 text-sm font-semibold">Lina n'est pas encore configurée</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Lina a besoin d'un fournisseur IA (clé API ou modèle local) pour rédiger ses réponses.
              </p>
              {can("prompt:read") && <Button asChild className="mt-4" size="sm"><Link to="/admin/ai">Configurer l'IA</Link></Button>}
            </div>
          ) : messages.length === 0 ? (
            <div className="mx-auto max-w-xl py-12 text-center">
              <h2 className="text-lg font-semibold tracking-tight">Que voulez-vous savoir ?</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {status ? `${status.indexed_documents} documents indexés. ` : ""}Chaque réponse cite les passages utilisés — cliquez pour ouvrir le document.
              </p>
              <div className="mt-6 grid gap-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)} className="rounded-lg border px-4 py-2.5 text-left text-sm transition hover:border-primary/50 hover:bg-accent/50">{s}</button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-6">
              {messages.map((m) => <MessageView key={m.id} m={m} />)}
              {sending && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner className="size-4" /> Lina consulte vos documents…</div>}
              <div ref={bottom} />
            </div>
          )}
        </div>

        <form className="border-t p-4" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border bg-card px-3 py-2 focus-within:ring-2 focus-within:ring-ring">
            <textarea
              value={question} rows={1} maxLength={2000} disabled={notConfigured}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder="Posez une question sur vos documents…" aria-label="Question pour Lina"
              className="max-h-40 min-h-[2.25rem] flex-1 resize-none bg-transparent py-1.5 text-sm outline-none placeholder:text-muted-foreground"
            />
            <Button type="submit" size="icon" className="size-8 shrink-0" disabled={!question.trim() || sending || notConfigured} aria-label="Envoyer"><ArrowUp /></Button>
          </div>
          <p className="mx-auto mt-1.5 max-w-3xl text-[11px] text-muted-foreground">Lina peut se tromper : vérifiez les sources citées avant toute décision.</p>
        </form>
      </Card>
    </div>
  );
}

function MessageView({ m }: { m: LinaMessage }) {
  if (m.role === "user")
    return <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">{m.content}</div>;
  const byRef = new Map(m.citations.map((c) => [c.ref, c]));
  const parts = m.content.split(/(\[S\d{1,2}\])/g);
  return (
    <div className="space-y-3">
      <div className="text-sm leading-relaxed">
        {parts.map((part, i) => {
          const ref = part.match(/^\[(S\d{1,2})\]$/)?.[1];
          const c = ref ? byRef.get(ref) : undefined;
          if (!c) return <span key={i} className="whitespace-pre-wrap">{ref ? "" : part}</span>;
          return (
            <Link key={i} to={`/documents/${c.document_id}`} title={`${c.title} — ${pagesLabel(c)}`}
                  className="mx-0.5 inline-flex -translate-y-0.5 items-center rounded bg-primary/10 px-1 text-[10px] font-semibold text-primary hover:bg-primary/20">
              {c.ref.slice(1)}
            </Link>
          );
        })}
      </div>
      {m.citations.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {m.citations.map((c) => <SourceCard key={c.ref} c={c} />)}
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">
        {m.meta.sources_found ?? 0} passage(s) consulté(s)
        {m.meta.semantic === "completed" ? " · recherche hybride" : m.meta.semantic === "not_configured" ? " · mots-clés" : ""}
        {m.meta.insufficient ? " · informations insuffisantes" : ""}
        {m.meta.model ? ` · ${m.meta.model}` : ""}
      </p>
    </div>
  );
}

const pagesLabel = (c: LinaCitation) =>
  c.page_from == null ? "" : c.page_from === c.page_to ? `p. ${c.page_from}` : `p. ${c.page_from}–${c.page_to}`;

function SourceCard({ c }: { c: LinaCitation }) {
  return (
    <Link to={`/documents/${c.document_id}`} className="group rounded-lg border p-3 text-xs transition hover:border-primary/50 hover:bg-accent/40">
      <div className="flex items-center gap-1.5 font-medium">
        <span className="rounded bg-primary/10 px-1 text-[10px] font-semibold text-primary">{c.ref.slice(1)}</span>
        <FileText className="size-3.5 text-muted-foreground" />
        <span className="truncate group-hover:text-primary">{c.title}</span>
        <span className="ml-auto shrink-0 text-muted-foreground">{pagesLabel(c)}</span>
      </div>
      <p className="mt-1.5 line-clamp-3 text-muted-foreground">{c.excerpt}</p>
    </Link>
  );
}

