import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import jsxA11y from "eslint-plugin-jsx-a11y";
import sonarjs from "eslint-plugin-sonarjs";
import tseslint from "typescript-eslint";

const eslintConfig = defineConfig([
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "node_modules/**",
    "next-env.d.ts",
    "*.tsbuildinfo",
  ]),

  // eslint-config-next already registers the `import`, `react`, `react-hooks`
  // and `jsx-a11y` plugins, so we only tune their rules below.
  ...nextVitals,
  ...nextTs,

  // Type-aware linting for all first-party TypeScript sources.
  {
    files: ["**/*.ts", "**/*.tsx", "**/*.mts"],
    extends: [
      tseslint.configs.recommendedTypeChecked,
      tseslint.configs.stylisticTypeChecked,
    ],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    settings: {
      "import/resolver": {
        typescript: { project: "./tsconfig.json" },
      },
    },
    plugins: { sonarjs },
    rules: {
      // --- Correctness ---------------------------------------------------
      eqeqeq: ["error", "always", { null: "ignore" }],
      "no-var": "error",
      "prefer-const": ["error", { destructuring: "all" }],
      "no-implicit-coercion": ["error", { boolean: false }],
      "no-param-reassign": ["error", { props: true }],
      "no-return-await": "off",
      "@typescript-eslint/return-await": ["error", "in-try-catch"],
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": [
        "error",
        { checksVoidReturn: { attributes: false } },
      ],
      "@typescript-eslint/await-thenable": "error",
      // Scoped to genuine defaulting. `a || b` used as a boolean test is not a
      // nullish-defaulting bug, and rewriting it to `??` would change behaviour
      // for falsy-but-present values such as `0` and `""`.
      "@typescript-eslint/prefer-nullish-coalescing": [
        "error",
        {
          ignoreConditionalTests: true,
          ignoreBooleanCoercion: true,
          ignoreMixedLogicalExpressions: true,
        },
      ],

      // --- Type hygiene --------------------------------------------------
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          args: "after-used",
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
          ignoreRestSiblings: true,
        },
      ],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "inline-type-imports" },
      ],
      "@typescript-eslint/no-import-type-side-effects": "error",

      // --- Style ---------------------------------------------------------
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "object-shorthand": ["error", "properties"],
      "@typescript-eslint/array-type": ["error", { default: "array-simple" }],

      // --- Code smells: complexity budgets --------------------------------
      // Cyclomatic complexity is enforced on plain logic modules only; the
      // `.tsx` override below swaps it for cognitive complexity, which is the
      // meaningful metric once JSX conditional rendering dominates the count.
      complexity: ["error", 15],
      "max-depth": ["error", 4],
      // `countVoidThis` defaults to false, so an explicit `this` parameter is
      // not counted toward the limit.
      "max-params": ["error", { max: 4 }],
      "max-lines": ["error", { max: 500, skipBlankLines: true, skipComments: true }],
      "max-lines-per-function": [
        "error",
        { max: 80, skipBlankLines: true, skipComments: true, IIFEs: true },
      ],
      "no-nested-ternary": "error",
      "no-else-return": ["error", { allowElseIf: false }],
      "no-lonely-if": "error",
      "no-unneeded-ternary": "error",
      "prefer-template": "error",

      // --- Code smells: sonarjs ------------------------------------------
      "sonarjs/cognitive-complexity": ["error", 15],
      "sonarjs/no-identical-functions": "error",
      "sonarjs/no-identical-expressions": "error",
      "sonarjs/no-all-duplicated-branches": "error",
      "sonarjs/no-duplicated-branches": "error",
      "sonarjs/no-collapsible-if": "error",
      "sonarjs/no-redundant-boolean": "error",
      "sonarjs/no-redundant-jump": "error",
      "sonarjs/no-inverted-boolean-check": "error",
      "sonarjs/no-useless-catch": "error",
      "sonarjs/no-element-overwrite": "error",
      "sonarjs/no-ignored-return": "error",
      "sonarjs/prefer-immediate-return": "error",
      "sonarjs/prefer-object-literal": "error",
      "sonarjs/prefer-single-boolean-return": "error",
      "sonarjs/no-unused-collection": "error",
      "sonarjs/no-gratuitous-expressions": "error",

      // --- Imports -------------------------------------------------------
      "import/no-duplicates": "error",
      "import/newline-after-import": "error",
      "import/order": [
        "error",
        {
          groups: [
            "builtin",
            "external",
            "internal",
            "parent",
            "sibling",
            "index",
            "type",
          ],
          pathGroups: [{ pattern: "@/**", group: "internal" }],
          pathGroupsExcludedImportTypes: ["builtin"],
          "newlines-between": "always",
          alphabetize: { order: "asc", caseInsensitive: true },
        },
      ],

      // --- Accessibility -------------------------------------------------
      ...jsxA11y.flatConfigs.recommended.rules,
      "jsx-a11y/no-autofocus": "off",
    },
  },

  // In components, cyclomatic complexity counts every `{cond && <El/>}` as a
  // branch, so JSX conditional rendering inflates the score above what the logic
  // warrants. Cognitive complexity (15, above) stays the primary gate for
  // comprehension burden; cyclomatic stays on at a modest raised ceiling (20) as
  // a backstop against a component whose *logic* — not its markup — is tangled.
  // The per-function line budget is likewise looser because JSX markup consumes
  // lines without adding behavioural complexity.
  {
    files: ["**/*.tsx"],
    rules: {
      complexity: ["error", 20],
      "max-lines-per-function": [
        "error",
        { max: 120, skipBlankLines: true, skipComments: true, IIFEs: true },
      ],
    },
  },

  // Test suites intentionally hold whole scenarios in one `describe`/`it` block,
  // so function length is not a useful signal there.
  {
    files: [
      "**/*.{test,spec}.{ts,tsx}",
      "**/__tests__/**/*.{ts,tsx}",
    ],
    rules: {
      "max-lines-per-function": "off",
      "max-lines": ["error", { max: 800, skipBlankLines: true, skipComments: true }],
    },
  },

  // Config files are not part of the app's type-checked program.
  {
    files: ["*.mjs", "*.js", "*.config.ts"],
    extends: [tseslint.configs.disableTypeChecked],
    rules: {
      "no-console": "off",
    },
  },
]);

export default eslintConfig;
