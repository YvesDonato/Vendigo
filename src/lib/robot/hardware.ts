import { readFile } from "node:fs/promises";
import { join } from "node:path";

export interface RobotHardware {
  unlockCompartment(robotId: string, compartmentId: number): Promise<void>;
  lockCompartment(robotId: string, compartmentId: number): Promise<void>;
  stopRobot(robotId: string): Promise<void>;
  resumeRobot(robotId: string): Promise<void>;
  returnToBase(robotId: string): Promise<void>;
}

const acknowledge = async () => {
  await new Promise<void>((resolve) => setTimeout(resolve, 180));
};

export const simulatedHardware: RobotHardware = {
  unlockCompartment: acknowledge,
  lockCompartment: acknowledge,
  stopRobot: acknowledge,
  resumeRobot: acknowledge,
  returnToBase: acknowledge,
};

async function setLid(state: "open" | "closed") {
  const url = process.env.LID_API_URL;
  if (!url) return acknowledge();
  const token = process.env.LID_API_KEY?.trim() || (await readFile(
    /* turbopackIgnore: true */ process.env.LID_API_TOKEN_FILE ?? join(process.cwd(), "robot_code/lid-api.token"), "utf8",
  )).trim();
  if (token.length < 32) throw new Error("Lid API key is not configured.");
  const response = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", "User-Agent": "Vendigo-Storefront/1.0" },
    body: JSON.stringify({ state }),
    cache: "no-store", redirect: "error", signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error(`Lid API rejected ${state}: HTTP ${response.status}.`);
  const result = await response.json();
  if (result.commanded_state !== state || result.commanded_angle !== (state === "open" ? 0 : 180) || result.enabled !== true) {
    throw new Error("Lid controller did not acknowledge the requested position.");
  }
}

// This robot has one shared lid for every catalog item. The store owns its timer.
export const robotHardware: RobotHardware = {
  ...simulatedHardware,
  unlockCompartment: () => setLid("open"),
  lockCompartment: () => setLid("closed"),
};
