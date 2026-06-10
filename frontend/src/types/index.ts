export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  organization_id: string | null;
  avatar_url: string | null;
}

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  organization_id: string;
  created_by: string;
  chunking_strategy: string;
  created_at: string;
  updated_at: string;
  member_count: number;
  document_count: number;
}

export interface Document {
  id: string;
  workspace_id: string;
  owner_id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  status: string;
  page_count: number | null;
  chunk_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  document_id: string;
  file_name: string;
  page_number: number | null;
  chunk_index: number;
  content_snippet: string;
  relevance_score: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: Citation[] | null;
  model: string | null;
  latency_ms: number | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  user_id: string;
  workspace_id: string;
  title: string;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AnalyticsSummary {
  total_queries: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_latency_ms: number;
  avg_retrieval_ms: number;
}
