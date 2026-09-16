import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ConfirmButton from "./ConfirmButton";

describe("ConfirmButton", () => {
  it("only runs the action after confirmation", async () => {
    const onConfirm = vi.fn();
    render(<ConfirmButton title="Delete this check?" body="Gone for good" onConfirm={onConfirm} ariaLabel="Delete">x</ConfirmButton>);
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByText("Delete this check?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onConfirm).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByTestId("confirm-delete"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
