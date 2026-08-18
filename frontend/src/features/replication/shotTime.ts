export function formatShotTimestamp(seconds: number) {
  const totalSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, "0");
  const remainder = (totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}
