import { useCallback, useRef, useState } from "react";

import {
  getAccountLibrary,
  getAccountProfile,
  getCommentReplies,
  getComments,
  getConnections,
  getFeed,
  getFollowingLive,
  getLiveRoom,
  getLiveMessages,
  getLiveStatus,
  getRelatedPosts,
  getSuggestions,
  getUserContent,
  getUserProfile,
  searchUserPosts,
} from "../../api/douyin";
import type { CapabilityPage } from "../../types/douyin";
import type { CapabilityDefinition, CapabilityField } from "./catalog";


export type CapabilityValues = Record<CapabilityField, string>;

export interface CapabilityOutput {
  kind: CapabilityDefinition["resultKind"];
  payload: Record<string, unknown>;
  items: unknown[];
  pagination?: { has_more: boolean; next_cursor?: number | null };
}

const pageOutput = (kind: CapabilityOutput["kind"], page: CapabilityPage<unknown>): CapabilityOutput => ({
  kind,
  payload: page as unknown as Record<string, unknown>,
  items: page.items,
  pagination: page.pagination,
});

export function useCapabilityRunner() {
  const [output, setOutput] = useState<CapabilityOutput | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const cache = useRef(new Map<string, CapabilityOutput>());
  const pending = useRef(new Map<string, Promise<CapabilityOutput>>());
  const activeKey = useRef("");
  const loadingMoreRef = useRef(false);

  const request = useCallback(async (definition: CapabilityDefinition, values: CapabilityValues, cursor = 0) => {
    switch (definition.id) {
      case "comments": return pageOutput("comments", await getComments(values.awemeId, cursor));
      case "comment-replies": return pageOutput("comments", await getCommentReplies(values.awemeId, values.commentId, cursor));
      case "related-posts": return pageOutput("posts", await getRelatedPosts(values.awemeId));
      case "user-profile": {
        const payload = await getUserProfile(values.secUserId);
        return { kind: "users" as const, payload: payload as unknown as Record<string, unknown>, items: [payload.profile] };
      }
      case "user-posts": return pageOutput("posts", await getUserContent("posts", values.secUserId, cursor));
      case "user-likes": return pageOutput("posts", await getUserContent("likes", values.secUserId, cursor));
      case "mix-posts": return pageOutput("posts", await getUserContent("mix", values.mixId, cursor));
      case "following": return pageOutput("users", await getConnections("following", values.secUserId, values.userId, cursor));
      case "followers": return pageOutput("users", await getConnections("followers", values.secUserId, values.userId, cursor));
      case "collections": return pageOutput("posts", await getAccountLibrary("collections", "", cursor));
      case "folders": return pageOutput("folders", await getAccountLibrary("folders", "", cursor));
      case "folder-posts": return pageOutput("posts", await getAccountLibrary("folder_posts", values.folderId, cursor));
      case "music": return pageOutput("music", await getAccountLibrary("music", "", cursor));
      case "recommended-feed": return pageOutput("posts", await getFeed("recommended", cursor));
      case "following-feed": return pageOutput("posts", await getFeed("following", cursor));
      case "friends-feed": return pageOutput("posts", await getFeed("friends", cursor));
      case "user-search": return pageOutput("posts", await searchUserPosts(values.secUserId, values.keyword, cursor));
      case "suggestions": return pageOutput("words", await getSuggestions(values.query));
      case "live-room": {
        const payload = await getLiveRoom(values.roomId);
        return { kind: "live" as const, payload: payload as unknown as Record<string, unknown>, items: [payload.live] };
      }
      case "live-status": {
        const payload = await getLiveStatus(values.roomId);
        return pageOutput("raw", payload);
      }
      case "live-messages": return pageOutput("raw", await getLiveMessages(values.roomId, values.userUniqueId));
      case "account-profile": {
        const payload = await getAccountProfile();
        return { kind: "users" as const, payload: payload as unknown as Record<string, unknown>, items: [payload.profile] };
      }
      case "following-live": return pageOutput("live-list", await getFollowingLive());
    }
  }, []);

  const remember = useCallback((key: string, result: CapabilityOutput) => {
    if (cache.current.size >= 30 && !cache.current.has(key)) {
      const oldestKey = cache.current.keys().next().value;
      if (oldestKey) cache.current.delete(oldestKey);
    }
    cache.current.set(key, result);
  }, []);

  const run = useCallback(async (
    definition: CapabilityDefinition,
    values: CapabilityValues,
    requestKey: string,
  ) => {
    activeKey.current = requestKey;
    setLoadingMore(false);
    loadingMoreRef.current = false;
    setError("");

    const cached = cache.current.get(requestKey);
    if (cached) {
      setOutput(cached);
      setLoading(false);
      return;
    }

    setLoading(true);
    setOutput(null);
    let currentRequest = pending.current.get(requestKey);
    if (!currentRequest) {
      currentRequest = request(definition, values);
      pending.current.set(requestKey, currentRequest);
    }
    try {
      const result = await currentRequest;
      remember(requestKey, result);
      if (activeKey.current === requestKey) setOutput(result);
    } catch (reason) {
      if (activeKey.current === requestKey) {
        setError(reason instanceof Error ? reason.message : "能力调用失败");
      }
    } finally {
      if (pending.current.get(requestKey) === currentRequest) {
        pending.current.delete(requestKey);
      }
      if (activeKey.current === requestKey) setLoading(false);
    }
  }, [remember, request]);

  const loadMore = useCallback(async (definition: CapabilityDefinition, values: CapabilityValues) => {
    const cursor = output?.pagination?.next_cursor;
    const requestKey = activeKey.current;
    if (cursor === null || cursor === undefined || loadingMoreRef.current || !requestKey) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    setError("");
    try {
      const next = await request(definition, values, cursor);
      const current = cache.current.get(requestKey) || output;
      if (!current) return;
      const items = [...current.items, ...next.items];
      const merged = { ...next, items, payload: { ...next.payload, items } };
      remember(requestKey, merged);
      if (activeKey.current === requestKey) setOutput(merged);
    } catch (reason) {
      if (activeKey.current === requestKey) {
        setError(reason instanceof Error ? reason.message : "下一页获取失败");
      }
    } finally {
      loadingMoreRef.current = false;
      if (activeKey.current === requestKey) setLoadingMore(false);
    }
  }, [output, remember, request]);

  const clearVisible = useCallback(() => {
    activeKey.current = "";
    loadingMoreRef.current = false;
    setOutput(null);
    setLoading(false);
    setLoadingMore(false);
    setError("");
  }, []);

  return { output, loading, loadingMore, error, run, loadMore, clearVisible };
}
