"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BottomActionBar } from "@/components/BottomActionBar";
import { Header } from "@/components/Header";
import { RequestSummary } from "@/components/RequestSummary";
import { useDelivery } from "@/context/DeliveryContext";
import { createDeliveryRequest } from "@/lib/mockDelivery";

export default function ReviewPage() {
  const router = useRouter();
  const { draft, itemCount, setItemQuantity, setRequest, hydrated } = useDelivery();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!hydrated) return;
    if (itemCount === 0) router.replace("/");
    else if (!draft.locationId) router.replace("/location");
  }, [hydrated, itemCount, draft.locationId, router]);

  async function submitRequest() {
    if (!draft.locationId || submitting) return;
    setSubmitting(true);
    try {
      const request = await createDeliveryRequest({
        selections: draft.selections,
        locationId: draft.locationId,
        locationLabel: draft.locationLabel,
      });
      setRequest(request);
      router.push("/tracking");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="app-shell has-bottom-action">
      <Header backHref="/location" step="2 / 2" />
      <div className="page-content">
        <section className="page-intro compact-intro">
          <h1>Review</h1>
        </section>

        <RequestSummary
          selections={draft.selections}
          locationLabel={draft.locationLabel}
          editable
          onQuantityChange={setItemQuantity}
        />

        <div className="wait-estimate">
          <span>Estimated wait</span>
          <strong>8 min</strong>
        </div>
      </div>
      <BottomActionBar
        label="Request snacks"
        onClick={submitRequest}
        disabled={itemCount === 0 || !draft.locationId}
        loading={submitting}
      />
    </main>
  );
}
