import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import Highlight, { segments } from "./Highlight";

describe("Highlight segments", () => {
  const text = "call 9876543210 now";

  it("returns plain text when there are no spans", () => {
    expect(segments(text, [])).toEqual([{ text, span: null }]);
  });

  it("lets a community report win over a model span on overlap", () => {
    const segs = segments(text, [
      { start: 0, end: 15, text: "", source: "model", weight: 0.9 },
      { start: 5, end: 15, text: "", source: "report", rule: "community_report" },
    ]);
    expect(segs.map((s) => [s.text, s.span?.source ?? null])).toEqual([
      ["call ", "model"],
      ["9876543210", "report"],
      [" now", null],
    ]);
  });

  it("ignores out-of-range spans and keeps the full text", () => {
    const { container } = render(<Highlight text={text} spans={[{ start: 10, end: 99, text: "", source: "rule" }]} />);
    expect(container.textContent).toBe(text);
    expect(container.querySelectorAll("mark")).toHaveLength(1);
  });
});
