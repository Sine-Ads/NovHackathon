import type { Config } from "tailwindcss";

/**
 * The palette is the radar design system: a light, low-chrome, editorial
 * surface. The legacy plain-CSS classes in globals.css are driven by CSS
 * variables set to these same values, so the two styling systems cannot drift
 * apart — change a colour here and change it there.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F6F7F9",
        surface: "#FFFFFF",
        border: "#E1E4E9",
        ink: "#1A2130",
        "ink-muted": "#5B6472",
        accent: "#1F5F5B",
        "accent-soft": "#E4EEEC",
        high: "#B8452F",
        "high-soft": "#F6E6E2",
        medium: "#B07A2E",
        "medium-soft": "#F5EBDC",
        low: "#7C8797",
        "low-soft": "#EEF0F2",
        closed: "#4B7A5E",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
