import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function focusInput(node: HTMLInputElement | null): void {
  node?.focus();
}

const TOPIC_REGEX = /##\s*Topic\s*[:\n\- ]*([^\n#]+)/i;

export function resolvePostTitle(
  item?: {
    title?: string;
    extracted_knowledge?: string;
    description?: string;
  } | null,
): string {
  if (!item) return "Reel Content";

  // 1. Prioritize ## Topic extracted from extracted_knowledge
  if (item.extracted_knowledge) {
    const match = item.extracted_knowledge.match(TOPIC_REGEX);
    if (match && match[1]) {
      const topic = match[1]
        .replace(/["'*#]+/g, "")
        .replace(/\.$/, "")
        .trim();
      if (topic) return topic;
    }
  }

  // 2. If item.title is provided, clean and return
  if (item.title && item.title.trim()) {
    const cleanTitle = item.title
      .replace(/["'*#]+/g, "")
      .replace(/\.$/, "")
      .trim();
    if (cleanTitle && cleanTitle.toLowerCase() !== "reel content") {
      return cleanTitle;
    }
  }

  return "Reel Content";
}
