# Chat upgrades — design

_2026-06-01 · branch `feat/chat-upgrades`_

Five improvements to the chat experience, in order of impact-to-effort. Approved
approach: all five, **server-side** history, **inline file text** for attachments.

## 1. Markdown + Shiki rendering

The agent emits Markdown (code blocks, lists, headers) but `chat/page.tsx`
renders it as plaintext (`whiteSpace: "pre-wrap"`). `react-markdown`,
`remark-gfm`, `rehype-raw`, and `shiki` are already in `package.json`, unused.

- New component `frontend/src/components/chat/Markdown.tsx`: `react-markdown` +
  `remark-gfm` + `rehype-raw`, with a custom `code` renderer (`CodeBlock`) that
  highlights via a cached Shiki highlighter, dark theme matched to `--ink/--paper`.
- Applied to final assistant messages (`MessageRow`) and the live streaming text
  (`AgentThinking`). The loop emits the final answer as one `text` event, so
  there is no partial-Markdown flicker concern.

## 2. Copy buttons

- Per code block: copy icon inside `CodeBlock`, copies raw code.
- Per assistant message: a small copy action that copies the raw Markdown.
- `navigator.clipboard` + transient "Copied ✓". No new deps.

## 3. Stop generation

- `AbortController` in a ref, passed to `fetch(..., { signal })`. While
  streaming the Send button becomes Stop; clicking aborts. Partial text streamed
  so far is committed as the assistant message, not discarded.
- Backend unchanged: an aborted fetch closes the SSE connection.

## 4. Server-side conversation history

**Schema.** `conversations` currently has `user_id uuid` with a real FK to
`users`. The JWT `sub` is a free string (uploads/notepad already scope by it as
`owner_id String(64)`), and the test client's `sub` ("test-user") isn't a real
user row. To match the existing pattern and avoid FK/uuid friction, migration
`0007` **drops the unused `user_id` FK column** (no conversations are persisted
today, so no data loss) and **adds `owner_id String(64)` indexed**. The model
mirrors `Upload`.

**Service** `app/services/agent/conversations_service.py`:
- `get_or_create(db, owner, conversation_id, first_message) -> Conversation` —
  ownership-checked; a missing/foreign id starts a new conversation. Title =
  first message, truncated.
- `save_message(db, conversation_id, role, content) -> Message`.
- `list_conversations(db, owner)`, `get_conversation(db, owner, id)` (404 if not
  owned), `delete_conversation(db, owner, id)`.

**Router** `app/api/conversations.py` (registered with `_auth`):
- `GET /api/conversations` — list (id, title, created_at) for the caller.
- `GET /api/conversations/{id}` — `{id, title, messages: [{role, content, created_at}]}`.
- `DELETE /api/conversations/{id}`.

**Chat endpoint** (`/api/agent/chat`): add `Depends(require_user)`. Resolve/
create the conversation, persist the **original** user message, stream a new
`{type:"conversation", id}` event first, accumulate the `text` event(s), and
persist the assistant message after the loop.

**Scope note (explicit):** only user + assistant **text** is persisted. Tool-call
rows and `sources` are ephemeral and do not reload on an old thread (the
`messages` table has no column for them). Live chat is unchanged.

**Frontend:** left rail gains a conversation list (load on click, "New
conversation" = null id). Track `conversationId`; send it each request; adopt the
id from the `conversation` event. Replaces the single-blob `localStorage`.

## 5. Attach uploaded file (inline text)

- Frontend: paperclip opens a picker of the user's uploads (`GET /api/uploads`);
  selecting shows a chip above the input and includes `upload_id` in the request.
- Backend helper `app/services/agent/attachments.py`:
  `build_attached_message(db, upload_id, owner, message) -> str`. Loads the
  upload (owner-scoped), decodes UTF-8, truncates to a cap (~50 KB), prepends as
  context:
  ```
  Attached file "errors.log":
  <content…>
  ---
  <user message>
  ```
  Binary/oversized/undecodable → a short inline note instead of garbage. A
  foreign/missing `upload_id` is ignored (message sent as-is).

## Testing

- Backend (TDD): conversation service + endpoints (create-on-first-message, list,
  load, delete, **owner scoping** — A can't see B), and attachment injection
  (text prepend, truncation cap, binary rejection, owner check, missing id).
- Frontend: verified by running the app — Markdown/copy/stop render; create +
  reload + delete a thread; attach a file and confirm the agent sees it.

## Sequencing

Migration + model → conversation service + attachment helper (tests first) →
conversations router + chat endpoint wiring → frontend.
