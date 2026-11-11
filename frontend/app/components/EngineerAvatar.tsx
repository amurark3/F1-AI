import { Bot } from "lucide-react";

// The engineer's identity tile: a red-tinted tile, like the chat's New chat
// button, so the conversation reads as one surface.
const SIZES = {
  sm: { box: "h-8 w-8", icon: "h-4 w-4" },
  md: { box: "h-10 w-10", icon: "h-5 w-5" },
  lg: { box: "h-14 w-14", icon: "h-7 w-7" },
} as const;

interface EngineerAvatarProps {
  size?: keyof typeof SIZES;
}

export default function EngineerAvatar({ size = "sm" }: EngineerAvatarProps) {
  const { box, icon } = SIZES[size];
  return (
    <div
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-md border border-[#E10600]/35 bg-[#E10600]/15 ${box}`}
    >
      <Bot className={`text-[#FF4655] ${icon}`} />
    </div>
  );
}
