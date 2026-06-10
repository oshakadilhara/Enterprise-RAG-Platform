import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthStore } from "@/stores/authStore";

export function Settings() {
  const user = useAuthStore((s) => s.user);

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-muted-foreground">Configure platform preferences</p>
      </div>

      <div className="max-w-2xl space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
            <CardDescription>Your account information</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="text-sm font-medium">Full Name</label>
              <p className="text-muted-foreground">{user?.full_name}</p>
            </div>
            <div>
              <label className="text-sm font-medium">Email</label>
              <p className="text-muted-foreground">{user?.email}</p>
            </div>
            <div>
              <label className="text-sm font-medium">Role</label>
              <p className="text-muted-foreground capitalize">{user?.role?.replace("_", " ")}</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>AI Configuration</CardTitle>
            <CardDescription>Managed by organization administrators</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="font-medium">LLM Provider</p>
                <p className="text-muted-foreground">Configurable via environment</p>
              </div>
              <div>
                <p className="font-medium">Embedding Provider</p>
                <p className="text-muted-foreground">Configurable via environment</p>
              </div>
              <div>
                <p className="font-medium">Hybrid Search</p>
                <p className="text-muted-foreground">0.6 Vector + 0.4 BM25</p>
              </div>
              <div>
                <p className="font-medium">Reranker</p>
                <p className="text-muted-foreground">BGE Reranker v2</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Security</CardTitle>
            <CardDescription>Authentication and access control</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>JWT authentication with refresh tokens</p>
            <p>Role-based access control (RBAC)</p>
            <p>Rate limiting enabled</p>
            <p>Audit logging for all mutations</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
