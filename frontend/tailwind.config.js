/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["selector", '[data-theme="dark"]'],
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        pocket: {
          bg: "#f6f6f8",
          primary: "#135bec",
          surface: "#ffffff",
          "surface-container": "#f1f3f9",
          "surface-high": "#e8ebf4",
          outline: "#cbd5e1",
          muted: "#64748b",
          ink: "#0f172a",
        },
      },
      borderRadius: {
        pocket: "0.75rem",
        "pocket-lg": "1rem",
        "pocket-xl": "1.5rem",
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
};
