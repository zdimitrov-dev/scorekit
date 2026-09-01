"use client";
import { useEffect } from "react";
import { startTracking } from "@/lib/track";

/** Registers the interaction logger's flush-on-exit handlers once for the whole app.
 *  Renders nothing; it exists because the root layout is a server component. */
export default function TrackingBoot() {
  useEffect(() => startTracking(), []);
  return null;
}
