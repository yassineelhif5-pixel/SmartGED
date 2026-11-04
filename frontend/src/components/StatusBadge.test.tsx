import { render, screen } from "@testing-library/react";
import { DocumentStatusBadge, StepBadge } from "./StatusBadge";

describe("status badges", () => {
  it("never presents a non-configured step as done", () => {
    render(<StepBadge status="not_configured" />);
    expect(screen.getByText("Non configuré")).toBeInTheDocument();
  });
  it("labels documents awaiting validation", () => {
    render(<DocumentStatusBadge status="pending_validation" />);
    expect(screen.getByText("À valider")).toBeInTheDocument();
  });
});
