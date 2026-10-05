import React, { useEffect, useState } from 'react';

const DEFAULT_PHRASES = [
  'Đang phân tích câu hỏi',
  'Đang tra cứu văn bản pháp luật',
  'Đang truy tìm điều khoản liên quan',
  'Đang đối chiếu hiệu lực văn bản',
  'Đang suy nghĩ',
  'Đang soạn câu trả lời',
];

export const Thinking_indicator: React.FC<{ phrases?: string[]; interval?: number; className?: string }> = ({
  phrases = DEFAULT_PHRASES,
  interval = 3500,
  className = '',
}) => {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setIndex((i) => (i + 1) % phrases.length), interval);
    return () => clearInterval(timer);
  }, [phrases.length, interval]);

  return (
    <div className={`flex items-center gap-3 py-1 ${className}`}>
      <div className="flex space-x-1">
        <div className="size-2 rounded-full bg-[#2563EB] animate-bounce" style={{ animationDelay: '0ms' }} />
        <div className="size-2 rounded-full bg-[#2563EB] animate-bounce" style={{ animationDelay: '150ms' }} />
        <div className="size-2 rounded-full bg-[#2563EB] animate-bounce" style={{ animationDelay: '300ms' }} />
      </div>
      <span key={index} className="thinking-text thinking-fade font-medium">
        {phrases[index]}...
      </span>
    </div>
  );
};
