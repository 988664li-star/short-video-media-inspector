import { useCallback, useRef, useState } from "react";

import { getUserPosts, getUserProfile } from "../api/douyin";
import type { UserProfilePayload, UserSummary } from "../types/douyin";


export function useUserDrawer() {
  const [user, setUser] = useState<UserSummary | null>(null);
  const [payload, setPayload] = useState<UserProfilePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [loadMoreError, setLoadMoreError] = useState("");
  const requestId = useRef(0);
  const loadingMoreRef = useRef(false);

  const open = useCallback(async (nextUser: UserSummary) => {
    if (!nextUser.sec_user_id) return;
    const currentRequest = ++requestId.current;
    setUser(nextUser);
    setPayload(null);
    setError("");
    setLoadMoreError("");
    setLoading(true);
    setLoadingMore(false);
    loadingMoreRef.current = false;
    try {
      const result = await getUserProfile(nextUser.sec_user_id);
      if (requestId.current === currentRequest) setPayload(result);
    } catch (requestError) {
      if (requestId.current === currentRequest) {
        setError(requestError instanceof Error ? requestError.message : "用户资料获取失败，请稍后重试。");
      }
    } finally {
      if (requestId.current === currentRequest) setLoading(false);
    }
  }, []);

  const loadMore = useCallback(async () => {
    const nextCursor = payload?.pagination.next_cursor;
    const secUserId = payload?.profile.sec_user_id || user?.sec_user_id;
    if (
      loadingMoreRef.current
      || !payload?.pagination.has_more
      || nextCursor === null
      || nextCursor === undefined
      || !secUserId
    ) return;

    const currentRequest = requestId.current;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    setLoadMoreError("");
    try {
      const page = await getUserPosts(secUserId, nextCursor);
      if (requestId.current !== currentRequest) return;
      setPayload((current) => {
        if (!current) return current;
        const knownIds = new Set(current.posts.map((post) => post.aweme_id));
        const newPosts = page.posts.filter((post) => !knownIds.has(post.aweme_id));
        return {
          ...current,
          access_mode: page.access_mode,
          posts: [...current.posts, ...newPosts],
          pagination: page.pagination,
        };
      });
    } catch (requestError) {
      if (requestId.current === currentRequest) {
        setLoadMoreError(requestError instanceof Error ? requestError.message : "更多作品获取失败，请稍后重试。");
      }
    } finally {
      if (requestId.current === currentRequest) {
        loadingMoreRef.current = false;
        setLoadingMore(false);
      }
    }
  }, [payload, user]);

  const close = useCallback(() => {
    requestId.current += 1;
    setUser(null);
    setPayload(null);
    setLoading(false);
    setLoadingMore(false);
    loadingMoreRef.current = false;
    setError("");
    setLoadMoreError("");
  }, []);

  return {
    user, payload, loading, loadingMore, error, loadMoreError,
    open, close, loadMore,
  };
}
