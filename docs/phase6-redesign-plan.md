# Phase 6 Frontend Redesign Plan

## Current Issues

1. Overall layout feels uncomfortable and does not provide a modern chat experience.
2. The right-side panel is not being used effectively.
3. File upload is separated from the chat workflow.
4. The interface does not resemble modern AI chat applications such as ChatGPT.

---

## Current Architecture (Before Redesign)

```
App.tsx
├── DocumentSidebar.tsx   ← document list + drag-drop upload zone combined
└── ChatWindow.tsx        ← monolithic: header + messages + input bar
    ├── MessageBubble.tsx
    │   └── CitationCard.tsx
    └── UploadDropzone.tsx
```

**What can be reused as-is:**
- `CitationCard.tsx`
- `MessageBubble.tsx`
- `StatusBadge.tsx`
- `useDocuments.ts`
- `api/client.ts`
- `types/index.ts` (extend, not replace)

---

## New Layout

```
┌────────────────────────────────────────────────────────────────────┐
│  [≡]  Industrial Document Intelligence                    [avatar] │  ← Topbar (mobile only)
├──────────────┬─────────────────────────────────────────────────────┤
│              │                                                     │
│  LEFT        │           MAIN CHAT AREA                           │
│  SIDEBAR     │                                                     │
│  (260px)     │   ┌─────────────────────────────────────────────┐  │
│              │   │          empty state / messages             │  │
│  [+ New Chat]│   │                                             │  │
│  ─────────── │   │  [user bubble]                   ────────►  │  │
│  Today       │   │                                             │  │
│  · Chat 1    │   │  ◄──── [assistant bubble + citations]       │  │
│  · Chat 2    │   │                                             │  │
│  ─────────── │   └─────────────────────────────────────────────┘  │
│  Yesterday   │                                                     │
│  · Chat 3    │   ┌─────────────────────────────────────────────┐  │
│              │   │ [+]  Ask about your documents...        [▶] │  │
│  ─────────── │   └─────────────────────────────────────────────┘  │
│  [Settings]  │                                                     │
│  [Account]   │                                                     │
└──────────────┴─────────────────────────────────────────────────────┘
```

On mobile: sidebar collapses to an off-canvas drawer, topbar shows hamburger icon.

---

## New Component Hierarchy

```
App.tsx
├── Sidebar.tsx                        ← NEW: replaces DocumentSidebar
│   ├── NewChatButton.tsx              ← NEW
│   ├── ChatHistoryList.tsx            ← NEW
│   │   └── ChatHistoryItem.tsx        ← NEW (with rename/delete context menu)
│   ├── SidebarDocumentSection.tsx     ← NEW: compact doc list (no upload zone)
│   └── SidebarFooter.tsx             ← NEW: Settings + Account links
│
├── MainArea.tsx                       ← NEW: layout wrapper
│   ├── ChatWindow.tsx                 ← REFACTORED: messages only
│   │   └── MessageBubble.tsx          ← KEEP AS-IS
│   │       └── CitationCard.tsx       ← KEEP AS-IS
│   └── ChatInputBar.tsx               ← NEW: extracted + enhanced
│       └── UploadPopover.tsx          ← NEW: replaces UploadDropzone
│
└── SettingsPanel.tsx                  ← NEW: slide-in overlay
    ├── ModelSettings.tsx              ← NEW
    ├── RetrievalSettings.tsx          ← NEW
    └── ThemeSettings.tsx             ← NEW
```

---

## Detailed Component Specifications

### `Sidebar.tsx`

```
Layout: fixed left, full height, 260px wide
Background: dark sidebar (gray-900), similar to ChatGPT
Collapsible: slides off-screen on mobile, toggle via hamburger

Sections (top to bottom):
  1. Logo/title area (top)
  2. [+ New Chat] button — primary CTA
  3. Scrollable chat history list grouped by: Today / Yesterday / Last 7 Days / Older
  4. Divider
  5. Documents section (collapsed by default, expandable) — compact doc list
  6. Footer: [Settings icon] [Account/Avatar]
```

### `ChatHistoryItem.tsx`

