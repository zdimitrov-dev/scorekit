/**
 * IMSLP's `Instrumentation` field can be long and contain literal `<br>` and
 * markup (e.g. `"Solo": piano<br>"Orchestra": flutes, oboes, ...`). For a compact
 * chip/badge we keep just the first segment, strip tags, and truncate.
 */
export function cleanInstrumentation(value?: string, max = 38): string | undefined {
  if (!value) return undefined;
  const first = value
    .split(/<br\s*\/?>/i)[0]
    .replace(/<[^>]+>/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!first) return undefined;
  return first.length > max ? first.slice(0, max - 1).trimEnd() + "…" : first;
}
