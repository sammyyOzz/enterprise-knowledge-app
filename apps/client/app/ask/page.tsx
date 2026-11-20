"use client";

import { Chat } from "@/components/chat/Chat";
import { useRequiredWorkspace } from "@/lib/workspace";

export default function AskPage() {
  const workspaceId = useRequiredWorkspace();
  // `key` resets all chat state if the workspace is changed.
  return <Chat key={workspaceId} workspaceId={workspaceId} />;
}