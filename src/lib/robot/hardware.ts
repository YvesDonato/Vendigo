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

/** Replace these acknowledgements with vehicle HTTP/WebSocket calls.
 * Resolve only after hardware acknowledges; reject on timeout or failure.
 * Keep command arbitration, inventory, and relock scheduling in the store.
 */
export const simulatedHardware: RobotHardware = {
  unlockCompartment: acknowledge,
  lockCompartment: acknowledge,
  stopRobot: acknowledge,
  resumeRobot: acknowledge,
  returnToBase: acknowledge,
};
