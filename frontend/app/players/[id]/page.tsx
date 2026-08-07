import { Suspense } from "react";

import { PlayerAnalyticsView } from "@/components/PlayerAnalyticsView";
import { LoadingState } from "@/components/LoadingState";

export default async function PlayerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <Suspense fallback={<LoadingState />}><PlayerAnalyticsView playerId={Number(id)} /></Suspense>;
}
