/** @type {import('next').NextConfig} */
const nextConfig = {
  // The CopilotKit runtime route proxies to the Python AG-UI backend (default :8000).
  env: {
    AGUI_URL: process.env.AGUI_URL ?? "http://localhost:8000/",
  },
  // Home is the live "watch it climb" view; the Logfire run-history lives at /history.
  async redirects() {
    return [{ source: "/", destination: "/live", permanent: false }];
  },
  turbopack: {
    // Pin the project root to THIS dir. Without it Next infers the root from a stray
    // ~/package-lock.json and mis-resolves aliases.
    root: import.meta.dirname,
    // CopilotKit's runtime eagerly imports its OpenAI adapter; we never use it (MiniMax via
    // AG-UI + ExperimentalEmptyAdapter). Alias `openai` to an unused stub → zero OpenAI dep.
    // Relative paths in resolveAlias are resolved from `root`.
    resolveAlias: {
      openai: "./stub-openai.mjs",
    },
  },
};

export default nextConfig;
