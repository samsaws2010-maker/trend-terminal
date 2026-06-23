export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-[100dvh] w-full bg-background overflow-y-auto text-sm font-sans">
      <div className="pl-3 pr-6 py-6 h-full space-y-6">
        {children}
      </div>
    </div>
  );
}