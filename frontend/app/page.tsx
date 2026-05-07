"use client";

import ChatScreen from '@/app/components/ChatScreen';
import ServerWarmingBanner from '@/app/components/ServerWarmingBanner';

export default function Home() {
  return (
    <>
      <ServerWarmingBanner />
      <ChatScreen />
    </>
  );
}
