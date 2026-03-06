/**
 * Discord → NormalizedMessage normalizer.
 *
 * Maps Discord messages to the canonical FloxBot message schema.
 */

import { ChannelType, Message } from "discord.js";

export interface NormalizedMessage {
  message_id: string;
  user_identity: {
    channel: "discord";
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
      guild_id?: string;
      thread_id?: string;
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
  const clean = text.replace(/```(?:\w+)?\n?([\s\S]*?)```/g, (_match, code) => {
    blocks.push(code.trim());
    return "";
  });
  return { clean: clean.trim(), blocks };
}

/**
 * Map Discord channel type to our canonical type.
 */
function getChannelType(channelType: ChannelType): string {
  switch (channelType) {
    case ChannelType.DM:
      return "dm";
    case ChannelType.GroupDM:
      return "group_dm";
    case ChannelType.GuildText:
      return "public_channel";
    case ChannelType.PublicThread:
    case ChannelType.PrivateThread:
      return "thread";
    default:
      return "public_channel";
  }
}

/**
 * Determine conversation ID from thread or channel.
 */
function getConversationId(message: Message): string {
  // Threads have a parent message reference
  if (message.channel.isThread()) {
    return `discord_thread_${message.channel.id}`;
  }
  return `discord_channel_${message.channelId}`;
}

/**
 * Normalize a Discord message to the canonical schema.
 */
export function normalizeDiscordMessage(message: Message): NormalizedMessage {
  const { clean, blocks } = extractCodeBlocks(message.content || "");

  return {
    message_id: `discord_${message.id}`,
    user_identity: {
      channel: "discord",
      channel_user_id: message.author.id,
    },
    content: {
      text: clean || message.content || "",
      attachments: message.attachments.map((a) => a.url),
      code_blocks: blocks,
    },
    context: {
      project: {
        has_flox_env: false,
        detected_skills: [],
      },
      conversation_id: getConversationId(message),
      channel_metadata: {
        channel_id: message.channelId,
        channel_type: getChannelType(message.channel.type),
        guild_id: message.guildId || undefined,
        thread_id: message.channel.isThread()
          ? message.channel.id
          : undefined,
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
