// Unused placeholder — Gambit carries ZERO real OpenAI dependency.
//
// CopilotKit's @copilotkit/runtime statically imports its OpenAI service adapter from its
// barrel (`import Openai from "openai"`), so the bundler must resolve the module name. But we
// use `ExperimentalEmptyAdapter` + a self-hosted MiniMax M3 AG-UI agent (gambit/agui.py), so
// `OpenAIAdapter` is never constructed and this stub is never executed. Aliased in
// next.config.mjs (turbopack.resolveAlias) so no OpenAI SDK is installed or called.
export default class OpenAIStub {}
export class OpenAI {}
export class AzureOpenAI {}
