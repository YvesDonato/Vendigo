"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { BottomActionBar } from "@/components/BottomActionBar";
import { Header } from "@/components/Header";
import { LocationPicker } from "@/components/LocationPicker";
import { useDelivery } from "@/context/DeliveryContext";
import { locations } from "@/data/locations";

export default function LocationPage() {
  const router = useRouter();
  const { draft, itemCount, setLocation, hydrated } = useDelivery();

  useEffect(() => {
    if (hydrated && itemCount === 0) router.replace("/");
  }, [hydrated, itemCount, router]);

  return (
    <main className="app-shell has-bottom-action">
      <Header backHref="/" step="1 / 2" />
      <div className="page-content">
        <section className="page-intro">
          <h1>Your location</h1>
        </section>
        <LocationPicker
          locations={locations}
          selectedId={draft.locationId}
          selectedLabel={draft.locationLabel}
          onSelect={setLocation}
        />
      </div>
      <BottomActionBar
        label="Continue"
        onClick={() => router.push("/review")}
        disabled={!draft.locationId || !draft.locationLabel}
      />
    </main>
  );
}