```
Default state: conversation title (first user message, max 30 chars) + time ago
Hover state: reveals [rename icon] [delete icon] on right
Right-click / long-press: context menu with Rename, Delete
Rename: inline text input replaces title, confirm on Enter
Active state: highlighted background
```

### `ChatHistoryList.tsx`

```
Data source: localStorage key 'chat_sessions'
Session schema:
  {
    id: string (uuid)
    title: string
    createdAt: ISO string
    updatedAt: ISO string
    messages: ChatMessage[]
    documentId?: string   ← which doc was active
  }
Groups: Today / Yesterday / Last 7 Days / Older
Search: text input at top filters by title
Empty state: "No conversations yet"
```

### `ChatInputBar.tsx`

```
Layout: fixed bottom of main area, full width, max-w-3xl centered
Structure:
  ┌──────────────────────────────────────────────────────┐
  │ [+]  textarea (auto-height, max 200px)          [▶]  │
  └──────────────────────────────────────────────────────┘

[+] button behavior:
  - Opens UploadPopover above the input
  - Popover has: "Upload Document" option (shows file picker)
  - Accepted: .pdf, .docx, .txt
  - After file selected: upload starts, progress chip appears above input bar
  - Progress chip: filename + spinner → filename + "Ready" (green) → auto-dismisses after 3s
  - On success: document auto-selected as active context

Upload chip (above input, while uploading):
  ┌──────────────────────────────────────┐
  │ 📄 document.pdf   [████░░░░] 60%  ✕ │
  └──────────────────────────────────────┘

Textarea:
  - Placeholder: "Ask about your documents..."
  - Enter to send, Shift+Enter for newline
  - Disabled if no document is ready

[▶] send button:
  - Indigo background
  - Disabled + grayed when input empty or no doc ready
```

### `UploadPopover.tsx`

```
Triggered by [+] button
Small popover above input, auto-closes on outside click
Options:
  ┌─────────────────────┐
  │ 📄  Upload Document  │
  └─────────────────────┘
File input hidden, triggered by clicking the option
No drag-drop in popover (drag-drop still works by dropping onto main area)
```

### `ChatWindow.tsx` (refactored — messages only)

```
Remove: input bar (moved to ChatInputBar)
Remove: header with document name
Keep: scrollable message list
Keep: auto-scroll to bottom behavior
Keep: empty state (update copy and icon)
Add: welcome screen when no session active:
  "Upload a document and start asking questions."
  [Upload a Document] button (triggers same flow as [+])
```

### `SettingsPanel.tsx`

```
Trigger: Settings icon in sidebar footer
Display: slides in from left as a full-height panel (no routing needed)

Sections:
  1. Model Settings
     - LLM model name (read-only, from backend config)
     - Embedding model name (read-only)
     - Backend status indicator (ping /health)

  2. Retrieval Settings
     - Top-K slider: 1–10 (default 5)
     - Similarity threshold slider: 0.0–1.0 (default 0.3)
     - Stored in localStorage, read by useChat on each query

  3. Appearance
     - Light / Dark / System theme toggle
     - Theme stored in localStorage, applied via CSS class on <html>

  4. About / System Info
     - App version
     - Backend URL
     - GitHub link
```

---

## State Management Changes

### `useChat.ts` — extend for session persistence

```
Current: useState([]) — ephemeral messages array
New:
  - sessions: ChatSession[] from localStorage
  - activeSessionId: string | null
  - loadSession(id) → restores messages from localStorage
  - createSession() → new uuid, empty messages, push to localStorage
  - updateSession() → debounced write to localStorage on each new message
  - deleteSession(id)
  - renameSession(id, title)
  - searchSessions(query)
```

### New `useSettings.ts` hook

```
Reads/writes localStorage key 'app_settings'
Exposes: topK, threshold, theme, setTopK, setThreshold, setTheme
Used by: ChatInputBar (query params), SettingsPanel (form controls)
```

### New `useTheme.ts` hook

```
Reads theme from useSettings
Applies 'dark' class to document.documentElement
Detects system preference if theme = 'system'
```

---

## Theme System

```
Light mode (default):
  Sidebar: white with gray-100 border
  Chat bg: white
  Input bar: white with shadow

Dark mode:
  Sidebar: gray-950
  Chat bg: gray-900
  Input bar: gray-800
  Text: gray-100
```

