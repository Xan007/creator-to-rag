---
name: CreatorRAG
description: Library-scoped RAG with direct source citations and integrated video viewing.
colors:
  primary: "#3b82f6"
  neutral-bg: "#f9fafb"
  neutral-surface: "#ffffff"
  neutral-text: "#111827"
typography:
  body:
    fontFamily: "Inter, sans-serif"
    fontWeight: 400
rounded:
  md: "8px"
spacing:
  sm: "8px"
  md: "16px"
---

# Design System: CreatorRAG

## Overview

**Creative North Star: "The Clean Dashboard"**

A sleek, distraction-free environment for focus and speed. The interface refuses the cluttered grid of typical social media feeds and focuses purely on high-density information retrieval and playback. Neutral grays allow the content to stand out, while a sharp blue accent highlights interactive elements.

**Key Characteristics:**
- High legibility and contrast.
- Dense data presentation without overwhelming the user.
- Floating/integrated video playback as a first-class citizen.

## Colors

The palette is restrained, using neutrals for structure and a single accent for action.

### Primary
- **Action Blue** (#3b82f6): Used for primary actions, active states, and highlights.

### Neutral
- **Background Gray** (#f9fafb): The main application background.
- **Surface White** (#ffffff): Card and sidebar backgrounds.
- **Text Dark** (#111827): Primary text color for high legibility.

## Typography

**Body Font:** Inter, sans-serif (with system fallbacks)

**Character:** Clean, legible, and unopinionated.

### Hierarchy
- **Body** (400, 15px): Used for chat messages and general UI text.
- **Label** (500, 14px): Used for navigation items and metadata.

## Layout

A fluid 3-column layout (sidebar, chat, video viewer) that maximizes horizontal space on desktop. The video viewer sits alongside the chat for continuous context.

## Elevation & Depth

Surfaces are mostly flat with subtle borders (1px solid gray-200) to separate regions. Soft shadows are used sparingly to elevate floating UI elements like the chat input.

## Shapes

Soft, rounded corners (8px / rounded-lg) on interactive elements to feel approachable, but sharp borders on major structural sections (sidebars).

## Components

### Buttons
- **Shape:** Rounded-lg (8px).
- **Primary:** Action Blue background with white text.
- **Secondary:** Gray-50 background for subtle actions.

### Navigation
- **Style:** Clean text with left-aligned Lucide icons.
- **Active State:** Light gray background with Action Blue icon.

## Do's and Don'ts

### Do:
- **Do** keep the interface monochromatic, relying on the Action Blue for interactive elements.
- **Do** show the video timeline context directly in the UI.

### Don't:
- **Don't** add unnecessary borders or cards inside the chat stream. Keep it flowing.
