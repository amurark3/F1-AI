"use client";

import NavShell from '@/app/components/NavShell';
import ChatScreen from '@/app/components/ChatScreen';
import ServerWarmingBanner from '@/app/components/ServerWarmingBanner';

export default function Home() {
  return (
    <NavShell>
      <ServerWarmingBanner />
      <ChatScreen />
    </NavShell>
  );
}
