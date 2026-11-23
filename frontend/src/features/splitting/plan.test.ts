import { describe, expect, it } from "vitest";
import type { SplitProposal } from "@/types/api";
import { isRealSplit, planFromProposal, segmentsOf, toggleCut, toggleExcluded, toPayload } from "./plan";

const proposal = {
  id: "p", status: "proposed", method: "heuristic", version_number: 1, page_count: 5, confidence: 0.8,
  separator_pages: [3], details: {}, decided_at: null, child_document_ids: [], created_at: "",
  segments: [
    { start_page: 1, end_page: 2, title: "Facture A", document_type_id: "t1" },
    { start_page: 4, end_page: 4, title: null },
    { start_page: 5, end_page: 5, title: "Facture B" },
  ],
} as SplitProposal;

describe("split plan", () => {
  it("rebuilds the proposal's segments and separators", () => {
    const plan = planFromProposal(5, proposal);
    const segs = segmentsOf(plan, proposal);
    expect(segs.map((s) => [s.start, s.end])).toEqual([[1, 2], [4, 4], [5, 5]]);
    expect(segs[0].title).toBe("Facture A");
    expect(toPayload(segs)[0]).toEqual({ start_page: 1, end_page: 2, title: "Facture A", document_type_id: "t1" });
    expect(toPayload(segs)[1].title).toBeNull();
  });

  it("joins and cuts documents, and excluding a page ends the current document", () => {
    let plan = planFromProposal(5, proposal);
    plan = toggleCut(plan, 5); // merge 4 and 5
    expect(segmentsOf(plan).map((s) => [s.start, s.end])).toEqual([[1, 2], [4, 5]]);
    plan = toggleExcluded(plan, 3); // include the blank page back: 1-5 minus cuts at 4 → [1-3], [4-5]
    expect(segmentsOf(plan).map((s) => [s.start, s.end])).toEqual([[1, 3], [4, 5]]);
    plan = toggleExcluded(plan, 2);
    expect(segmentsOf(plan).map((s) => [s.start, s.end])).toEqual([[1, 1], [3, 3], [4, 5]]);
  });

  it("detects when nothing would be cut", () => {
    const plan = planFromProposal(3, null);
    expect(segmentsOf(plan).map((s) => [s.start, s.end])).toEqual([[1, 3]]);
    expect(isRealSplit(segmentsOf(plan), 3)).toBe(false);
    expect(isRealSplit(segmentsOf(toggleCut(plan, 2)), 3)).toBe(true);
  });
});
