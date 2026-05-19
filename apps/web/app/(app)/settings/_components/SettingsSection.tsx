// Shared visual wrapper for a logical group of fields. Used inside all six
// settings pages so they share padding, heading scale, and divider style.

export function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-input bg-card p-6 shadow-sm">
      <header className="mb-4 flex flex-col gap-1">
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
      </header>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}
