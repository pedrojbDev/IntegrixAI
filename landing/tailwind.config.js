/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        corporate: {
          50: "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
        },
        cyan: "#5ee7ff",
        violet: "#8d7dff",
        mint: "#73f4c5",
      },
      boxShadow: {
        glow: "0 22px 70px rgba(37, 99, 235, 0.12)",
        panel: "0 24px 80px rgba(15, 23, 42, 0.14)",
      },
      fontFamily: {
        sans: ["Manrope", "Aptos", "Segoe UI", "sans-serif"],
        display: ["Sora", "Manrope", "Aptos", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Code", "monospace"],
      },
    },
  },
  plugins: [],
}
