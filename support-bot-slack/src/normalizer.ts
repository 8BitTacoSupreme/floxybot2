/**
 * Slack → NormalizedMessage normalizer.
 *
 * Maps Slack events to the canonical FloxBot message schema.
 */

export interface NormalizedMessage {
  message_id: string;
  user_identity: {
    channel: "slack";
    channel_user_id: string;
    email?: string;
    canonical_user_id?: string;
    floxhub_username?: string;
    entitlement_tier?: string;
  };
  content: {
    text: string;
    attachments: string[];
    code_blocks: string[];
  };
  context: {
    project: {
      has_flox_env: boolean;
      manifest?: string;
      detected_skills: string[];
    };
    conversation_id: string;
    channel_metadata: {
      channel_id: string;
      channel_type: string;
      thread_ts?: string;
    };
  };
  session: {
    prior_messages: number;
    active_skills: string[];
    escalation_attempts: number;
    copilot_active: boolean;
  };
}

/**
 * Extract code blocks from message text.
 */
function extractCodeBlocks(text: string): { clean: string; blocks: string[] } {
  const blocks: string[] = [];
  const clean = text.replace(/```([\s\S]*?)```/g, (_match, code) => {
    blocks.push(code.trim());
    return "";
  });
  return { clean: clean.trim(), blocks };
}

/**
 * Generate a unique message ID from Slack event data.
 */
function makeMessageId(event: any): string {
  const ts = event.ts || event.event_ts || Date.now().toString();
  const channel = event.channel || "unknown";
  return `slack_${channel}_${ts}`;
}

/**
 * Determine conversation ID from thread or channel.
 */
function getConversationId(event: any): string {
  // If in a thread, use thread_ts as conversation anchor
  if (event.thread_ts) {
    return `slack_thread_${event.channel}_${event.thread_ts}`;
  }
  // Otherwise use channel + a window-based ID
  return `slack_channel_${event.channel}`;
}

/**
 * Determine channel type from Slack event.
 */
function getChannelType(event: any): string {
  if (event.channel_type === "im") return "dm";
  if (event.channel_type === "mpim") return "group_dm";
  if (event.channel_type === "group") return "private_channel";
  return "public_channel";
}

/**
 * Normalize a Slack message event to the canonical schema.
 */
export function normalizeSlackMessage(event: any): NormalizedMessage {
  const { clean, blocks } = extractCodeBlocks(event.text || "");

  return {
    message_id: makeMessageId(event),
    user_identity: {
      channel: "slack",
      channel_user_id: event.user || "unknown",
    },
    content: {
      text: clean || event.text || "",
      attachments: (event.files || []).map((f: any) => f.url_private || f.permalink || ""),
      code_blocks: blocks,
    },
    context: {
      project: {
        has_flox_env: false,
        detected_skills: [],
      },
      conversation_id: getConversationId(event),
      channel_metadata: {
        channel_id: event.channel || "",
        channel_type: getChannelType(event),
        thread_ts: event.thread_ts,
      },
    },
    session: {
      prior_messages: 0,
      active_skills: [],
      escalation_attempts: 0,
      copilot_active: false,
    },
  };
}
