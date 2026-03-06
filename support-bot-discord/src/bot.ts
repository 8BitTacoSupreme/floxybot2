/**
 * FloxBot Discord Adapter — discord.js with Gateway WebSocket.
 *
 * Thin, stateless adapter that normalizes Discord messages to the canonical
 * FloxBot message schema and forwards to the Central API.
 */

import {
  Client,
  Events,
  GatewayIntentBits,
  ChannelType,
  Message,
  Interaction,
} from "discord.js";
import axios from "axios";
import { normalizeDiscordMessage } from "./normalizer";
import { formatResponse } from "./formatter";

const CENTRAL_API_URL = process.env.FLOXBOT_API_URL || "http://localhost:8000";

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.DirectMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.GuildMessageReactions,
  ],
});

/**
 * Handle incoming messages.
 */
client.on(Events.MessageCreate, async (message: Message) => {
  // Ignore bot messages
  if (message.author.bot) return;

  // In guilds, only respond to mentions or DMs
  const isDM = message.channel.type === ChannelType.DM;
  const isMention =
    client.user && message.mentions.has(client.user);

  if (!isDM && !isMention) return;

  // Strip bot mention from text
  let text = message.content;
  if (client.user) {
    text = text.replace(new RegExp(`<@!?${client.user.id}>`, "g"), "").trim();
  }

  const normalized = normalizeDiscordMessage(message);
  // Use cleaned text
  normalized.content.text = text || message.content;

  try {
    const response = await axios.post(
      `${CENTRAL_API_URL}/v1/message`,
      normalized,
      { timeout: 30000 }
    );

    const formatted = formatResponse(response.data);

    await message.reply({
      embeds: formatted.embeds,
      components: formatted.components,
    });
  } catch (error: any) {
    console.error("API call failed:", error.message);
    await message.reply(
      "Sorry, I'm having trouble processing your request. Please try again."
    );
  }
});

/**
 * Handle vote button interactions.
 */
client.on(Events.InteractionCreate, async (interaction: Interaction) => {
  if (!interaction.isButton()) return;

  const customId = interaction.customId;
  if (!customId.startsWith("vote_")) return;

  const isUp = customId.startsWith("vote_up_");
  const responseId = customId.replace(/^vote_(up|down)_/, "");
  const vote = isUp ? "up" : "down";

  try {
    await axios.post(`${CENTRAL_API_URL}/v1/vote`, {
      message_id: responseId,
      conversation_id: "",
      user_id: interaction.user.id,
      vote,
    });

    await interaction.reply({
      content: `Thanks for the feedback! (${vote === "up" ? "👍" : "👎"})`,
      ephemeral: true,
    });
  } catch (error: any) {
    console.error("Vote submission failed:", error.message);
    await interaction.reply({
      content: "Failed to record vote. Please try again.",
      ephemeral: true,
    });
  }
});

/**
 * Handle reaction-based votes.
 */
client.on(Events.MessageReactionAdd, async (reaction, user) => {
  if (user.bot) return;

  const reactionMap: Record<string, string> = {
    "👍": "up",
    "👎": "down",
  };

  const emoji = reaction.emoji.name || "";
  const vote = reactionMap[emoji];
  if (!vote) return;

  // Only process reactions on bot messages
  const message = reaction.message;
  if (message.author?.id !== client.user?.id) return;

  try {
    await axios.post(`${CENTRAL_API_URL}/v1/vote`, {
      message_id: message.id,
      conversation_id: "",
      user_id: user.id,
      vote,
    });
  } catch (error: any) {
    console.error("Reaction vote failed:", error.message);
  }
});

client.once(Events.ClientReady, (readyClient) => {
  console.log(`⚡ FloxBot Discord adapter ready as ${readyClient.user.tag}`);
});

// Login
client.login(process.env.DISCORD_BOT_TOKEN);

export { client };
