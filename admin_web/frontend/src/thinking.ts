type Part = Record<string, any>;

// Parse the accumulated snapshot, not individual SSE chunks. This also works
// for restored history and tags split across adjacent text parts.
export function splitThinking(text: string, streaming = false): Part[] {
  const result: Part[] = [];
  let thinking = false,
    buffer = "",
    fence = "",
    inline = "";
  const flush = () => {
    if (buffer)
      result.push({ type: thinking ? "reasoning" : "text", text: buffer });
    buffer = "";
  };
  for (let i = 0; i < text.length; ) {
    const rest = text.slice(i);
    const lineStart = i === 0 || text[i - 1] === "\n";
    const marker = lineStart
      ? /^( {0,3})(`{3,}|~{3,})[^\n]*(?:\n|$)/.exec(rest)
      : null;
    if (marker && !inline) {
      const run = marker[2];
      if (!fence) fence = run;
      else if (
        run[0] === fence[0] &&
        run.length >= fence.length &&
        /^\s*$/.test(marker[0].slice(marker[1].length + run.length))
      )
        fence = "";
      buffer += marker[0];
      i += marker[0].length;
      continue;
    }
    if (fence) {
      buffer += text[i++];
      continue;
    }
    if (text[i] === "\\" && !inline && i + 1 < text.length) {
      buffer += text.slice(i, i + 2);
      i += 2;
      continue;
    }
    const ticks = /^`+/.exec(rest);
    if (ticks) {
      if (!inline) inline = ticks[0];
      else if (inline === ticks[0]) inline = "";
      buffer += ticks[0];
      i += ticks[0].length;
      continue;
    }
    if (!inline) {
      const tag = thinking ? "</think>" : "<think>";
      if (rest.toLowerCase().startsWith(tag)) {
        flush();
        thinking = !thinking;
        i += tag.length;
        continue;
      }
      // Withhold only a potential trailing delimiter while it is arriving.
      if (streaming && tag.startsWith(rest.toLowerCase())) break;
    }
    buffer += text[i++];
  }
  flush();
  return result;
}

export function displayParts(
  parts: Part[],
  assistant: boolean,
  streaming = false,
): Part[] {
  if (!assistant) return parts;
  const output: Part[] = [];
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    if (part.type !== "text") {
      output.push(part);
      continue;
    }
    let text = part.text || "";
    while (parts[i + 1]?.type === "text") text += parts[++i].text || "";
    output.push(
      ...splitThinking(text, streaming && i === parts.length - 1).map(
        (segment, index) => ({
          ...segment,
          id: `${part.id || i}:segment:${index}`,
        }),
      ),
    );
  }
  return output;
}
