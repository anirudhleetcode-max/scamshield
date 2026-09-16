import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import History from "./History";
import { ToastProvider } from "../lib/toast";
import { jsonResponse } from "../test/fixtures";

const wrap = () => render(<MemoryRouter><ToastProvider><History /></ToastProvider></MemoryRouter>);

describe("History", () => {
  it("shows an error state when the API fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({ detail: "Database unavailable", status: 500 }, 500));
    wrap();
    expect(await screen.findByTestId("history-error")).toHaveTextContent("Database unavailable");
  });

  it("marks abstained and demo checks", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => jsonResponse({
      total: 1, next_cursor: null,
      items: [{ id: "1", text: "ok", sender: null, score: 20, verdict: "Safe", status: "insufficient_confidence", demo: true,
                category: "personal", category_label: "Personal", flags_hit: [], created_at: "2026-09-16T10:00:00Z" }],
    }));
    wrap();
    expect(await screen.findByText("Unsure")).toBeInTheDocument();
    expect(screen.getByText("demo")).toBeInTheDocument();
    expect(screen.getByTestId("history-total")).toHaveTextContent("1 check");
  });
});
