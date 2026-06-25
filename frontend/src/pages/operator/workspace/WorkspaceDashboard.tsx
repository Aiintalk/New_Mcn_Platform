// Placeholder — will be replaced in Task 10
export default function WorkspaceDashboard({ kolId, onKolLoaded }: {
  kolId: number;
  onKolLoaded?: (kol: { name: string; avatar_url: string | null }) => void;
}) {
  void kolId; void onKolLoaded;
  return <div data-testid="workspace-dashboard" />;
}
