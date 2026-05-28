import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Geist", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["Geist Mono", "JetBrains Mono", "ui-monospace", "monospace"],
        serif: ["Instrument Serif", "Cormorant Garamond", "Georgia", "serif"],
      },
      colors: {
        ink: {
          0: "#0a0908",
          1: "#100e0c",
          2: "#161412",
          3: "#1d1a17",
          4: "#26221e",
          5: "#322d28",
          6: "#46403a",
        },
        paper: {
          0: "#f4ede0",
          1: "#e8e0d2",
          2: "#c9bfae",
          3: "#9b9384",
          4: "#6c6558",
          5: "#4a443a",
        },
        amber: { DEFAULT: "#d4a574", dim: "#8a6c4c" },
        sage:  { DEFAULT: "#8aab8e", dim: "#5a7060" },
        rust:  { DEFAULT: "#c2745f", dim: "#7a4738" },
        sky:   { DEFAULT: "#7fa6c9", dim: "#4e6e8a" },
        plum:  { DEFAULT: "#a888b5" },
      },
      animation: {
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        "shimmer": "shimmer 1.5s infinite",
        "float": "float 3s ease-in-out infinite",
        "typing-dot": "typing-dot 1.4s ease-in-out infinite",
        "fade-in": "fadeIn 0.4s ease-out",
        "fade-in-up": "fadeInUp 0.4s ease-out",
        "scale-in": "scaleIn 0.3s ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
