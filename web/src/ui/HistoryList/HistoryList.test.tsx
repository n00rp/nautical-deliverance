import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { HistoryList } from "./HistoryList";

const entries = [
  { id: "1", actor: "Ann", at: "2026-11-01T08:00:00Z", action: "create" as const, changes: [] },
  {
    id: "3",
    actor: "Cid",
    at: "2026-11-03T10:30:00Z",
    action: "update" as const,
    changes: [
      { field: "Port", before: "Gibraltar", after: "Rotterdam" },
      { field: "Note", before: null, after: "new" },
      { field: "Flag", before: "old", after: null },
    ],
  },
  { id: "2", actor: "Bob", at: "2026-11-02T09:00:00Z", action: "deactivate" as const, changes: [] },
];

describe("HistoryList", () => {
  afterEach(cleanup);

  it("[B1-R13] history list: newest first regardless of input order", () => {
    render(<HistoryList entries={entries} />);
    const items = screen.getAllByRole("listitem").filter((li) => li.hasAttribute("data-entry"));
    expect(items.map((li) => li.getAttribute("data-entry"))).toEqual(["3", "2", "1"]);
  });

  it("[B1-R13] history list: before → after per field, dash for null, UTC timestamp", () => {
    render(<HistoryList entries={entries} />);
    expect(screen.getByText("Gibraltar → Rotterdam")).toBeTruthy();
    expect(screen.getByText("— → new")).toBeTruthy();
    expect(screen.getByText("old → —")).toBeTruthy();
    const first = screen.getAllByRole("listitem")[0] as HTMLElement;
    expect(within(first).getByText("03 Nov 10:30 UTC")).toBeTruthy();
    expect(within(first).getByText(/Cid/)).toBeTruthy();
  });

  it("[B1-R13] history list: empty list shows a note", () => {
    render(<HistoryList entries={[]} />);
    expect(screen.getByText("No history yet")).toBeTruthy();
  });

  it("[B1-R13] history list: an unparseable timestamp counts as oldest", () => {
    const bad = {
      id: "bad",
      actor: "Zed",
      at: "not a date",
      action: "create" as const,
      changes: [],
    };
    render(<HistoryList entries={[bad, ...entries]} />);
    const ids = screen.getAllByRole("listitem").filter((li) => li.hasAttribute("data-entry"));
    expect(ids.map((li) => li.getAttribute("data-entry"))).toEqual(["3", "2", "1", "bad"]);
  });
});
