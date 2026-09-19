import { allVenueLocations, type VenueLocation } from "../../data/venue-locations.ts";

export type ResolveLocationInput = {
  query: string;
  floor?: number;
};

export type PublicLocation = Pick<VenueLocation, "id" | "name" | "floor">;

export type ResolveLocationResult = {
  found: boolean;
  location?: PublicLocation;
  candidates?: PublicLocation[];
};

const normalize = (value: string) =>
  value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

const publicLocation = ({ id, name, floor }: VenueLocation): PublicLocation => ({ id, name, floor });

export function resolveLocation({ query, floor }: ResolveLocationInput): ResolveLocationResult {
  const normalizedQuery = normalize(query);
  if (!normalizedQuery) return { found: false };

  const locations = floor !== undefined
    ? allVenueLocations.filter((candidate) => candidate.floor === floor)
    : allVenueLocations;

  const exact = locations.filter((candidate) =>
    [candidate.name, ...candidate.aliases].some((value) => normalize(value) === normalizedQuery),
  );

  if (exact.length === 1) return { found: true, location: publicLocation(exact[0]) };
  if (exact.length > 1) return { found: false, candidates: exact.map(publicLocation) };

  const partial = locations.filter((candidate) =>
    [candidate.name, ...candidate.aliases].some((value) => {
      const normalizedValue = normalize(value);
      return normalizedValue.includes(normalizedQuery) || normalizedQuery.includes(normalizedValue);
    }),
  );

  if (partial.length === 1) return { found: true, location: publicLocation(partial[0]) };
  if (partial.length > 1) return { found: false, candidates: partial.map(publicLocation) };
  return { found: false };
}
