import { LogoMark } from "@/components/logo";

// Served by the service worker when a navigation fails offline.
export default function OfflinePage() {
  return (
    <div className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center gap-4 px-4 py-24 text-center">
      <LogoMark className="size-12" />
      <h1 className="font-heading text-xl font-semibold">You&apos;re offline</h1>
      <p className="text-sm text-muted-foreground">
        Deep-Foundry needs a connection to reach your foundry. Your coworkers
        keep working server-side — reconnect to catch up.
      </p>
    </div>
  );
}
