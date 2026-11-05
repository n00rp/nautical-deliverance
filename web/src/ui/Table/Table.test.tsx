import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Table } from "./Table";

type Row = { id: string; name: string; qty: number };
const rows: Row[] = [
  { id: "a", name: "Bravo", qty: 20 },
  { id: "b", name: "Alpha", qty: 100 },
  { id: "c", name: "Charlie", qty: 3 },
];
const columns = [
  { key: "name", header: "Name", render: (r: Row) => r.name, sortValue: (r: Row) => r.name },
  {
    key: "qty",
    header: "Qty",
    align: "end" as const,
    render: (r: Row) => String(r.qty),
    sortValue: (r: Row) => r.qty,
  },
];
const setup = (extra: Partial<Parameters<typeof Table<Row>>[0]> = {}) =>
  render(<Table columns={columns} rows={rows} rowKey={(r) => r.id} caption="Offers" {...extra} />);
const names = () =>
  within(screen.getAllByRole("rowgroup")[1] as HTMLElement)
    .getAllByRole("row")
    .map((r) => within(r).getAllByRole("cell")[0]?.textContent);
const sortOf = (name: string) =>
  screen.getByRole("columnheader", { name }).getAttribute("aria-sort");

describe("Table", () => {
  afterEach(cleanup);

  it("[B1-R13] table sort: toggles asc, desc, none with aria-sort and numeric order", async () => {
    setup();
    const qtyBtn = screen.getByRole("button", { name: "Qty" });
    expect(sortOf("Name")).toBeNull();
    await userEvent.click(qtyBtn);
    expect(names()).toEqual(["Charlie", "Bravo", "Alpha"]);
    expect(sortOf("Qty")).toBe("ascending");
    await userEvent.click(qtyBtn);
    expect(names()).toEqual(["Alpha", "Bravo", "Charlie"]);
    expect(sortOf("Qty")).toBe("descending");
    await userEvent.click(qtyBtn);
    expect(names()).toEqual(["Bravo", "Alpha", "Charlie"]);
    expect(sortOf("Qty")).toBeNull();
  });

  it("[B1-R13] table sort: stable for equal values and only one active header", async () => {
    const tied = [
      { id: "1", name: "x", qty: 1 },
      { id: "2", name: "y", qty: 1 },
      { id: "3", name: "z", qty: 0 },
    ];
    setup({ rows: tied });
    await userEvent.click(screen.getByRole("button", { name: "Qty" }));
    expect(names()).toEqual(["z", "x", "y"]);
    await userEvent.click(screen.getByRole("button", { name: "Name" }));
    expect(sortOf("Qty")).toBeNull();
    expect(sortOf("Name")).toBe("ascending");
  });

  it("[B1-R13] table selection: click, Enter and Space select; selected row is aria-selected", async () => {
    const onRowSelect = vi.fn();
    setup({ onRowSelect, selectedKey: "b" });
    const [first, second] = screen.getAllByRole("row").slice(1);
    expect(second?.getAttribute("aria-selected")).toBe("true");
    expect(first?.getAttribute("aria-selected")).toBe("false");
    await userEvent.click(first as HTMLElement);
    expect(onRowSelect).toHaveBeenLastCalledWith(rows[0]);
    (second as HTMLElement).focus();
    await userEvent.keyboard("{Enter}");
    expect(onRowSelect).toHaveBeenLastCalledWith(rows[1]);
    await userEvent.keyboard(" ");
    expect(onRowSelect).toHaveBeenCalledTimes(3);
  });

  it("[B1-R13] table selection: other keys and inner control keys do not double-select", async () => {
    const onRowSelect = vi.fn();
    render(
      <Table
        columns={[
          { key: "n", header: "N", render: (r: Row) => <button type="button">{r.name}</button> },
        ]}
        rows={rows}
        rowKey={(r) => r.id}
        caption="Offers"
        onRowSelect={onRowSelect}
      />,
    );
    (screen.getAllByRole("row")[1] as HTMLElement).focus();
    await userEvent.keyboard("a");
    screen.getByRole("button", { name: "Bravo" }).focus();
    await userEvent.keyboard("{Enter}");
    // The inner button's own click bubbles once; its keydown must not select a second time.
    expect(onRowSelect).toHaveBeenCalledTimes(1);
  });

  it("[B1-R13] table selection: rows are not interactive without onRowSelect", () => {
    setup();
    const row = screen.getAllByRole("row")[1] as HTMLElement;
    expect(row.hasAttribute("tabindex")).toBe(false);
    expect(row.hasAttribute("aria-selected")).toBe(false);
  });

  it("[B1-R13] table states: loading is busy, empty shows the empty content", () => {
    const { rerender } = setup({ loading: true });
    expect(screen.getByRole("table").getAttribute("aria-busy")).toBe("true");
    expect(screen.getByText("Loading…")).toBeTruthy();
    rerender(
      <Table columns={columns} rows={[]} rowKey={(r) => r.id} caption="Offers" empty="No offers" />,
    );
    expect(screen.getByText("No offers")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Offers" })).toBeTruthy();
  });

  it("[B1-R13] table layout: end alignment and a scroll container", () => {
    const { container } = setup();
    const qtyCell = screen.getAllByRole("cell")[1] as HTMLElement;
    expect(qtyCell.getAttribute("data-align")).toBe("end");
    expect(container.querySelector("[data-scroll]")).toBeTruthy();
  });
});
