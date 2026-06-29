// PM2 process definitions for the gambit.nudepineapple.com deploy.
//   pm2 start ecosystem.config.cjs && pm2 save
//
// Two processes behind one nginx vhost (see deploy/nginx note in README):
//   - gambit-api : Python AG-UI seller + Logfire run-history reader (uvicorn)  -> 127.0.0.1:8000
//   - gambit-web : Next.js UI (chat + run history)                              -> 127.0.0.1:3002
// Both bind to loopback only; nginx terminates TLS and routes by path.
const ROOT = "/home/matt/Programming/Projects/gambit";

module.exports = {
  apps: [
    {
      name: "gambit-api",
      cwd: ROOT, // pydantic-settings reads ./.env and the backend reads ./checkpoints relative to cwd
      script: ".venv/bin/uvicorn",
      args: "gambit.agui:app --host 127.0.0.1 --port 8000",
      interpreter: "none", // execute the venv's uvicorn shebang directly (it points at .venv/bin/python)
      instances: 1, // single process: logfire_read holds an in-process cache + one shared poller
      autorestart: true,
      max_restarts: 10,
      env: { PYTHONUNBUFFERED: "1" },
    },
    {
      name: "gambit-web",
      cwd: ROOT + "/frontend",
      script: "node_modules/next/dist/bin/next",
      args: "start -H 127.0.0.1 -p 3002",
      interpreter: "/usr/bin/node",
      instances: 1,
      autorestart: true,
      max_restarts: 10,
      env: {
        NODE_ENV: "production",
        AGUI_URL: "http://127.0.0.1:8000/", // server-side: CopilotKit runtime -> Python AG-UI seller
        COPILOTKIT_TELEMETRY_DISABLED: "true",
      },
    },
  ],
};
