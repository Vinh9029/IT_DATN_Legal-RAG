import React, { useRef, useState } from 'react';
import { Heart } from 'lucide-react';
import { cn } from '@/components/ui/button';
import { communityService, type ReactionTarget } from '@/lib/community-service';
import { useRequireLogin } from '@/lib/login-gate';

interface LikeButtonProps {
  target: ReactionTarget;
  targetId: number;
  liked: boolean;
  count: number;
  size?: 'sm' | 'md';
  onError?: (message: string) => void;
}

// Cập nhật lạc quan: đổi giao diện ngay, gửi PUT/DELETE (idempotent) theo trạng thái mong muốn.
// Bấm liên tục thì chỉ phản hồi của lần bấm cuối cùng được dùng để đồng bộ lại số đếm.
export const Like_button: React.FC<LikeButtonProps> = ({ target, targetId, liked, count, size = 'md', onError }) => {
  const requireLogin = useRequireLogin();
  const [state, setState] = useState({ liked, count });
  const [popKey, setPopKey] = useState(0);
  const latestRequest = useRef(0);

  // Dữ liệu từ server thay đổi (tải lại feed, đổi tài khoản) → đồng bộ lại
  const [fromProps, setFromProps] = useState({ liked, count });
  if (fromProps.liked !== liked || fromProps.count !== count) {
    setFromProps({ liked, count });
    setState({ liked, count });
  }

  const toggle = async () => {
    if (!requireLogin()) return;
    const prev = state;
    const next = { liked: !prev.liked, count: Math.max(0, prev.count + (prev.liked ? -1 : 1)) };
    setState(next);
    if (next.liked) setPopKey((k) => k + 1);

    const requestId = ++latestRequest.current;
    try {
      const res = await communityService.setLike(target, targetId, next.liked);
      if (requestId === latestRequest.current) setState({ liked: res.liked, count: res.like_count });
    } catch (e) {
      if (requestId === latestRequest.current) {
        setState(prev);
        onError?.(e instanceof Error ? e.message : 'Không thể cập nhật lượt thích.');
      }
    }
  };

  const small = size === 'sm';
  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={state.liked}
      aria-label={state.liked ? 'Bỏ thích' : 'Thích'}
      className={cn(
        'group/like inline-flex items-center gap-1.5 rounded-lg font-semibold transition-colors cursor-pointer',
        small ? 'px-1.5 py-1 text-xs' : 'px-3 py-2 text-sm',
        state.liked ? 'text-rose-600 hover:bg-rose-50' : 'text-slate-500 hover:bg-slate-100 hover:text-rose-600',
      )}
    >
      <span className="relative inline-flex">
        {popKey > 0 && state.liked && (
          <span key={`burst-${popKey}`} className="like-burst absolute inset-0 rounded-full bg-rose-400" />
        )}
        <Heart
          key={popKey}
          className={cn(
            small ? 'size-3.5' : 'size-[18px]',
            'relative transition-colors',
            state.liked ? 'fill-rose-500 stroke-rose-500' : 'group-hover/like:stroke-rose-500',
            popKey > 0 && state.liked && 'like-pop',
          )}
        />
      </span>
      <span key={state.count} className={cn('count-tick tabular-nums', (state.count > 0 || !small) && 'min-w-[1ch]')}>
        {state.count > 0 ? state.count : small ? '' : 'Thích'}
      </span>
    </button>
  );
};
