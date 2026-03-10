/**
 * Module-level feedback context — screens update this so FeedbackCapture
 * can include rich context without prop drilling or React Context.
 */

interface FeedbackContext {
  screen: string;
  articleId?: string;
  articleTitle?: string;
  scrollProgress?: number;
  readingMode?: string;
  activeLens?: string;
  extra?: Record<string, any>;
}

let _context: FeedbackContext = { screen: 'unknown' };

export function setFeedbackContext(ctx: Partial<FeedbackContext>) {
  _context = { ..._context, ...ctx };
}

export function getFeedbackContext(): FeedbackContext {
  return { ..._context };
}
