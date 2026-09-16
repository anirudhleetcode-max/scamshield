import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import VerdictPanel from "./VerdictPanel";
import { analysis } from "../test/fixtures";

const renderPanel = (a = analysis()) => render(<MemoryRouter><VerdictPanel a={a} /></MemoryRouter>);

describe("VerdictPanel", () => {
  it("shows a decided verdict with score, calibrated probability and confidence", () => {
    renderPanel();
    expect(screen.getByTestId("verdict")).toHaveTextContent("Scam");
    expect(screen.getByTestId("score")).toHaveTextContent("88");
    expect(screen.getByTestId("confidence")).toHaveTextContent("high");
    expect(screen.getByText(/91\.0%/)).toBeInTheDocument();
    expect(screen.queryByTestId("abstain")).not.toBeInTheDocument();
  });

  it("places meter ticks at the model's operating points, not fixed numbers", () => {
    renderPanel();
    const meter = screen.getByRole("meter");
    expect(within(meter).getByText("60")).toBeInTheDocument();
    expect(within(meter).getByText("71")).toBeInTheDocument();
    expect(within(meter).queryByText("35")).not.toBeInTheDocument();
  });

  it("renders the insufficient-confidence state with its reasons", () => {
    renderPanel(analysis({
      status: "insufficient_confidence",
      verdict: "Safe",
      score: 20,
      confidence_level: "low",
      abstain_reasons: [{ id: "too_short", text: "The message is too short to judge from its wording." }],
    }));
    expect(screen.getByTestId("verdict")).toHaveTextContent("Insufficient confidence");
    expect(screen.getByTestId("leaning")).toHaveTextContent("Safe");
    const box = screen.getByTestId("abstain");
    expect(within(box).getByText(/too short/)).toBeInTheDocument();
    expect(screen.getByTestId("confidence")).toHaveTextContent("low");
  });

  it("explains a medium confidence as an override", () => {
    renderPanel(analysis({ confidence_level: "medium" }));
    expect(screen.getByTestId("confidence")).toHaveTextContent(/overrode the model/);
  });

  it("lists red flags that fired before the ones that did not", () => {
    renderPanel();
    const items = screen.getByRole("list", { name: /red flag checklist/i }).querySelectorAll("li");
    expect(items[0]).toHaveAttribute("data-flag", "urgency");
    expect(items[0]).toHaveAttribute("data-hit", "true");
  });
});
