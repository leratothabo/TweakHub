// Flat ESLint config (required by ESLint 9, which this repo pins).
// `next lint` and the legacy `.eslintrc.json` it read were both removed in
// Next.js 16 — `eslint-config-next`'s flat-config export is the direct
// replacement for the old "next/core-web-vitals" string in .eslintrc.json.
const nextCoreWebVitals = require("eslint-config-next/core-web-vitals");

module.exports = [
  ...nextCoreWebVitals,
  {
    ignores: [".next/**", "node_modules/**"],
  },
];
