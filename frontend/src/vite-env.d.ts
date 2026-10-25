/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin or `/api` prefix. Defaults to `/api` (Vite proxy in dev). */
  readonly VITE_API_URL?: string;
  /** Identity sent as `X-User-Id`. Defaults to `default`. */
  readonly VITE_USER_ID?: string;
  /** Only needed when the backend sets `CRAG_API_KEY`. Public at build time. */
  readonly VITE_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
