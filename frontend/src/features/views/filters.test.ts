import { filtersFromParams, paramsFromFilters, sameFilters } from "./filters";

describe("view filters <-> URL", () => {
  it("round-trips every criterion", () => {
    const f = {
      q: "atlas", folder_id: "f1", recursive: true, document_type_id: "t1", status: "published" as const, tag: "finance",
      mine: true, object_id: "o1", created_from: "2026-01-01", created_to: "2026-12-31",
      meta: { supplier_name: "Atlas" }, sort: "title", order: "asc" as const,
    };
    expect(filtersFromParams(paramsFromFilters(f))).toEqual(f);
  });
  it("ignores pagination and view id when comparing", () => {
    const p = paramsFromFilters({ status: "published" }, "v1");
    p.set("page", "3");
    expect(sameFilters(filtersFromParams(p), { status: "published", sort: "created_at", order: "desc" })).toBe(true);
  });
});
