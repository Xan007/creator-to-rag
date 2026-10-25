export interface Library {
  id: string;
  name: string;
  slug: string;
  description: string;
  owner_id: string;
  created_at: number;
}

export interface LibraryIn {
  name: string;
  description?: string;
}

export interface ChatTurn {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceInfo[];
}

export interface QueryIn {
  question: string;
  query?: string;
  library?: string;
  library_id?: string;
  creator?: string;
  mode?: string;
  history?: ChatTurn[];
  top_k?: number;
  min_score?: number;
}

export interface SourceInfo {
  creator?: string;
  creator_username?: string;
  author?: string;
  url: string;
  score?: number;
  cited: boolean;
  source_index?: number;
  title?: string;
  summary?: string;
  platform?: string;
  source_id?: string;
  id?: string;
  knowledge?: string;
  caption?: string;
}

export interface QueryResponse {
  answer: string;
  sources: SourceInfo[];
  mode: string;
  standalone_question?: string;
  timings_ms?: Record<string, number>;
}

export interface GlobalPost {
  id: string;
  url: string;
  creator?: string;
  creator_username?: string;
  type?: string;
  title?: string;
  description?: string;
  extracted_knowledge?: string;
  published_at?: number | null;
  indexed_at?: number;
  library_id?: string | null;
  source_id?: string | null;
  score?: number;
}

export interface PaginatedPosts {
  items: GlobalPost[];
  total: number;
  page: number;
  page_size: number;
  search_mode?: 'keyword' | 'semantic';
}

export interface SourceItem {
  id: string;
  library_id?: string;
  platform?: string;
  content_type?: string;
  url: string;
  author?: string;
  title?: string;
  description?: string;
  status?: string;
  ingest_status?: string;
  published_at?: number | null;
  indexed_at?: number | null;
}

export interface BulkDeleteResponse {
  status: string;
  removed?: number;
  not_found?: string[];
}

export interface ChatSession {
  id: string;
  libraryId: string;
  title: string;
  history: ChatTurn[];
  isCustomTitle?: boolean;
}

export interface LibraryDetails extends Library {
  posts?: GlobalPost[];
  sources?: SourceItem[];
  profiles?: ProfileInfo[];
}

export interface ProfileInfo {
  username: string;
  interests?: string;
  max_posts?: number;
  analysis_mode?: string;
  audio_only?: boolean;
  processed_count?: number;
  total_posts_scraped?: number;
  total_posts?: number;
  failed_ids?: string[];
}

export interface CookiesStatus {
  exists: boolean;
  size_bytes: number;
}

export interface JobInfo {
  id: string;
  kind: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | string;
  created_at?: number;
  started_at?: number | null;
  finished_at?: number | null;
  duration_s?: number | null;
  result?: unknown;
  error?: string | null;
  log?: string[] | null;
}

