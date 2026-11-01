import { describe, expect, it } from "vitest";
import { isResetLink, showsSignIn } from "./gate";

describe("sign-in gate", () => {
  it("opens a reset link even in a browser that is still signed in", () => {
    expect(showsSignIn(true, true, "#/reset?token=abc123")).toBe(true);
  });

  it("keeps a signed-in user in the app everywhere else", () => {
    expect(showsSignIn(true, true, "#/search")).toBe(false);
    expect(showsSignIn(true, true, "#/reset")).toBe(false); // no token: nothing to reset with
    expect(showsSignIn(true, false, "#/search")).toBe(true);
  });

  it("never gates the local, single-user mode", () => {
    expect(showsSignIn(false, false, "#/reset?token=abc123")).toBe(false);
  });

  it("finds the token wherever it sits in the query", () => {
    expect(isResetLink("#/reset?utm=mail&token=abc")).toBe(true);
    expect(isResetLink("#/search?token=abc")).toBe(false);
  });
});
