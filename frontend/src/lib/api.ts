import axios from "axios";
import { useAuthStore } from "@/stores/authStore";
import type { ChatStreamEvent } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refreshToken = useAuthStore.getState().refreshToken;
      if (refreshToken) {
        try {
          const { data } = await axios.post(`${API_BASE}/auth/refresh`, {
            refresh_token: refreshToken,
          });
          useAuthStore.getState().setTokens(data.access_token, data.refresh_token);
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return api(original);
        } catch {
          useAuthStore.getState().logout();
        }
      }
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  login: (email: string, password: string) =>
    api.post("/auth/login", { email, password }),
  register: (data: { email: string; password: string; full_name: string; organization_name?: string }) =>
    api.post("/auth/register", data),
  me: () => api.get("/auth/me"),
  logout: () => api.post("/auth/logout"),
};

export const workspaceApi = {
  list: (page = 1) => api.get("/workspaces", { params: { page } }),
  get: (id: string) => api.get(`/workspaces/${id}`),
  create: (data: { name: string; description?: string }) =>
    api.post("/workspaces", data),
  members: (id: string) => api.get(`/workspaces/${id}/members`),
  invite: (id: string, data: { email: string; role: string }) =>
    api.post(`/workspaces/${id}/members`, data),
};

export const documentApi = {
  list: (workspaceId: string, page = 1) =>
    api.get("/documents", { params: { workspace_id: workspaceId, page } }),
  upload: (workspaceId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post(`/documents/upload?workspace_id=${workspaceId}`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  delete: (id: string) => api.delete(`/documents/${id}`),
};

export const chatApi = {
  send: (data: { message: string; workspace_id: string; conversation_id?: string }) =>
    api.post("/chat", data),
  /**
   * Streaming chat over SSE. Axios cannot consume streams in the browser,
   * so this uses fetch + ReadableStream and invokes onEvent per parsed event.
   */
  stream: async (
    data: { message: string; workspace_id: string; conversation_id?: string },
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal
  ): Promise<void> => {
    const token = useAuthStore.getState().accessToken;
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
      signal,
    });
    if (!response.ok || !response.body) {
      throw new Error(`Stream failed: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by a blank line
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        for (const line of block.split("\n")) {
          if (line.startsWith("data:")) {
            try {
              onEvent(JSON.parse(line.slice(5).trim()) as ChatStreamEvent);
            } catch {
              // ignore malformed/keepalive frames
            }
          }
        }
      }
    }
  },
  conversations: (workspaceId?: string) =>
    api.get("/chat/conversations", { params: { workspace_id: workspaceId } }),
  messages: (conversationId: string) =>
    api.get(`/chat/conversations/${conversationId}/messages`),
  createConversation: (data: { workspace_id: string; title?: string }) =>
    api.post("/chat/conversations", data),
};

export const analyticsApi = {
  usage: (days = 30) => api.get("/analytics/usage", { params: { days } }),
  runEvaluation: (data: { workspace_id: string; framework: string }) =>
    api.post("/analytics/evaluation", data),
};

export const userApi = {
  list: (page = 1) => api.get("/users", { params: { page } }),
};
