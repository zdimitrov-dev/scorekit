// Starts the FastAPI backend using the project's virtualenv Python.
// Cross-platform: picks the right venv path for Windows vs. macOS/Linux.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";

const isWin = process.platform === "win32";
const python = isWin ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";

if (!existsSync(python)) {
  console.error(
    `\n[api] venv Python not found at "${python}".\n` +
      "[api] Create it first:  python -m venv .venv   then   pip install -r requirements.txt\n",
  );
  process.exit(1);
}

const child = spawn(
  python,
  ["-m", "uvicorn", "scorekit.api:app", "--reload", "--port", "8000"],
  { stdio: "inherit" },
);

child.on("exit", (code) => process.exit(code ?? 0));
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, () => child.kill(sig));
}
