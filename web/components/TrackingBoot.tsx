"use client";
import { useEffect } from "react";
import { startTracking, syncSignals } from "@/lib/track";
import { warmFeed } from "@/lib/feedCache";

/** App-wide startup: registers the interaction logger's flush-on-exit handlers, reconciles
 *  this browser's likes and saves with the database, and builds the home ranking in the
 *  background so it is already waiting whenever the Home tab is opened — from Search, from
 *  Saved, or on a fresh load. Renders nothing. */
export default function TrackingBoot() {
  useEffect(() => {
    startTracking();
    // Backfills anything liked while the API was unreachable. Without this the two stores
    // drift further apart with every outage and nothing ever notices.
    void syncSignals();
    warmFeed();
  }, []);
  return null;
}
