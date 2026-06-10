import { useQuery } from "@tanstack/react-query";
import { Users as UsersIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { userApi } from "@/lib/api";
import type { User } from "@/types";

const roleBadge: Record<string, string> = {
  super_admin: "bg-red-100 text-red-800",
  org_admin: "bg-purple-100 text-purple-800",
  manager: "bg-blue-100 text-blue-800",
  employee: "bg-gray-100 text-gray-800",
};

export function Users() {
  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => userApi.list().then((r) => r.data),
  });

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold">Users</h1>
        <p className="text-muted-foreground">Manage organization members and permissions</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{users?.total || 0} Team Members</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p>Loading...</p>
          ) : users?.items?.length ? (
            <div className="divide-y">
              {users.items.map((user: User) => (
                <div key={user.id} className="flex items-center justify-between py-4">
                  <div className="flex items-center gap-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                      <UsersIcon className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <p className="font-medium">{user.full_name}</p>
                      <p className="text-sm text-muted-foreground">{user.email}</p>
                    </div>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs font-medium ${roleBadge[user.role] || roleBadge.employee}`}>
                    {user.role.replace("_", " ")}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground">No users found</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
