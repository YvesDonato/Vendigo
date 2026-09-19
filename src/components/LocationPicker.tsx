"use client";

import { useMemo, useState } from "react";
import { Check, MapPin, Search } from "lucide-react";
import type { VenueLocation } from "@/lib/types";

type LocationPickerProps = {
  locations: VenueLocation[];
  selectedId: string | null;
  selectedLabel: string;
  onSelect: (id: string, label: string) => void;
};

export function getLocationLabel(location: VenueLocation) {
  return [location.name, location.description].filter(Boolean).join(" — ");
}

export function LocationPicker({
  locations,
  selectedId,
  selectedLabel,
  onSelect,
}: LocationPickerProps) {
  const [query, setQuery] = useState("");
  const [manual, setManual] = useState(
    selectedId === "manual" ? selectedLabel : "",
  );

  const filtered = useMemo(() => {
    const search = query.trim().toLowerCase();
    if (!search) return locations;
    return locations.filter((location) =>
      getLocationLabel(location).toLowerCase().includes(search),
    );
  }, [locations, query]);

  return (
    <div className="location-picker">
      <label className="search-field">
        <Search size={18} strokeWidth={1.8} aria-hidden="true" />
        <span className="sr-only">Search locations</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search locations"
        />
      </label>

      <div className="location-list" role="radiogroup" aria-label="Known locations">
        {filtered.map((location) => {
          const isSelected = selectedId === location.id;
          return (
            <button
              className={`location-option${isSelected ? " is-selected" : ""}`}
              type="button"
              role="radio"
              aria-checked={isSelected}
              key={location.id}
              onClick={() => onSelect(location.id, getLocationLabel(location))}
            >
              <span className="location-icon" aria-hidden="true">
                <MapPin size={18} strokeWidth={1.8} />
              </span>
              <span className="location-copy">
                <strong>{location.name}</strong>
                {location.description && <span>{location.description}</span>}
              </span>
              <span className="radio-indicator" aria-hidden="true">
                {isSelected && <Check size={13} strokeWidth={2.5} />}
              </span>
            </button>
          );
        })}
        {filtered.length === 0 && (
          <p className="empty-state">No known locations match “{query}”.</p>
        )}
      </div>

      <div className="manual-location">
        <div className="section-label-row">
          <span className="section-label">Other location</span>
        </div>
        <label className="text-field">
          <span className="sr-only">Describe another location</span>
          <input
            type="text"
            value={manual}
            maxLength={80}
            onChange={(event) => {
              const value = event.target.value;
              setManual(value);
              if (value.trim()) onSelect("manual", value.trim());
            }}
            onBlur={() => manual.trim() && onSelect("manual", manual.trim())}
            placeholder="e.g. North hallway, blue booth"
          />
        </label>
      </div>
    </div>
  );
}
