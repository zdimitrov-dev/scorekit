import DevDashboard from "@/components/DevDashboard";

// Development surface, not part of the product. Remove this route, the component,
// web/app/api/dev and the /dev/stats endpoint before release.
export default function DevPage() {
  return (
    <div className="mx-auto max-w-4xl px-3 pt-4 sm:px-5">
      <DevDashboard />
    </div>
  );
}
