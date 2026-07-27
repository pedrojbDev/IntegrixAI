/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          cream: "#f5f1e7",
          paper: "#fbfaf5",
          ink: "#14241c",
          green: "#16764b",
          lime: "#d9ff57",
          coral: "#ff7158",
          sky: "#63d4ff",
        },
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "sans-serif"],
        display: ["Bricolage Grotesque", "sans-serif"],
      },
    },
  },
  plugins: [],
}
