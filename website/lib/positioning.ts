// How we describe the business in one breath. NSFAG (Name, Same, Fame, Aim,
// Game) is Daniel Priestley's Key Person of Influence framework. We use it
// because it forces Fame to be stated as something we actually do rather than
// a number we wish we had, and because it keeps Same and Aim honest: a pitch
// with no Same is an advert, and a pitch with no Game has no way of saying no.

/**
 * The pitch, written to be spoken aloud in under 30 seconds. That is roughly
 * 70 words at presenting pace, so anything longer gets skimmed. It is read out
 * to producers on calls, which means every extra clause is a clause they sit
 * through before we reach the point.
 *
 * Fame is an unfilled TODO on purpose. Do not close the slot with install
 * counts, review counts, subscriber numbers or client names we cannot show a
 * source for: it is the one line a producer can check in ten seconds, and a
 * number we cannot defend costs more than the missing number does. Replace the
 * placeholder with how people genuinely arrive (talks given, forum answers, a
 * release already in their sessions) and keep it short.
 */
export const NSFAG_PITCH =
  "Name: NITE DSP, audio production tools and engineering for producers. " +
  "Same: twelve years of professional audio work in studios, game audio, and now AI audio tools. " +
  "Fame: [TODO: how producers find us]. " +
  "Aim: small tools that do one job properly, plus DSP, website and research work for hire. " +
  "Game: ship finished tools, not feature lists. Answer technical questions in the open. " +
  "Say no when the month is full.";

/**
 * Footer cut of the same pitch, roughly 30 words. It omits Fame on purpose:
 * the slot is still a TODO, and printing a placeholder in the footer of every
 * page is noise a visitor never asked for. Name, Same and Aim still carry the
 * positioning, so the sentence says what we are for without the gap in it.
 */
export const NSFAG_PITCH_FOOTER =
  "NITE DSP builds small audio production tools, and takes DSP, website and research work for hire. " +
  "Twelve years in studios, game audio and AI audio tools.";

/**
 * Monthly capacity ceiling for the studio services, one hard number per line.
 *
 * Both are 0 until Jack sets them, and 0 is the "not measured yet" sentinel
 * rather than a real number. /services reads a 0 as unset and prints a visible
 * TODO marker in place of the figure, because "0 mix revisions a month" on a
 * live page reads as a refusal of business, and a guessed number is a promise.
 *
 * TODO(Jack): set these to what you will actually honour in a month you are
 * already busy. Count mix revisions in rounds, not projects -- a standard mix
 * runs 2-4 rounds, so a project-based cap silently triples the work behind it.
 * Mixing, mastering and DSP contract work compete for the same hours, so leave
 * headroom in both numbers rather than quoting your best month.
 */
export const SERVICES_CAPACITY = {
  mixRevisionsPerMonth: 0,
  masteringProjectsPerMonth: 0,
};