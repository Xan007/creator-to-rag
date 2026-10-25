import { resolvePostTitle } from './utils';
import type { ContentItem } from '../components/ui/ContentTable';

const TOKEN_RE = /(?:(\w+):(?:"([^"]+)"|([^\s]+))|@([a-zA-Z0-9_.-]+)|-(\w+):(?:"([^"]+)"|([^\s]+))|-"([^"]+)"|-([^\s]+)|"([^"]+)"|([^\s]+))/g;

export interface ParsedSearchQuery {
  authors: string[];
  excludeAuthors: string[];
  titles: string[];
  captions: string[];
  knowledge: string[];
  positiveTerms: string[];
  negativeTerms: string[];
  isLinked?: boolean;
  hasKnowledge?: boolean;
  contentType?: string;
  afterTimestamp?: number;
  beforeTimestamp?: number;
}

export function parseSearchQuery(rawQuery: string): ParsedSearchQuery {
  const pq: ParsedSearchQuery = {
    authors: [],
    excludeAuthors: [],
    titles: [],
    captions: [],
    knowledge: [],
    positiveTerms: [],
    negativeTerms: [],
  };

  if (!rawQuery || !rawQuery.trim()) {
    return pq;
  }

  let match: RegExpExecArray | null;
  while ((match = TOKEN_RE.exec(rawQuery)) !== null) {
    const [
      ,
      k, vQuoted, vRaw,
      atUser,
      negK, negVq, negVraw,
      negPhrase,
      negWord,
      quotedPhrase,
      word,
    ] = match;

    // 1. key:value or key:"quoted value"
    if (k) {
      const val = (vQuoted || vRaw || '').trim().toLowerCase();
      const keyLower = k.toLowerCase();
      if (['author', 'creator', 'from', 'user'].includes(keyLower)) {
        pq.authors.push(val.replace(/^@/, ''));
      } else if (['title', 'topic'].includes(keyLower)) {
        pq.titles.push(val);
      } else if (['caption', 'desc', 'description'].includes(keyLower)) {
        pq.captions.push(val);
      } else if (['knowledge', 'content', 'ai', 'transcript'].includes(keyLower)) {
        pq.knowledge.push(val);
      } else if (keyLower === 'type') {
        pq.contentType = val;
      } else if (keyLower === 'is') {
        if (val === 'linked') pq.isLinked = true;
        if (val === 'unlinked') pq.isLinked = false;
      } else if (keyLower === 'has') {
        if (['knowledge', 'ai', 'transcript'].includes(val)) pq.hasKnowledge = true;
      } else if (['after', 'since'].includes(keyLower)) {
        const d = new Date(val).getTime();
        if (!isNaN(d)) pq.afterTimestamp = d / 1000;
      } else if (['before', 'until'].includes(keyLower)) {
        const d = new Date(val).getTime();
        if (!isNaN(d)) pq.beforeTimestamp = d / 1000;
      }
      continue;
    }

    // 2. @username
    if (atUser) {
      pq.authors.push(atUser.toLowerCase());
      continue;
    }

    // 3. -key:value
    if (negK) {
      const negVal = (negVq || negVraw || '').trim().toLowerCase();
      if (['author', 'creator', 'from', 'user'].includes(negK.toLowerCase())) {
        pq.excludeAuthors.push(negVal.replace(/^@/, ''));
      }
      continue;
    }

    // 4. -phrase / -word
    if (negPhrase || negWord) {
      const neg = (negPhrase || negWord || '').trim().toLowerCase();
      if (neg) pq.negativeTerms.push(neg);
      continue;
    }

    // 5. "exact phrase"
    if (quotedPhrase) {
      const qp = quotedPhrase.trim().toLowerCase();
      if (qp) pq.positiveTerms.push(qp);
      continue;
    }

    // 6. word
    if (word) {
      const w = word.trim().toLowerCase();
      if (w) pq.positiveTerms.push(w);
      continue;
    }
  }

  return pq;
}

export function matchesSearchQuery(item: ContentItem, rawQuery: string): boolean {
  if (!rawQuery || !rawQuery.trim()) {
    return true;
  }

  const pq = parseSearchQuery(rawQuery);
  const author = (item.creator || '').toLowerCase();
  const title = resolvePostTitle(item).toLowerCase();
  const caption = (item.description || '').toLowerCase();
  const knowledge = (item.extracted_knowledge || '').toLowerCase();
  const type = (item.type || '').toLowerCase();
  const url = (item.url || '').toLowerCase();

  // 1. Author filters
  for (const a of pq.authors) {
    if (!author.includes(a)) return false;
  }
  for (const ea of pq.excludeAuthors) {
    if (author.includes(ea)) return false;
  }

  // 2. Specific field filters
  for (const t of pq.titles) {
    if (!title.includes(t)) return false;
  }
  for (const c of pq.captions) {
    if (!caption.includes(c)) return false;
  }
  for (const k of pq.knowledge) {
    if (!knowledge.includes(k)) return false;
  }

  // 3. Type
  if (pq.contentType && !type.includes(pq.contentType)) {
    return false;
  }

  // 4. Linked / Unlinked
  if (pq.isLinked === true && (!item.library_id || item.library_id === '')) {
    return false;
  }
  if (pq.isLinked === false && item.library_id && item.library_id !== '') {
    return false;
  }

  // 5. Has Knowledge
  if (pq.hasKnowledge === true && (!item.extracted_knowledge || item.extracted_knowledge.trim().length === 0)) {
    return false;
  }

  // 6. Dates
  const itemDate = item.published_at || item.indexed_at;
  if (pq.afterTimestamp && (!itemDate || itemDate < pq.afterTimestamp)) {
    return false;
  }
  if (pq.beforeTimestamp && (!itemDate || itemDate > pq.beforeTimestamp)) {
    return false;
  }

  // 7. Negative terms (cannot appear in title, caption, knowledge, or author)
  for (const term of pq.negativeTerms) {
    if (
      title.includes(term) ||
      caption.includes(term) ||
      knowledge.includes(term) ||
      author.includes(term)
    ) {
      return false;
    }
  }

  // 8. Positive terms (must appear somewhere in title, caption, knowledge, author, or url)
  for (const term of pq.positiveTerms) {
    const found =
      title.includes(term) ||
      caption.includes(term) ||
      knowledge.includes(term) ||
      author.includes(term) ||
      url.includes(term);
    if (!found) return false;
  }

  return true;
}

