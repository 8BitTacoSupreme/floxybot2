/**
 * API response → Slack Block Kit formatter.
 *
 * Converts FloxBot API responses to rich Slack messages with code blocks,
 * links, and vote buttons.
 */

export interface SlackBlock {
  type: string;
  text?: any;
  elements?: any[];
  block_id?: string;
  accessory?: any;
}

export interface FormattedResponse {
  text: string; // Fallback plain text
  blocks: SlackBlock[];
  thread_ts?: string;
}

/**
 * Format a FloxBot API response for Slack.
 */
export function formatResponse(
  apiResponse: any,
  threadTs?: string
): FormattedResponse {
  const text = apiResponse.text || "I couldn't generate a response.";
  const blocks: SlackBlock[] = [];

  // Main response text (split into sections if long)
  const sections = splitIntoSections(text);
  for (const section of sections) {
    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text: section,
      },
    });
  }

  // Code blocks from response
  const codeBlocks: string[] = apiResponse.code_blocks || [];
  for (const code of codeBlocks) {
    // Only add separate code blocks if they weren't inline
    if (!text.includes(code)) {
      blocks.push({
        type: "section",
        text: {
          type: "mrkdwn",
          text: "```" + code + "```",
        },
      });
    }
  }

  // Skills used (context line)
  const skills: any[] = apiResponse.skills_used || [];
  if (skills.length > 0) {
    const skillNames = skills.map((s: any) => s.name).join(", ");
    blocks.push({
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: `_Skills: ${skillNames} | Confidence: ${Math.round(
            (apiResponse.confidence || 0) * 100
          )}%_`,
        },
      ],
    });
  }

  // Vote buttons (if suggested)
  if (apiResponse.suggested_votes) {
    blocks.push({
      type: "actions",
      block_id: `vote_${apiResponse.response_id || "unknown"}`,
      elements: [
        {
          type: "button",
          text: { type: "plain_text", text: "👍 Helpful", emoji: true },
          action_id: "vote_up",
          value: apiResponse.response_id || "",
          style: "primary",
        },
        {
          type: "button",
          text: { type: "plain_text", text: "👎 Not helpful", emoji: true },
          action_id: "vote_down",
          value: apiResponse.response_id || "",
        },
      ],
    });
  }

  return {
    text,
    blocks,
    thread_ts: threadTs,
  };
}

/**
 * Split long text into Slack-compatible sections (max 3000 chars each).
 */
function splitIntoSections(text: string, maxLen: number = 2900): string[] {
  if (text.length <= maxLen) return [text];

  const sections: string[] = [];
  let remaining = text;

  while (remaining.length > 0) {
    if (remaining.length <= maxLen) {
      sections.push(remaining);
      break;
    }

    // Find a good break point (paragraph, then sentence, then word)
    let breakAt = remaining.lastIndexOf("\n\n", maxLen);
    if (breakAt < maxLen * 0.5) {
      breakAt = remaining.lastIndexOf(". ", maxLen);
    }
    if (breakAt < maxLen * 0.3) {
      breakAt = remaining.lastIndexOf(" ", maxLen);
    }
    if (breakAt <= 0) {
      breakAt = maxLen;
    }

    sections.push(remaining.slice(0, breakAt + 1));
    remaining = remaining.slice(breakAt + 1);
  }

  return sections;
}
