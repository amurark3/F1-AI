"use client";

import NavShell from '@/app/components/NavShell';
import ChatScreen from '@/app/components/ChatScreen';

export default function Home() {
  return (
    <NavShell>
      <ChatScreen />
    </NavShell>
  );
}
