/** Tailwind build for the storefront. Run `npm run build:css` after changing classes. */
module.exports = {
  content: ["./frontend/index.html", "./frontend/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f4f9ea",
          100: "#e6f3d3",
          600: "#3f7d20",
          700: "#2f641b",
          800: "#1f4420",
          gold: "#a8763e",
          accent: "#cfe88a",
        },
      },
      fontFamily: {
        sans: ["Nunito Sans", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["Fraunces", "Georgia", "serif"],
      },
    },
  },
};
