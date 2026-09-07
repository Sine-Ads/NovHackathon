/**
 * Role presets.
 *
 * Each one is a filter over dimensions the corpus actually has — the derived
 * category, and the Phase 1 classifier's verdict. None of them asserts that a
 * record has been *routed* to a team: nothing in the data supports that claim,
 * so the UI offers a lens rather than an assignment.
 */
import type { Category, SignalCategory } from "./types";

export type Role =
  | "Leadership"
  | "Clinical Development"
  | "Medical Affairs"
  | "Commercial / Brand"
  | "Evidence Review";

export interface RoleFocus {
  kinds: SignalCategory[];
  verdicts: Category[];
  description: string;
}

export const ROLE_FOCUS: Record<Role, RoleFocus> = {
  Leadership: {
    kinds: [],
    verdicts: [],
    description: "Everything monitored, most urgent first",
  },
  "Clinical Development": {
    kinds: ["Trial"],
    verdicts: [],
    description: "Trial registrations, status changes and sponsors",
  },
  "Medical Affairs": {
    kinds: ["Publication"],
    verdicts: [],
    description: "Peer-reviewed literature and preprints",
  },
  "Commercial / Brand": {
    kinds: ["Corporate"],
    verdicts: [],
    description: "Corporate filings from companies in the field",
  },
  "Evidence Review": {
    kinds: [],
    verdicts: ["proven_right", "proven_false", "proven_false_but_useful"],
    description: "Records the classifier has reached a verdict on",
  },
};

export const ALL_ROLES = Object.keys(ROLE_FOCUS) as Role[];
