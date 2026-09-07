/**
 * User-facing failure copy.
 *
 * Nothing thrown, no status code and no backend string is ever rendered: a
 * stakeholder reading a card should not be shown a TypeError or an
 * environment variable name. The detail is still needed to debug, so it goes
 * to the browser console, where an operator can find it and a reader will not.
 */

export const FAILURE_COPY = {
  feed: "The record feed is unavailable right now. It should return shortly.",
  summary:
    "An AI summary is not available for this record right now. The structured facts below come straight from the source.",
  chat: "The assistant is unavailable right now. Any sources already retrieved are listed below.",
} as const;

export type FailureKind = keyof typeof FAILURE_COPY;

/** Log the real cause for operators, return the copy a reader should see. */
export function userMessage(kind: FailureKind, detail?: unknown): string {
  if (detail !== undefined) {
    console.error(`[radar] ${kind} failed:`, detail);
  }
  return FAILURE_COPY[kind];
}
