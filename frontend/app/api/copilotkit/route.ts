// CopilotKit runtime route — bridges the React frontend to the Python AG-UI backend.
// The trained M3 seller is a self-hosted AG-UI agent (gambit/agui.py); CopilotKit forwards
// the chat to it over the AG-UI protocol. No separate LLM service adapter: the agent IS the LLM.
import {
  CopilotRuntime,
  copilotRuntimeNextJSAppRouterEndpoint,
  ExperimentalEmptyAdapter,
} from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";
import { NextRequest } from "next/server";

const AGUI_URL = process.env.AGUI_URL ?? "http://localhost:8000/";

const runtime = new CopilotRuntime({
  agents: {
    // the human is the BUYER; this agent plays the trained SELLER
    seller: new HttpAgent({ url: AGUI_URL }),
  },
});

export const POST = async (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter: new ExperimentalEmptyAdapter(),
    endpoint: "/api/copilotkit",
  });
  return handleRequest(req);
};
