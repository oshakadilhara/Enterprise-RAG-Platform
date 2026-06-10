import { useQuery } from "@tanstack/react-query";
import { FileText, MessageSquare, Users, Zap } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { workspaceApi, analyticsApi } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

export function Dashboard() {
  const user = useAuthStore((s) => s.user);

  const { data: workspaces } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => workspaceApi.list().then((r) => r.data),
  });

  const { data: analytics } = useQuery({
    queryKey: ["analytics"],
    queryFn: () => analyticsApi.usage(30).then((r) => r.data),
  });

  const totalDocs = workspaces?.items?.reduce((sum: number, w: { document_count: number }) => sum + w.document_count, 0) || 0;

  const stats = [
    { label: "Workspaces", value: workspaces?.total || 0, icon: FileText, color: "text-blue-600" },
    { label: "Documents", value: totalDocs, icon: FileText, color: "text-green-600" },
    { label: "Queries (30d)", value: analytics?.summary?.total_queries || 0, icon: MessageSquare, color: "text-purple-600" },
    { label: "Avg Latency", value: `${Math.round(analytics?.summary?.avg_latency_ms || 0)}ms`, icon: Zap, color: "text-orange-600" },
  ];

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold">Welcome back, {user?.full_name?.split(" ")[0]}</h1>
        <p className="text-muted-foreground">Here's an overview of your knowledge platform</p>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {stat.label}
                </CardTitle>
                <Icon className={`h-4 w-4 ${stat.color}`} />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stat.value}</div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recent Workspaces</CardTitle>
          </CardHeader>
          <CardContent>
            {workspaces?.items?.length ? (
              <ul className="space-y-3">
                {workspaces.items.slice(0, 5).map((ws: { id: string; name: string; document_count: number; member_count: number }) => (
                  <li key={ws.id} className="flex items-center justify-between rounded-lg border p-3">
                    <div>
                      <p className="font-medium">{ws.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {ws.document_count} docs · {ws.member_count} members
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">No workspaces yet. Create one to get started.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <a href="/chat" className="flex items-center gap-3 rounded-lg border p-4 hover:bg-accent transition-colors">
              <MessageSquare className="h-5 w-5 text-primary" />
              <div>
                <p className="font-medium">Start a Chat</p>
                <p className="text-sm text-muted-foreground">Ask questions about your documents</p>
              </div>
            </a>
            <a href="/documents" className="flex items-center gap-3 rounded-lg border p-4 hover:bg-accent transition-colors">
              <FileText className="h-5 w-5 text-primary" />
              <div>
                <p className="font-medium">Upload Documents</p>
                <p className="text-sm text-muted-foreground">Add PDF, DOCX, TXT, or CSV files</p>
              </div>
            </a>
            <a href="/users" className="flex items-center gap-3 rounded-lg border p-4 hover:bg-accent transition-colors">
              <Users className="h-5 w-5 text-primary" />
              <div>
                <p className="font-medium">Manage Users</p>
                <p className="text-sm text-muted-foreground">Invite team members to workspaces</p>
              </div>
            </a>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
