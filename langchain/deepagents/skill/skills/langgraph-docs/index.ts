// index.ts
export function resolveLlmsUrl(url: string) {
  return url.endsWith(".md") ? url.slice(0, -3) : url;
}