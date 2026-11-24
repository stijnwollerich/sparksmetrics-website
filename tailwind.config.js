/** Tailwind v3 config for sparksmetrics.com (was the inline tailwind.config in base.html, CDN build). */
module.exports = {
  darkMode: "class",
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
    "./app/**/*.py",
    "./app/blog_posts.json",
  ],
  theme: {
    extend: {
      colors: {
        primary: "#FF4D00",
        "deep-charcoal": "#1A1A1B",
        "light-base": "#F9F9FB",
        "background-dark": "#050505",
        charcoal: "#0F0F0F",
        surface: "#161616",
        "off-white": "#F9F9FB",
      },
      fontFamily: {
        display: ["Lexend", "sans-serif"],
        sans: ["Inter", "sans-serif"],
      },
    },
  },
  plugins: [require("@tailwindcss/forms"), require("@tailwindcss/container-queries")],
};
