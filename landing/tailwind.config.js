/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          paper: "#fafaf7",
          ink: "#242e31",
          petrol: "#174b56",
          copper: "#f0a273",
          mist: "#edf1ef",
        },
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "sans-serif"],
        editorial: ["Source Serif 4", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
}
