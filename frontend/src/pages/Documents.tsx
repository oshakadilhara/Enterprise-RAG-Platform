import { useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, FileText, Trash2, CheckCircle, Clock, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { documentApi, workspaceApi } from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import type { Document } from "@/types";

const statusIcon = {
  completed: <CheckCircle className="h-4 w-4 text-green-500" />,
  processing: <Clock className="h-4 w-4 text-yellow-500" />,
  pending: <Clock className="h-4 w-4 text-gray-400" />,
  failed: <AlertCircle className="h-4 w-4 text-red-500" />,
};

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function Documents() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const currentWorkspace = useAppStore((s) => s.currentWorkspace);

  const { data: workspaces } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => workspaceApi.list().then((r) => r.data),
  });

  const workspaceId = currentWorkspace?.id || workspaces?.items?.[0]?.id;

  const { data: documents, isLoading } = useQuery({
    queryKey: ["documents", workspaceId],
    queryFn: () => documentApi.list(workspaceId!).then((r) => r.data),
    enabled: !!workspaceId,
    refetchInterval: 5000,
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => documentApi.upload(workspaceId!, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => documentApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadMutation.mutate(file);
    e.target.value = "";
  };

  return (
    <div className="p-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Documents</h1>
          <p className="text-muted-foreground">Upload and manage knowledge base documents</p>
        </div>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.csv"
            className="hidden"
            onChange={handleUpload}
          />
          <Button onClick={() => fileInputRef.current?.click()} disabled={!workspaceId || uploadMutation.isPending}>
            <Upload className="mr-2 h-4 w-4" />
            {uploadMutation.isPending ? "Uploading..." : "Upload Document"}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>
            {documents?.total || 0} Documents
            {workspaceId && workspaces?.items && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                in {workspaces.items.find((w: { id: string }) => w.id === workspaceId)?.name}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-muted-foreground">Loading...</p>
          ) : documents?.items?.length ? (
            <div className="divide-y">
              {documents.items.map((doc: Document) => (
                <div key={doc.id} className="flex items-center justify-between py-4">
                  <div className="flex items-center gap-4">
                    <FileText className="h-8 w-8 text-primary" />
                    <div>
                      <p className="font-medium">{doc.file_name}</p>
                      <p className="text-sm text-muted-foreground">
                        {doc.file_type.toUpperCase()} · {formatSize(doc.file_size)} · {doc.chunk_count} chunks
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1 text-sm">
                      {statusIcon[doc.status as keyof typeof statusIcon]}
                      <span className="capitalize">{doc.status}</span>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => deleteMutation.mutate(doc.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-12 text-center">
              <FileText className="mx-auto h-12 w-12 text-muted-foreground" />
              <p className="mt-4 text-muted-foreground">No documents uploaded yet</p>
              <p className="text-sm text-muted-foreground">Supports PDF, DOCX, TXT, and CSV files</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
