/** An emailed reset link: `#/reset?token=…`. */
export function isResetLink(hash: string): boolean {
  return /^#\/reset\?(?:.*&)?token=[^&]+/.test(hash);
}

/** Accounts mode shows the sign-in page when signed out, and for a reset link even when a session is saved:
 *  otherwise a browser that's still signed in can never reach the reset form. */
export function showsSignIn(accountMode: boolean, signedIn: boolean, hash: string): boolean {
  return accountMode && (!signedIn || isResetLink(hash));
}
