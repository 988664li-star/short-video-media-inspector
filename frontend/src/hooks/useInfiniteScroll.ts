import { useEffect, useRef } from "react";
import type { RefObject } from "react";


export function useInfiniteScroll(
  rootRef: RefObject<HTMLElement | null>,
  enabled: boolean,
  onLoadMore: () => void,
) {
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    const sentinel = sentinelRef.current;
    if (!enabled || !root || !sentinel) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) onLoadMore();
      },
      { root, rootMargin: "0px 0px 360px", threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [enabled, onLoadMore, rootRef]);

  return sentinelRef;
}
