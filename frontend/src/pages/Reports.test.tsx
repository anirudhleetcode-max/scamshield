import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Reports from "./Reports";
import { ToastProvider } from "../lib/toast";
import { jsonResponse } from "../test/fixtures";

function setup(post: (body: unknown) => Promise<Response>) {
  vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (init?.method === "POST") return post(JSON.parse(String(init.body)));
    if (url.startsWith("/api/reports/top")) return jsonResponse({ items: [] });
    return jsonResponse({ items: [], next_cursor: null });
  });
  render(<MemoryRouter><ToastProvider><Reports /></ToastProvider></MemoryRouter>);
}

describe("Reports form", () => {
  beforeEach(() => localStorage.clear());

  it("keeps submit disabled until a value is entered and shows empty states", async () => {
    setup(() => jsonResponse({}));
    expect(screen.getByTestId("report-submit")).toBeDisabled();
    expect(await screen.findByText("No reports yet")).toBeInTheDocument();
    await userEvent.type(screen.getByTestId("report-value"), "98");
    expect(screen.getByTestId("report-submit")).toBeDisabled();
    await userEvent.type(screen.getByTestId("report-value"), "76543210");
    expect(screen.getByTestId("report-submit")).toBeEnabled();
  });

  it("switches the identifier type", async () => {
    setup(() => jsonResponse({}));
    await userEvent.click(screen.getByTestId("kind-upi"));
    expect(screen.getByTestId("kind-upi")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("report-value")).toHaveAttribute("placeholder", "name@ybl");
  });

  it("sends the chosen kind and shows the server's duplicate error", async () => {
    const post = vi.fn(() => jsonResponse({ detail: "You have already reported this", status: 409 }, 409));
    setup(post);
    await userEvent.type(screen.getByTestId("report-value"), "9876543210");
    await userEvent.click(screen.getByTestId("report-submit"));
    await waitFor(() => expect(screen.getByTestId("report-msg")).toHaveTextContent("already reported"));
    expect(post).toHaveBeenCalledWith(expect.objectContaining({ kind: "phone", value: "9876543210", category: "kyc_bank" }));
  });
});
