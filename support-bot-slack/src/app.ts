/**
 * FloxBot Slack Adapter — thin, stateless adapter using Bolt SDK + Socket Mode.
 *
 * Normalizes Slack messages to the canonical format and forwards to Central API.
 *
 * TODO: Implement:
 * - Bolt app initialization with Socket Mode
 * - Message event handler → normalize → POST /v1/message
 * - Response formatting (Slack blocks)
 * - Vote reactions (thumbs up/down → POST /v1/vote)
 * - Thread context extraction
 */

export const CENTRAL_API_URL = process.env.FLOXBOT_API_URL || "http://localhost:8000";

// Placeholder — will implement with @slack/bolt
console.log("FloxBot Slack adapter (not yet implemented)");
