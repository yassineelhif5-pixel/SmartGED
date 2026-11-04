import { displayValue, formatBytes, initials } from "./format";

describe("format utils", () => {
  it("formats byte sizes", () => {
    expect(formatBytes(512)).toBe("512 o");
    expect(formatBytes(1536)).toBe("1.5 Ko");
    expect(formatBytes(null)).toBe("—");
  });
  it("builds initials", () => {
    expect(initials("Marie Durand")).toBe("MD");
  });
  it("renders metadata values per data type", () => {
    expect(displayValue(true, "boolean")).toBe("Oui");
    expect(displayValue(null, "text")).toBe("—");
    expect(displayValue(["a", "b"], "multi_select")).toBe("a, b");
  });
});
