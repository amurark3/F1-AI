import { afterEach, describe, expect, it } from "vitest";

import { focusables, moveFocus, trapTab, wrapIndex } from "./focus";

/** A container with three reachable controls and two that are not. */
function mount(): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML = `
    <a href="/one">One</a>
    <a>No href</a>
    <button type="button">Two</button>
    <button type="button" disabled>Off</button>
    <div hidden><a href="/hidden">Hidden</a></div>
    <a href="/three">Three</a>`;
  document.body.append(root);
  return root;
}

const label = () => document.activeElement?.textContent;

afterEach(() => {
  document.body.innerHTML = "";
});

describe("wrapIndex", () => {
  it("steps forward and back, wrapping round both ends", () => {
    expect(wrapIndex(0, 1, 3)).toBe(1);
    expect(wrapIndex(2, 1, 3)).toBe(0);
    expect(wrapIndex(0, -1, 3)).toBe(2);
  });
});

describe("focusables", () => {
  it("lists the links and enabled buttons a keyboard can reach, in order", () => {
    expect(focusables(mount()).map((el) => el.textContent)).toEqual(["One", "Two", "Three"]);
  });
});

describe("moveFocus", () => {
  it("lands on the first or last item when focus is outside the list", () => {
    const items = focusables(mount());
    moveFocus(items, 1);
    expect(label()).toBe("One");
    (document.activeElement as HTMLElement).blur();
    moveFocus(items, -1);
    expect(label()).toBe("Three");
  });

  it("steps from the focused item, wrapping round", () => {
    const items = focusables(mount());
    items[2]?.focus();
    moveFocus(items, 1);
    expect(label()).toBe("One");
    moveFocus(items, -1);
    expect(label()).toBe("Three");
  });

  it("does nothing with no items", () => {
    expect(() => moveFocus([], 1)).not.toThrow();
  });
});

describe("trapTab", () => {
  it("sends Tab from the last control back to the first", () => {
    const root = mount();
    focusables(root)[2]?.focus();
    expect(trapTab(root, false)).toBe(true);
    expect(label()).toBe("One");
  });

  it("sends Shift+Tab from the first control round to the last", () => {
    const root = mount();
    focusables(root)[0]?.focus();
    expect(trapTab(root, true)).toBe(true);
    expect(label()).toBe("Three");
  });

  it("leaves Tab alone between the ends, so the browser moves focus", () => {
    const root = mount();
    focusables(root)[1]?.focus();
    expect(trapTab(root, false)).toBe(false);
    expect(trapTab(root, true)).toBe(false);
    expect(label()).toBe("Two");
  });

  it("does nothing in a container with nothing to focus", () => {
    const root = document.createElement("div");
    document.body.append(root);
    expect(trapTab(root, false)).toBe(false);
  });
});
