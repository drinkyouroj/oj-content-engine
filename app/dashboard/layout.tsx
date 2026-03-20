import { Sidebar } from "@/components/sidebar";

/**
 * Dashboard layout wrapper.
 *
 * Renders the fixed sidebar on the left and the main content area offset
 * by the sidebar width (220px). All /dashboard/* routes are nested inside
 * this layout.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 ml-[220px] p-8">
        {children}
      </main>
    </div>
  );
}
