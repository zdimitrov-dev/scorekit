"use client";
import { useEffect } from "react";
import { startTracking } from "@/lib/track";
import { warmFeed } from "@/lib/feedCache";

/** App-wide startup: registers the interaction logger's flush-on-exit handlers, and
 *  builds the home ranking in the background so it is already waiting whenever the Home
 *  tab is opened — from Search, from Saved, or on a fresh load. Renders nothing. */
export default function TrackingBoot() {
  useEffect(() => {
    startTracking();
    warmFeed();
  }, []);
  return null;
}
