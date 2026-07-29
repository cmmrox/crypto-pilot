import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Initial data loads and polling callbacks intentionally begin in effects.
      // They synchronize this client with external API state rather than deriving
      // local render state, so the React Compiler-oriented rule is not applicable.
      "react-hooks/set-state-in-effect": "off",
    },
  },
);
