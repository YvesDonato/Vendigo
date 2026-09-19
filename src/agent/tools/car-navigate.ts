import { allVenueLocations, type VenueLocation } from "../../data/venue-locations.ts";

export type CarNavigateInput = {
  source_location_id: string;
  target_location_id: string;
};

export type CarNavigateResult = {
  success: boolean;
  status: "arrived" | "failed";
  source?: Pick<VenueLocation, "id" | "name" | "floor">;
  target?: Pick<VenueLocation, "id" | "name" | "floor">;
  simulated: true;
  error?: string;
};

const wait = (milliseconds: number) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

// Replace only this function body when the Jev agent-car API is ready.
export async function mockCarNavigate({
  source_location_id,
  target_location_id,
}: CarNavigateInput): Promise<CarNavigateResult> {
  const source = allVenueLocations.find(({ id }) => id === source_location_id);
  const target = allVenueLocations.find(({ id }) => id === target_location_id);

  if (!source || !target) {
    return {
      success: false,
      status: "failed",
      simulated: true,
      error: "One or both location IDs are not in the venue registry.",
    };
  }

  await wait(700);

  return {
    success: true,
    status: "arrived",
    source: { id: source.id, name: source.name, floor: source.floor },
    target: { id: target.id, name: target.name, floor: target.floor },
    simulated: true,
  };
}

export const carNavigate = mockCarNavigate;
