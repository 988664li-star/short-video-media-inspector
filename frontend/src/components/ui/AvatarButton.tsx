import type { CSSProperties } from "react";

import type { UserSummary } from "../../types/douyin";


interface AvatarButtonProps {
  user: UserSummary;
  imageUrl?: string;
  size?: "small" | "reply" | "medium" | "large";
  onOpenUser: (user: UserSummary) => void;
}

export function AvatarButton({
  user,
  imageUrl,
  size = "small",
  onOpenUser,
}: AvatarButtonProps) {
  const canOpen = Boolean(user.sec_user_id);
  const style = imageUrl
    ? ({ "--avatar-image": `url("${imageUrl}")` } as CSSProperties)
    : undefined;
  if (!canOpen) {
    return <span className={`avatar avatar--${size}`} style={style} aria-label={`${user.nickname}的头像`} />;
  }
  return (
    <button
      type="button"
      className={`avatar avatar--${size} avatar--interactive`}
      style={style}
      aria-label={`查看${user.nickname}的资料`}
      title={`查看${user.nickname}的资料`}
      onClick={() => onOpenUser(user)}
    />
  );
}
