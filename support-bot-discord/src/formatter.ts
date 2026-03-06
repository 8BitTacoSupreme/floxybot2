/**
 * API response → Discord embed formatter.
 *
 * Converts FloxBot API responses to rich Discord embed messages.
 */

import { EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle } from "discord.js";

export interface FormattedResponse {
  content?: string;
  embeds: EmbedBuilder[];
  components: ActionRowBuilder<ButtonBuilder>[];
}

/**
 * Format a FloxBot API response for Discord.
 */
export function formatResponse(apiResponse: any): FormattedResponse {
  const text: string = apiResponse.text || "I couldn't generate a response.";
  const embeds: EmbedBuilder[] = [];
  const components: ActionRowBuilder<ButtonBuilder>[] = [];

  // Main response embed
  const mainEmbed = new EmbedBuilder()
    .setColor(0x7c3aed) // Flox purple
    .setDescription(truncate(text, 4096));

  // Skills used as footer
  const skills: any[] = apiResponse.skills_used || [];
  if (skills.length > 0) {
    const skillNames = skills.map((s: any) => s.name).join(", ");
    const confidence = Math.round((apiResponse.confidence || 0) * 100);
    mainEmbed.setFooter({
      text: `Skills: ${skillNames} | Confidence: ${confidence}%`,
    });
  }

  embeds.push(mainEmbed);

  // Code blocks that weren't inline (as separate embeds)
  const codeBlocks: string[] = apiResponse.code_blocks || [];
  for (const code of codeBlocks) {
    if (!text.includes(code) && code.trim()) {
      const codeEmbed = new EmbedBuilder()
        .setColor(0x2f3136)
        .setDescription("```\n" + truncate(code, 4000) + "\n```");
      embeds.push(codeEmbed);
    }
  }

  // Vote buttons
  if (apiResponse.suggested_votes) {
    const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`vote_up_${apiResponse.response_id || "unknown"}`)
        .setLabel("👍 Helpful")
        .setStyle(ButtonStyle.Success),
      new ButtonBuilder()
        .setCustomId(`vote_down_${apiResponse.response_id || "unknown"}`)
        .setLabel("👎 Not helpful")
        .setStyle(ButtonStyle.Secondary)
    );
    components.push(row);
  }

  return { embeds, components };
}

/**
 * Truncate text to max length with ellipsis.
 */
function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 3) + "...";
}