Implemented via Tailwind's `dark:` variant classes + `class="dark"` on `<html>`.

---

## Mobile Responsiveness

| Breakpoint | Behavior |
|---|---|
| `lg` (1024px+) | Full layout visible |
| `md` (768–1023px) | Sidebar collapses to icon strip (48px wide) |
| `sm` (below 768px) | Sidebar hidden, hamburger topbar, drawer overlay |

Sidebar toggle state stored in `useState` in `App.tsx`.

---

## Files Summary

| Status | File | Action |
|---|---|---|
| Modify | `App.tsx` | 3-area layout, sidebar state, theme class |
| Modify | `ChatWindow.tsx` | Remove input + header, add welcome state |
| Modify | `useChat.ts` | Add session persistence |
| Modify | `types/index.ts` | Add `ChatSession`, `AppSettings` |
| Delete | `DocumentSidebar.tsx` | Replaced by `Sidebar.tsx` |
| Delete | `UploadDropzone.tsx` | Replaced by `UploadPopover.tsx` |
| Create | `Sidebar.tsx` | Main sidebar shell |
| Create | `ChatHistoryList.tsx` | Session list grouped by date |
| Create | `ChatHistoryItem.tsx` | Single session row with actions |
| Create | `SidebarFooter.tsx` | Settings + Account links at bottom |
| Create | `ChatInputBar.tsx` | Input + `+` button + send button |
| Create | `UploadPopover.tsx` | File upload popover from `+` |
| Create | `SettingsPanel.tsx` | Slide-in settings overlay |
| Create | `ModelSettings.tsx` | Model info sub-section |
| Create | `RetrievalSettings.tsx` | Top-K + threshold sliders |
| Create | `ThemeSettings.tsx` | Light/dark/system toggle |
| Create | `useSettings.ts` | Settings hook with localStorage |
| Create | `useTheme.ts` | Theme application hook |

---

## Implementation Roadmap

### Step 1 — Foundation (non-breaking)
- Add `useSettings.ts` hook
- Add `useTheme.ts` hook
- Extend `useChat.ts` with localStorage session persistence
- Extend `types/index.ts` with `ChatSession` and `AppSettings` types

### Step 2 — New Sidebar
- Build `Sidebar.tsx` shell with dark background
- Build `ChatHistoryList.tsx` + `ChatHistoryItem.tsx` (read from localStorage)
- Build `SidebarFooter.tsx` with Settings + Account icons
- Wire `NewChatButton` to create a new session in `useChat`
- Replace `DocumentSidebar.tsx` with `Sidebar.tsx` in `App.tsx`

### Step 3 — Chat Input Overhaul
- Extract `ChatInputBar.tsx` from `ChatWindow.tsx`
- Build `UploadPopover.tsx` with file picker
- Add upload progress chip above input bar
- Wire upload → auto-select document → enable chat
- Remove `UploadDropzone.tsx`

### Step 4 — ChatWindow Cleanup
- Strip input bar and document header from `ChatWindow.tsx`
- Add welcome screen empty state
- Ensure scroll behavior still works with new layout

### Step 5 — Settings Panel
- Build `SettingsPanel.tsx` as a slide-in overlay
- `ModelSettings.tsx`, `RetrievalSettings.tsx`, `ThemeSettings.tsx` sub-sections
- Wire `useSettings` to sliders and toggles
- Connect settings to chat queries (topK, threshold)

### Step 6 — Theme System
- Apply `dark:` classes across all components
- Wire `useTheme` to apply class to `<html>`
- Test light/dark/system modes

### Step 7 — Mobile Responsiveness
- Add hamburger topbar for mobile
- Implement sidebar drawer with overlay backdrop
- Test all breakpoints
- Fix any overflow/scroll issues

### Step 8 — Polish
- Smooth sidebar slide animation
- Transition on theme change
- Keyboard shortcut: `Cmd/Ctrl + Shift + O` for new chat
- `Cmd/Ctrl + B` to toggle sidebar (ChatGPT convention)
- Tooltip on sidebar icon-only mode
