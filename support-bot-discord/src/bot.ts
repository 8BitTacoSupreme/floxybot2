/**
 * FloxBot Discord Adapter — thin, stateless adapter using discord.js + Gateway WebSocket.
 *
 * Normalizes Discord messages to the canonical format and forwards to Central API.
 *
 * TODO: Implement:
 * - Client initialization with Gateway intents
 * - Message event handler → normalize → POST /v1/message
 * - Response formatting (Discord embeds)
 * - Vote reactions (emoji → POST /v1/vote)
 * - Thread/channel context extraction
 */

export const CENTRAL_API_URL = process.env.FLOXBOT_API_URL || "http://localhost:8000";

// Placeholder — will implement with discord.js
console.log("FloxBot Discord adapter (not yet implemented)");
