import type { SplitProposal, SplitSegment } from "@/types/api";

/**
 * Editable split plan. A page either belongs to a segment or is excluded (blank separator).
 * `cuts` holds the pages that start a new document; an excluded page always ends the current one,
 * so every segment is a contiguous page range (what the API requires).
 */
export interface SplitPlan {
  pageCount: number;
  cuts: Set<number>;
  excluded: Set<number>;
  meta: Map<number, { title: string; typeId: string }>; // keyed by the segment's first page
}

export interface PlannedSegment {
  start: number;
  end: number;
  pages: number[];
  title: string;
  typeId: string;
  source?: SplitSegment;
}

export function planFromProposal(pageCount: number, proposal: SplitProposal | null): SplitPlan {
  const cuts = new Set<number>();
  const meta = new Map<number, { title: string; typeId: string }>();
  const excluded = new Set<number>(proposal?.separator_pages ?? []);
  for (const s of proposal?.segments ?? []) {
    cuts.add(s.start_page);
    meta.set(s.start_page, { title: s.title ?? "", typeId: s.document_type_id ?? "" });
    // pages inside no segment are excluded
  }
  if (proposal) {
    const covered = new Set<number>();
    for (const s of proposal.segments) for (let p = s.start_page; p <= s.end_page; p++) covered.add(p);
    for (let p = 1; p <= pageCount; p++) if (!covered.has(p)) excluded.add(p);
  }
  return { pageCount, cuts, excluded, meta };
}

export function segmentsOf(plan: SplitPlan, proposal?: SplitProposal | null): PlannedSegment[] {
  const out: PlannedSegment[] = [];
  let current: PlannedSegment | null = null;
  for (let p = 1; p <= plan.pageCount; p++) {
    if (plan.excluded.has(p)) {
      current = null;
      continue;
    }
    if (!current || plan.cuts.has(p)) {
      const m = plan.meta.get(p);
      current = {
        start: p, end: p, pages: [p], title: m?.title ?? "", typeId: m?.typeId ?? "",
        source: proposal?.segments.find((s) => s.start_page === p),
      };
      out.push(current);
    } else {
      current.end = p;
      current.pages.push(p);
    }
  }
  return out;
}

export const toggleCut = (plan: SplitPlan, page: number): SplitPlan => {
  const cuts = new Set(plan.cuts);
  if (cuts.has(page)) cuts.delete(page);
  else cuts.add(page);
  return { ...plan, cuts };
};

export const toggleExcluded = (plan: SplitPlan, page: number): SplitPlan => {
  const excluded = new Set(plan.excluded);
  if (excluded.has(page)) excluded.delete(page);
  else excluded.add(page);
  return { ...plan, excluded };
};

export const setMeta = (plan: SplitPlan, start: number, patch: Partial<{ title: string; typeId: string }>): SplitPlan => {
  const meta = new Map(plan.meta);
  meta.set(start, { title: "", typeId: "", ...meta.get(start), ...patch });
  return { ...plan, meta };
};

/** True when applying would actually cut the PDF (not one segment spanning every page). */
export const isRealSplit = (segs: PlannedSegment[], pageCount: number) =>
  segs.length > 1 || (segs.length === 1 && (segs[0].start !== 1 || segs[0].end !== pageCount));

export const toPayload = (segs: PlannedSegment[]) =>
  segs.map((s) => ({ start_page: s.start, end_page: s.end, title: s.title.trim() || null, document_type_id: s.typeId || null }));
