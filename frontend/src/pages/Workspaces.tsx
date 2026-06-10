import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, FolderOpen, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { workspaceApi } from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import type { Workspace } from "@/types";

export function Workspaces() {
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const queryClient = useQueryClient();
  const setCurrentWorkspace = useAppStore((s) => s.setCurrentWorkspace);

  const { data: workspaces, isLoading } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => workspaceApi.list().then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: () => workspaceApi.create({ name, description }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      setShowCreate(false);
      setName("");
      setDescription("");
    },
  });

  return (
    <div className="p-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Workspaces</h1>
          <p className="text-muted-foreground">Organize documents and team access</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Workspace
        </Button>
      </div>

      {showCreate && (
        <Card className="mb-6">
          <CardContent className="pt-6 space-y-4">
            <Input placeholder="Workspace name" value={name} onChange={(e) => setName(e.target.value)} />
            <Input placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
            <div className="flex gap-2">
              <Button onClick={() => createMutation.mutate()} disabled={!name || createMutation.isPending}>
                Create
              </Button>
              <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <p>Loading...</p>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {workspaces?.items?.map((ws: Workspace) => (
            <Card
              key={ws.id}
              className="cursor-pointer hover:shadow-md transition-shadow"
              onClick={() => setCurrentWorkspace(ws)}
            >
              <CardHeader>
                <div className="flex items-center gap-3">
                  <FolderOpen className="h-8 w-8 text-primary" />
                  <div>
                    <CardTitle className="text-lg">{ws.name}</CardTitle>
                    <p className="text-sm text-muted-foreground">{ws.description || "No description"}</p>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex gap-4 text-sm text-muted-foreground">
                  <span>{ws.document_count} documents</span>
                  <span className="flex items-center gap-1">
                    <Users className="h-3 w-3" />
                    {ws.member_count} members
                  </span>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  Chunking: {ws.chunking_strategy}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
