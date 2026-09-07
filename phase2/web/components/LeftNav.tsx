"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageCircle, Radar } from "lucide-react";
import { useUnreviewedHighCount } from "@/hooks/useSignals";
import { cn } from "@/lib/utils";

export function LeftNav() {
  const pathname = usePathname();
  const highCount = useUnreviewedHighCount();

  const items = [
    { href: "/", label: "Radar feed", icon: Radar, badge: highCount },
    { href: "/assistant", label: "Assistant", icon: MessageCircle, badge: 0 },
  ];

  return (
    <nav className="flex w-16 shrink-0 flex-col items-center gap-1 border-r border-border bg-surface py-4">
      {items.map(({ href, label, icon: Icon, badge }) => {
        const active = href === "/" ? pathname === "/" || pathname.startsWith("/signal") : pathname === href;
        return (
          <Link
            key={href}
            href={href}
            title={
              badge > 0 ? `${label} — ${badge} high-urgency signals not yet reviewed` : label
            }
            className={cn(
              "relative flex h-11 w-11 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-accent-soft hover:text-accent",
              active && "bg-accent-soft text-accent"
            )}
          >
            <Icon size={18} strokeWidth={1.75} />
            {badge > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-high px-1 font-mono text-[10px] text-white">
                {badge}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
