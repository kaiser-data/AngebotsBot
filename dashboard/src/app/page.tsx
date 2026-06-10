import { Suspense } from "react";
import { ForYouFeed } from "@/components/ForYouFeed";

export const metadata = {
  title: "Für dich · AngebotsBot",
};

// The feed is fully client-driven (preferences live in localStorage), so the
// page itself is a static shell. ForYouFeed reads useSearchParams() (week
// filter) and therefore needs a Suspense boundary for static prerendering.
export default function HomePage() {
  return (
    <Suspense>
      <ForYouFeed />
    </Suspense>
  );
}
