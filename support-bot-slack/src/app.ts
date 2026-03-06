/**
 * FloxBot Slack Adapter — Bolt SDK with Socket Mode.
 *
 * Thin, stateless adapter that normalizes Slack events to the canonical
 * FloxBot message schema and forwards to the Central API.
 */

import { App } from "@slack/bolt";
import axios from "axios";
import { normalizeSlackMessage } from "./normalizer";
import { formatResponse } from "./formatter";

const CENTRAL_API_URL = process.env.FLOXBOT_API_URL || "http://localhost:8000";

const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  appToken: process.env.SLACK_APP_TOKEN,
  socketMode: true,
});

/**
 * Handle direct messages and @mentions.
 */
app.message(async ({ message, say, client }) => {
  // Skip bot messages, message_changed, etc.
  if (!("text" in message) || ("bot_id" in message)) return;

  const normalized = normalizeSlackMessage(message);

  try {
    const response = await axios.post(
      `${CENTRAL_API_URL}/v1/message`,
      normalized,
      { timeout: 30000 }
    );

    const formatted = formatResponse(
      response.data,
      (message as any).thread_ts || (message as any).ts
    );

    await say({
      text: formatted.text,
      blocks: formatted.blocks,
      thread_ts: formatted.thread_ts,
    });
  } catch (error: any) {
    console.error("API call failed:", error.message);
    await say({
      text: "Sorry, I'm having trouble processing your request. Please try again.",
      thread_ts: (message as any).thread_ts || (message as any).ts,
    });
  }
});

/**
 * Handle @FloxBot mentions in channels.
 */
app.event("app_mention", async ({ event, say }) => {
  // Strip the bot mention from text
  const text = event.text.replace(/<@[A-Z0-9]+>/g, "").trim();
  const mentionEvent = { ...event, text };

  const normalized = normalizeSlackMessage(mentionEvent);

  try {
    const response = await axios.post(
      `${CENTRAL_API_URL}/v1/message`,
      normalized,
      { timeout: 30000 }
    );

    const formatted = formatResponse(response.data, event.ts);

    await say({
      text: formatted.text,
      blocks: formatted.blocks,
      thread_ts: event.ts,
    });
  } catch (error: any) {
    console.error("API call failed:", error.message);
    await say({
      text: "Sorry, I'm having trouble right now. Please try again.",
      thread_ts: event.ts,
    });
  }
});

/**
 * Handle vote button clicks.
 */
app.action(/^vote_(up|down)$/, async ({ action, ack, body }) => {
  await ack();

  const vote = (action as any).action_id === "vote_up" ? "up" : "down";
  const responseId = (action as any).value;
  const userId = (body as any).user?.id || "unknown";

  try {
    await axios.post(`${CENTRAL_API_URL}/v1/vote`, {
      message_id: responseId,
      conversation_id: "",
      user_id: userId,
      vote,
    });
  } catch (error: any) {
    console.error("Vote submission failed:", error.message);
  }
});

/**
 * Handle reaction_added events (thumbsup/thumbsdown as votes).
 */
app.event("reaction_added", async ({ event }) => {
  const reactionMap: Record<string, string> = {
    "+1": "up",
    thumbsup: "up",
    "-1": "down",
    thumbsdown: "down",
  };

  const vote = reactionMap[event.reaction];
  if (!vote) return;

  try {
    await axios.post(`${CENTRAL_API_URL}/v1/vote`, {
      message_id: event.item.ts,
      conversation_id: "",
      user_id: event.user,
      vote,
    });
  } catch (error: any) {
    console.error("Reaction vote failed:", error.message);
  }
});

// Start the app
(async () => {
  await app.start();
  console.log("⚡ FloxBot Slack adapter is running (Socket Mode)");
})();

export { app };
